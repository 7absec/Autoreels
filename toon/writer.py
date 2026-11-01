"""Writes one episode: a 25 to 45 second Hindi comedy scene for Pappu, Golu and Chhotu.
Each line has Devanagari text for the voice and Hinglish (Roman script) for the on-screen caption,
plus stage directions (pose, face, prop, effect) the renderer understands."""
import json
import logging
import random
import re

from . import analytics, config, provider
from .draw import FACES, FX, POSES, PROPS
from .sets import LOCATIONS

log = logging.getLogger("toon.writer")
WHO = ["pappu", "golu", "chhotu"]

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "YouTube title in Hinglish, max 60 chars, no hashtags"},
        "hook": {"type": "string", "description": "2 to 5 word Hinglish hook shown on top of the video"},
        "location": {"type": "string", "enum": LOCATIONS},
        "lines": {
            "type": "array", "minItems": 5, "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "who": {"type": "string", "enum": WHO},
                    "hi": {"type": "string", "description": "the line in Hindi, Devanagari script, for the voice"},
                    "caption": {"type": "string", "description": "the same line in Hinglish (Roman script)"},
                    "pose": {"type": "string", "enum": POSES},
                    "face": {"type": "string", "enum": FACES},
                    "prop": {"type": "string", "enum": PROPS},
                    "fx": {"type": "string", "enum": FX},
                    "react": {"type": "string", "enum": FACES, "description": "face of the two listeners"},
                },
                "required": ["who", "hi", "caption", "pose", "face", "prop", "fx", "react"],
            },
        },
        "description": {"type": "string", "description": "2 short Hinglish sentences for the YouTube description"},
        "comment": {"type": "string", "description": "one fun Hinglish question to viewers about this episode, pinned as the first comment"},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
    },
    "required": ["title", "hook", "location", "lines", "description", "tags", "comment"],
}


def _cast_block() -> str:
    out = []
    for k in WHO:
        c = config.CAST.get(k, {})
        out.append(f"- {k} ({c.get('name', k)}): {c.get('role', '')} Catchphrase: \"{c.get('catchphrase', '')}\"")
    return "\n".join(out)


def system_prompt() -> str:
    ch = config.CHANNEL
    return f"""You write episodes of "{ch.get('name', 'Autoreels')}", a desi stickman cartoon comedy for YouTube Shorts.

THE CAST (always these three, nobody else speaks):
{_cast_block()}
Off-screen people (Mummy, Master ji, Sharma aunty, Raju bhaiya) may be mentioned but never speak.

FORMAT
- One scene, 5 to 7 lines, 20 to 35 seconds when spoken, about 70 words in total. Every line is short: at most 11 words.
  Shorter is funnier: cut every line that does not set up or land the joke.
- Line 1 is the hook: a funny problem or a ridiculous claim, said in the first 2 seconds. No greetings, no "dosto".
- Build up with 2 escalations. The LAST line is the punchline and it is Chhotu's (most of the time) or a twist.
- The video loops: the punchline should make people want to watch the hook again (a callback to line 1 is ideal).
- Natural spoken Hindi like friends talk in a north Indian city. Light English words are fine (phone, exam, WiFi).
- "hi" is Devanagari only. "caption" is the SAME line in Hinglish Roman script, the way Indians type on WhatsApp.
- Pick pose/face/prop/fx that act out the line. Use "laugh" fx or "laugh" react on the punchline.

COMEDY RULES
- Relatable everyday India: chai tapri, kirana shop, school, gali cricket, rooftops, mummy's orders, exams, UPI, power cuts.
- Clean and family friendly. No abuses, no double meaning, no religion, caste, region, politics, body shaming or real people.
- The joke comes from character: Pappu's over-confident jugaad, Golu's literal innocence and hunger, Chhotu's calm logic.

- "comment": one playful question for viewers that invites a reply, e.g. "Golu ko kaunsi chai milni chahiye?"

Return JSON only."""


def _example() -> str:
    return json.dumps(SAMPLE, ensure_ascii=False)


