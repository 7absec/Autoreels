"""Optional vidIQ helper. Everything here is best effort: with no key, no network, no credits or any error,
every function returns None / the input unchanged, so the factory behaves exactly as before.
.env settings:
  VIDIQ_API_KEY=...            (empty = vidIQ is off)
  VIDIQ_URL=https://mcp.vidiq.com/mcp
  VIDIQ=off                    switch everything off
  VIDIQ_MAX_CREDITS=30         most credits one run (one process) may spend
  VIDIQ_TITLES=on|off          score the title and swap in a better one (5 to 10 credits per video)
  VIDIQ_TAGS=on|off            add searched keywords to the tags
  VIDIQ_TRENDS=on|off          show search demand to the topic picker
"""
import json
import logging
import os
import re
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "vidiq_cache.json"
COST = {"vidiq_score_title": 5, "vidiq_generate_titles": 5, "vidiq_keyword_research": 2,
        "vidiq_trending_videos": 5, "vidiq_balance": 0, "vidiq_instagram_connected_accounts": 0,
        "vidiq_instagram_publish_reel": 0, "vidiq_job_poll": 0}
_state = {"spent": 0, "fails": 0, "sid": None, "init": False, "off": False}


def _env(k, d=""):
    return os.getenv(k, d).strip()


def enabled() -> bool:
    return bool(_env("VIDIQ_API_KEY")) and _env("VIDIQ", "on").lower() != "off" and not _state["off"] and _state["fails"] < 2


def _flag(k) -> bool:
    return enabled() and _env(k, "on").lower() != "off"


def _budget() -> int:
    try:
        return int(_env("VIDIQ_MAX_CREDITS", "30"))
    except ValueError:
        return 30


def _post(payload: dict):
    h = {"Authorization": "Bearer " + _env("VIDIQ_API_KEY"), "Content-Type": "application/json",
         "Accept": "application/json, text/event-stream"}
    if _state["sid"]:
        h["Mcp-Session-Id"] = _state["sid"]
    r = requests.post(_env("VIDIQ_URL", "https://mcp.vidiq.com/mcp"), json=payload, headers=h, timeout=25)
    if r.status_code in (401, 403):
        _state["off"] = True  # wrong key or OAuth only: stop trying this run
        raise RuntimeError("vidIQ refused the key (HTTP %d)" % r.status_code)
    r.raise_for_status()
    if r.headers.get("Mcp-Session-Id"):
        _state["sid"] = r.headers["Mcp-Session-Id"]
    body = r.text.strip()
    if not body:
        return {}
    if "data:" in body and not body.startswith("{"):
        lines = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")]
        body = lines[-1] if lines else "{}"
    return json.loads(body)


def call(tool: str, args: dict):
    """Returns the tool's JSON result, or None. Never raises."""
    if not enabled():
        return None
    cost = COST.get(tool, 5)
    if _state["spent"] + cost > _budget():
        log.info("vidIQ credit limit for this run reached, using the normal way")
        return None
    try:
        if not _state["init"]:
            _post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "autoreels", "version": "1"}}})
            try:
                _post({"jsonrpc": "2.0", "method": "notifications/initialized"})
            except Exception:
                pass
            _state["init"] = True
        res = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}})
        if res.get("error"):
            raise RuntimeError(str(res["error"])[:200])
        r = res.get("result") or {}
        if r.get("isError"):
            raise RuntimeError("tool error " + json.dumps(r.get("content"))[:200])
        _state["spent"] += cost
        if r.get("structuredContent"):
            return r["structuredContent"]
        txt = "".join(c.get("text", "") for c in r.get("content", []) if c.get("type") == "text")
        try:
            return json.loads(txt)
        except ValueError:  # the tool wraps its JSON in a short text summary
            a, b = txt.find("{"), txt.rfind("}")
            return json.loads(txt[a:b + 1])
    except Exception as e:
        _state["last_error"] = str(e)[:400]
        if not tool.startswith("vidiq_instagram") and tool != "vidiq_job_poll":
            _state["fails"] += 1  # Instagram errors must not switch off title scoring
        log.warning("vidIQ %s skipped (%s)", tool, str(e)[:160])
        return None


def _cache_get(key):
    try:
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        v = d.get(key)
        if v and time.time() - v["t"] < 86400 * 3:
            return v["v"]
    except Exception:
        pass
    return None


def _cache_put(key, val):
    try:
        try:
            d = json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        d[key] = {"t": time.time(), "v": val}
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass


