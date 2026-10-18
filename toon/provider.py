"""One place that talks to the language model: local Ollama (default) or Claude (LLM_PROVIDER=anthropic).
Trimmed from shorts_factory_v8/shorts/provider.py."""
import json
import logging

from . import config

log = logging.getLogger("toon.provider")
_NO_FORCE = set()  # models that refuse tool_choice "tool"


def _json_only(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[4:] if t.lower().startswith("json") else t
    a, b = t.find("{"), t.rfind("}")
    return t[a:b + 1] if 0 <= a < b else t


def chat(system: str, user: str, schema: dict = None, temperature: float = 0.8, provider: str = None) -> str:
    """Returns the reply text; with a schema the reply is a JSON string that follows it."""
    provider = provider or config.LLM_PROVIDER
    if provider == "anthropic":
        import anthropic
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty in .env")
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=3, timeout=180)
        kw = {"model": config.ANTHROPIC_MODEL, "max_tokens": 4000, "system": system,
              "messages": [{"role": "user", "content": user}]}
        if schema:  # a tool call gives reliable structured output
            kw["tools"] = [{"name": "return_json", "description": "Return the episode as JSON.", "input_schema": schema}]
            kw["tool_choice"] = {"type": "auto"} if config.ANTHROPIC_MODEL in _NO_FORCE else {"type": "tool", "name": "return_json"}
            if config.ANTHROPIC_MODEL in _NO_FORCE:
                kw["system"] = system + "\n\nAnswer by calling the return_json tool exactly once."
        try:
            resp = client.messages.create(**kw)
        except anthropic.BadRequestError as e:
            if not schema or "tool_choice" not in str(e) or config.ANTHROPIC_MODEL in _NO_FORCE:
                raise
            _NO_FORCE.add(config.ANTHROPIC_MODEL)  # this model refuses a forced tool: ask nicely instead
            return chat(system, user, schema, temperature, provider)
        for block in resp.content:
            if getattr(block, "type", "") == "tool_use":
                return json.dumps(block.input, ensure_ascii=False)
        return _json_only("".join(getattr(b, "text", "") for b in resp.content)) if schema else \
            "".join(getattr(b, "text", "") for b in resp.content)
    import ollama
    client = ollama.Client(host=config.OLLAMA_HOST)
    kw = {"model": config.OLLAMA_MODEL, "options": {"temperature": temperature, "num_ctx": 8192},
          "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if schema:
        kw["format"] = schema
    return client.chat(**kw).message.content


def chat_json(system: str, user: str, schema: dict, temperature: float = 0.8, tries: int = 3) -> dict:
    last = None
    for i in range(tries):
        try:
            return json.loads(_json_only(chat(system, user, schema, temperature)))
        except Exception as e:  # bad JSON or a network hiccup: ask again
            last = e
            log.warning("model answer unusable (try %d): %s", i + 1, str(e)[:160])
    raise RuntimeError(f"the model did not return usable JSON: {last}")


def describe() -> str:
    return f"claude:{config.ANTHROPIC_MODEL}" if config.LLM_PROVIDER == "anthropic" else f"ollama:{config.OLLAMA_MODEL}"