def write(idea: str, location: str = "", feedback: str = "") -> dict:
    """The episode as a dict, cleaned and validated. Raises if the model fails three times."""
    loc = location if location in LOCATIONS else ""
    user = (f"Episode idea: {idea}\n" + (f"Location: {loc}\n" if loc else "") +
            f"\nExample of the exact format (a different episode, do not copy its jokes):\n{_example()}\n" +
            (f"\nThe previous draft was rejected because: {feedback}\nFix that.\n" if feedback else "") +
            (f"\nWhat our viewers liked so far (learn from it, do not copy):\n{notes}\n" if (notes := analytics.writer_notes()) else "") +
            "\nWrite the new episode now.")
    raw = provider.chat_json(system_prompt(), user, SCHEMA, temperature=0.9)
    return clean(raw, loc or "tapri")


_DEVA = re.compile(r"[ऀ-ॿ]")


def clean(raw: dict, default_loc: str = "tapri") -> dict:
    """Keeps the model's answer inside what the renderer can draw. Raises ValueError when it is unusable."""
    lines = []
    for ln in raw.get("lines") or []:
        if not isinstance(ln, dict):
            continue
        who = str(ln.get("who", "")).lower().strip()
        hi = str(ln.get("hi", "")).strip()
        cap = re.sub(r"\s+", " ", str(ln.get("caption", "")).strip())
        if who not in WHO or not hi or not cap:
            continue
        if not _DEVA.search(hi):
            hi = cap  # the voice can read Hinglish too, just less naturally
        if _DEVA.search(cap):
            continue  # captions must be Roman script: the caption font cannot shape Devanagari
        lines.append({
            "who": who, "hi": hi[:220], "caption": cap[:110],
            "pose": ln.get("pose") if ln.get("pose") in POSES else "talk",
            "face": ln.get("face") if ln.get("face") in FACES else "neutral",
            "prop": ln.get("prop") if ln.get("prop") in PROPS else "none",
            "fx": ln.get("fx") if ln.get("fx") in FX else "none",
            "react": ln.get("react") if ln.get("react") in FACES else "neutral",
        })
    if len(lines) < 4:
        raise ValueError(f"only {len(lines)} usable lines")
    if len({l["who"] for l in lines}) < 2:
        raise ValueError("fewer than two characters speak")
    lines = lines[:8]
    title = re.sub(r"#\w+", "", str(raw.get("title", ""))).strip()[:70] or lines[0]["caption"][:60]
    hook = str(raw.get("hook", "")).strip()[:40] or title[:30]
    loc = raw.get("location") if raw.get("location") in LOCATIONS else default_loc
    tags = [str(t).strip().lower().lstrip("#") for t in (raw.get("tags") or []) if str(t).strip()][:12]
    return {"title": title, "hook": hook, "location": loc, "lines": lines,
            "description": str(raw.get("description", "")).strip()[:600], "tags": tags,
            "comment": re.sub(r"\s+", " ", str(raw.get("comment", ""))).strip()[:300]}


def pick_idea(used: set) -> dict:
    """A random unused idea from data/ideas.json. When all were used, the model invents a new one (saved to the list)."""
    ideas = config.load_json("ideas.json", []) or []
    fresh = [i for i in ideas if i["idea"] not in used]
    if fresh:
        from . import analytics  # locations that hold viewers come up more often once there is data
        return random.choices(fresh, weights=[analytics.weight("by_location", i.get("location", ""), "view_pct") for i in fresh])[0]
    try:
        new = invent_idea([i["idea"] for i in ideas])
        ideas.append(new)
        (config.DATA / "ideas.json").write_text(json.dumps(ideas, ensure_ascii=False, indent=1), encoding="utf-8")
        return new
    except Exception as e:
        log.warning("could not invent a new idea (%s), reusing an old one", e)
        return random.choice(ideas or [{"location": "tapri", "idea": "Golu orders a cutting chai"}])


IDEA_SCHEMA = {"type": "object", "properties": {"location": {"type": "string", "enum": LOCATIONS},
                                                 "idea": {"type": "string", "description": "one sentence episode idea"}},
               "required": ["location", "idea"]}