def keywords(seed: str):
    """[{keyword, volume, competition, overall}] for a seed phrase, or None."""
    seed = (seed or "").strip().lower()
    if not seed or not enabled():
        return None
    got = _cache_get("kw:" + seed)
    if got is not None:
        return got
    res = call("vidiq_keyword_research", {"mode": "research", "keyword": seed, "country": "IN"})
    if not isinstance(res, dict):
        return None
    rows = []
    for r in [res.get("seedKeyword")] + list(res.get("relatedKeywords") or []):
        if isinstance(r, dict) and r.get("keyword"):
            rows.append({k: r.get(k) for k in ("keyword", "volume", "competition", "overall")})
    if rows:
        _cache_put("kw:" + seed, rows)
    return rows or None


def seed_score(seed: str):
    rows = keywords(seed)
    if not rows:
        return None
    r = rows[0]
    try:
        return float(r.get("overall") if r.get("overall") is not None else r.get("volume"))
    except (TypeError, ValueError):
        return None


def extra_tags(seed: str, have: list, n: int = 4) -> list:
    """Searched phrases worth adding as tags, best first. [] when vidIQ is off."""
    if not _flag("VIDIQ_TAGS"):
        return []
    rows = keywords(seed) or []
    have_l = {t.lower() for t in have}
    rows = sorted(rows[1:], key=lambda r: -(r.get("overall") or 0) if isinstance(r.get("overall"), (int, float)) else 0)
    out = []
    for r in rows:
        k = str(r["keyword"]).strip().lower()
        if 3 <= len(k) <= 30 and k not in have_l and len(k.split()) <= 4:
            out.append(k)
        if len(out) >= n:
            break
    return out


def _plain(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"#\w+", "", t or "")).strip()


def better_title(title: str, description: str, seed_words: list, kind: str = "short", max_len: int = 70):
    """(new_title, old_score, new_score) or None. Only swaps in a title that is clearly better and still about the same thing."""
    if not _flag("VIDIQ_TITLES") or not title:
        return None
    s = call("vidiq_score_title", {"title": title, "type": kind})
    try:
        old = float(s["score"])
    except Exception:
        return None
    try:
        floor = float(_env("VIDIQ_TITLE_MIN", "80"))
    except ValueError:
        floor = 80.0
    if old >= floor:
        return (title, old, old)
    g = call("vidiq_generate_titles", {"title": title, "description": (description or title)[:400], "type": kind,
                                         "numTitles": 5, "language": "en"})
    best = None
    sw = {w for w in seed_words if len(w) > 3}
    for t in (g or {}).get("titles", []):
        txt = _plain(t.get("title", ""))
        sc = t.get("score") or 0
        if not txt or len(txt) > max_len or sc < old + 4:
            continue
        low = txt.lower()
        if sw and not any(w in low for w in sw):
            continue  # drifted away from what the video is about
        if best is None or sc > best[2]:
            best = (txt, old, sc)
    return best or (title, old, old)


def demand(cands: list, n: int = 6) -> list:
    """Adds c['demand'] (0 to 100) to the first n candidates. Returns the list unchanged otherwise."""
    if not _flag("VIDIQ_TRENDS"):
        return cands
    for c in cands[:n]:
        ws = [w for w in re.findall(r"[A-Za-z0-9']+", c.get("title", "")) if len(w) > 2][:4]
        v = seed_score(" ".join(ws))
        if v is not None:
            c["demand"] = int(v)
    return cands


def check() -> list:
    out = []
    if not _env("VIDIQ_API_KEY"):
        return ["No VIDIQ_API_KEY in .env, vidIQ is off. The factory works the normal way."]
    _state["spent"] = 0
    b = call("vidiq_balance", {})
    if b is None:
        return ["vidIQ did not answer. Check VIDIQ_API_KEY and VIDIQ_URL in .env. The factory keeps working the normal way."]
    out.append("vidIQ answered. Credits: " + json.dumps(b)[:200])
    k = keywords("desi cartoon comedy")
    out.append("Keyword test: " + (", ".join(r["keyword"] for r in (k or [])[:4]) or "no rows"))
    t = better_title("Golu ne maangi cutting chai", "", ["golu", "chai"])
    out.append("Title test: " + (f"{t[1]:.0f} -> {t[2]:.0f} {t[0]}" if t else "no answer"))
    out.append("Credits used by this test: %d" % _state["spent"])
    return out