def invent_idea(done: list) -> dict:
    """One fresh everyday-India situation for the cast that is not one of the ideas already done."""
    month = __import__("datetime").date.today().strftime("%B")
    user = (f"It is {month} in India. Invent ONE new episode idea for Pappu, Golu and Chhotu: a small, relatable everyday situation "
            "(season, festivals, exams, cricket, monsoon, shopping, family orders, school) with a clear comic premise.\n"
            "It must be different from all of these:\n- " + "\n- ".join(done[-80:]))
    got = provider.chat_json(system_prompt(), user, IDEA_SCHEMA, temperature=1.0)
    idea = str(got.get("idea", "")).strip()
    if len(idea) < 15:
        raise ValueError("idea too short")
    return {"location": got.get("location") if got.get("location") in LOCATIONS else random.choice(LOCATIONS), "idea": idea[:400]}


# A hand written episode: the format example for the model and the offline test script.
SAMPLE = {
    "title": "Golu ne maangi Cutting Chai... kainchi kahan hai?",
    "hook": "Cutting chai ka raaz",
    "location": "tapri",
    "lines": [
        {"who": "golu", "hi": "छोटू, एक कटिंग चाय देना... पर कैंची कहाँ है?", "caption": "Chhotu, ek cutting chai dena... par kainchi kahan hai?",
         "pose": "talk", "face": "confused", "prop": "none", "fx": "question", "react": "shocked"},
        {"who": "pappu", "hi": "अरे गोलू, कैंची से नहीं काटते! ये तो जुगाड़ है।", "caption": "Arre Golu, kainchi se nahi kaatte! Ye toh jugaad hai.",
         "pose": "point", "face": "smug", "prop": "none", "fx": "none", "react": "confused"},
        {"who": "golu", "hi": "तो फिर चाय आधी कैसे होती है?", "caption": "Toh phir chai aadhi kaise hoti hai?",
         "pose": "shrug", "face": "worried", "prop": "none", "fx": "sweat", "react": "neutral"},
        {"who": "pappu", "hi": "सिंपल! राजू भैया आधी चाय पीकर बाकी हमें दे देते हैं।", "caption": "Simple! Raju bhaiya aadhi chai peekar baaki humein de dete hain.",
         "pose": "talk", "face": "happy", "prop": "chai", "fx": "idea", "react": "shocked"},
        {"who": "golu", "hi": "छी! मुझे पूरी चाय चाहिए, दो कटिंग जोड़ के!", "caption": "Chhee! Mujhe poori chai chahiye, do cutting jod ke!",
         "pose": "panic", "face": "shocked", "prop": "none", "fx": "exclaim", "react": "laugh"},
        {"who": "chhotu", "hi": "भैया, दो कटिंग जोड़ोगे तो बीस रुपये। पूरी चाय पंद्रह की।", "caption": "Bhaiya, do cutting jodoge toh bees rupaye. Poori chai pandrah ki.",
         "pose": "hips", "face": "smug", "prop": "kettle", "fx": "none", "react": "shocked"},
        {"who": "pappu", "hi": "अरे वाह, फिर तो मैं रोज़ पूरी चाय पिऊँगा... उधार पे!", "caption": "Arre waah, phir toh main roz poori chai piyunga... udhaar pe!",
         "pose": "cheer", "face": "laugh", "prop": "none", "fx": "none", "react": "angry"},
        {"who": "chhotu", "hi": "उधार वाले को चाय नहीं, सिर्फ भाप मिलती है!", "caption": "Udhaar waale ko chai nahi, sirf bhaap milti hai!",
         "pose": "point", "face": "smug", "prop": "kettle", "fx": "laugh", "react": "laugh"},
    ],
    "description": "Golu ko lagta hai cutting chai kainchi se kati jaati hai. Pappu ka jugaad aur Chhotu ka hisaab, dono garam!",
    "tags": ["cutting chai", "chai tapri comedy", "desi comedy", "cartoon comedy", "golu", "pappu", "chhotu"],
    "comment": "Tum cutting chai lete ho ya poori? Aur udhaar wala dost kaun hai, tag karo!",
}
