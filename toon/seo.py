"""SEO for every upload: title, description, tags, the first comment and Hindi captions.

Built on research from 2026-10-18 (data/keywords.json, docs/SEO_RESEARCH.md):
  * The top 40 Hindi cartoon comedy Shorts of the last 60 days (median 6.6M views) use a short Hinglish hook with an emoji,
    then a keyword phrase: "Alarm Ka Badla 😂⏰ | Funny Cartoon Short". 27 of 40 put a topic hashtag in the title.
  * vidIQ scores a short curiosity hook with a character name highest (73); a keyword suffix costs about 4 points but
    reaches searches like "hindi cartoon" (183K a month) and "cartoon video" (770K a month, competition 39/100).
  * Indians also search in Devanagari ("कार्टून कॉमेडी", "देसी कॉमेडी वीडियो"), so tags and the description carry both scripts.

Title = <hook, max 45 chars, a character name, one emoji> | <keyword phrase for the location or festival> #cartoon
The model writes 4 hooks; plain rules rank them and vidIQ scores the best two (VIDIQ_TITLE_CANDIDATES), the winner is used.
"""
import logging
import os
import random
import re

from . import config, provider, vidiq

log = logging.getLogger("toon.seo")
KW = config.load_json("keywords.json", {}) or {}
CANDIDATES_SCORED = int(os.getenv("VIDIQ_TITLE_CANDIDATES", "2"))
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")

# never borrow other creators' names or generic noise as tags: misleading tags break YouTube's spam policy
BLOCKED = {"shorts", "short", "viral", "trending", "tiktok", "reels", "mjo", "oggy", "cockroaches", "motu",
           "patlu", "chhota", "bheem", "doraemon", "shinchan", "chintu", "chinki", "bittu", "pagal", "babu", "bisht", "funtoo",
           "chutku", "nobita", "pokemon", "mrbeast", "top", "new", "best", "baap", "beta", "papa", "mummy", "bahu", "saas",
           "kids", "nursery", "rhymes", "hardtoonz", "titoo"}
TOPIC_WORDS = {"comedy", "funny", "cartoon", "animation", "animated", "stickman", "desi", "hindi", "jokes", "joke", "chai",
               "tapri", "school", "kirana", "gali", "masti", "skit", "dost", "dosti", "friends", "comic", "hasi", "mazedaar"}
HINGLISH = {"ka", "ki", "ke", "ne", "hai", "hain", "kya", "bhai", "nahi", "mein", "aur", "se", "ko", "toh", "wala", "wali", "kaise",
            "kyun", "kahan", "sirf", "bhi", "pe", "ho", "gaya", "gayi", "maangi", "mila", "raha", "rahi"}


def clean_tag(t: str) -> str:
    t = re.sub(r"[^a-z0-9 ऀ-ॿ]+", " ", (t or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def topical(tag: str) -> bool:
    words = set(tag.split())
    return bool(words & TOPIC_WORDS) and not (words & BLOCKED) and 3 <= len(tag) <= 30 and len(words) <= 4


def hinglish(title: str) -> bool:
    """True when a title reads as Hinglish (the channel's voice), not plain English."""
    return len(set(re.findall(r"[a-z]+", title.lower())) & HINGLISH) >= 1


def first_comment(ep: dict) -> str:
    q = (ep.get("comment") or "").strip() or "Tumhare group mein Pappu kaun hai? Usko tag karo!"
    return f"{q}\n\nRoz 3 naye episode: subah 7, dopahar 12, shaam 7 baje. Agla kissa kahan ho: tapri, school, kirana, gali ya chhat?"


# ======================================================================= keyword phrase
def _episode_text(ep: dict) -> str:
    return " ".join([ep.get("title", ""), ep.get("hook", ""), ep.get("description", "")] + [l["caption"] for l in ep["lines"]]).lower()


def keyword_phrase(ep: dict) -> str:
    """The searched phrase this video targets: a festival or season when the episode is about one, else the location's phrase."""
    text = _episode_text(ep)
    for word, phrase in (KW.get("seasons") or {}).items():
        if re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", text):
            return phrase
    options = (KW.get("phrases") or {}).get(ep.get("location"), []) or (KW.get("phrases") or {}).get("default", ["Funny Hindi Cartoon"])
    from . import analytics  # phrases that bring search views get picked more often once there is data
    w = [analytics.weight("by_keyword", o, "search_share") for o in options]
    return random.Random(ep.get("title", "")).choices(options, weights=w)[0]  # stable per episode, varied across episodes


# ======================================================================= title
HOOK_SCHEMA = {"type": "object", "properties": {"hooks": {"type": "array", "minItems": 3, "maxItems": 5, "items": {"type": "string"}}},
               "required": ["hooks"]}


def write_hooks(ep: dict) -> list:
    lines = "\n".join(f"{l['who']}: {l['caption']}" for l in ep["lines"])
    system = ("You write YouTube Shorts title hooks for Tapri Gang, a Hindi desi stickman comedy (Pappu, Golu, Chhotu). "
              "Rules: Hinglish in Roman script, at most 45 characters, include one character name, end with exactly one fitting emoji. "
              "Best patterns: a curiosity question ('Golu ka Lunch Break toot gaya?'), a ridiculous claim ('Pappu ne becha gaddha!'), "
              "a 'X ka Y' twist ('Chhotu ka Diwali Hisaab'). Do not reveal the punchline, no clickbait lies, no hashtags, no ALL CAPS. "
              "Return JSON only.")
    from . import analytics
    notes = analytics.writer_notes()
    user = (f"Episode title draft: {ep['title']}\nScript:\n{lines}\n"
            + (f"\nWhat our viewers liked so far:\n{notes}\n" if notes else "") + "\nWrite 4 different hooks.")
    try:
        hooks = provider.chat_json(system, user, HOOK_SCHEMA, temperature=0.9).get("hooks", [])
    except Exception as e:
        log.warning("hook writing failed (%s), using the episode title", e)
        hooks = []
    hooks = [re.sub(r"#\w+", "", re.sub(r"\s+", " ", h)).strip() for h in hooks if isinstance(h, str)]
    return [h for h in hooks if 8 <= len(h) <= 60] or [ep["title"]]


def rule_score(hook: str, ep: dict) -> float:
    """Plain checks that predict a good Shorts hook, 0 to 100."""
    s = 50.0
    n = len(hook)
    s += 15 if 18 <= n <= 45 else (-10 if n > 55 else 0)
    if any(config.CAST[w]["name"].lower() in hook.lower() for w in config.CAST):
        s += 10
    if "?" in hook:
        s += 8
    s += 5 if EMOJI.search(hook) else -5
    if hinglish(hook):
        s += 7
    if re.search(r"[A-Z]{5,}", hook):
        s -= 10
    punch = ep["lines"][-1]["caption"].lower()
    if len(set(re.findall(r"[a-z]{5,}", hook.lower())) & set(re.findall(r"[a-z]{5,}", punch))) >= 2:
        s -= 10  # gives the punchline away
    return s


def pick_title(ep: dict) -> dict:
    phrase = keyword_phrase(ep)
    hooks = write_hooks(ep)
    if ep["title"] not in hooks:
        hooks.append(ep["title"])
    ranked = sorted(hooks, key=lambda h: -rule_score(h, ep))
    scores = {}
    for h in ranked[:CANDIDATES_SCORED]:
        try:
            r = vidiq.call("vidiq_score_title", {"title": f"{h} | {phrase}", "type": "short"})
            if r and "score" in r:
                scores[h] = float(r["score"])
        except Exception as e:
            log.warning("vidIQ title score skipped: %s", e)
    best = max(scores, key=scores.get) if scores else ranked[0]
    if not EMOJI.search(best):
        best += " 😂"
    title = f"{best} | {phrase} #cartoon"
    if len(title) > 100:
        title = f"{best} | {phrase}"[:100]
    return {"title": title, "hook": best, "keyword": phrase, "vidiq": scores, "candidates": ranked}


# ======================================================================= description and tags
def description(ep: dict, hook: str, phrase: str) -> str:
    ch = config.CHANNEL
    names = [config.CAST[w]["name"] for w in dict.fromkeys(l["who"] for l in ep["lines"]) if w in config.CAST]
    playlist = ch.get("playlists", {}).get(ep["location"], "")
    hindi = (KW.get("hindi_tags") or ["कार्टून कॉमेडी"])[0]
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", ep.get("description", "")) if x.strip()]
    first = f"{hook} {sentences[0] if sentences else ''} {phrase} | {hindi}".replace("  ", " ")
    tags3 = ["#cartoon", "#comedy", "#TapriGang"]  # the first three hashtags show above the title
    more = ["#funnycartoon", "#hindicartoon", "#desicomedy", "#shorts"]
    body = [
        first[:160],
        "",
        " ".join(sentences[1:]),
        "",
        f"Is episode mein: {', '.join(names)} | Jagah: {playlist or ep['location']}",
        "Pappu ka jugaad, Golu ki bhookh aur Chhotu ka dimaag: Tapri Gang ki desi stickman comedy, Hindi cartoon kahani har roz.",
        "",
        (ep.get("comment") or "Comment karo: tumhare group mein Pappu kaun hai?"),
        "",
        ch.get("description_footer", ""),
        "",
        " ".join(tags3 + more),
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(body))[:4900]


def tags(ep: dict, phrase: str) -> list:
    out = []

    def add(t):
        t = clean_tag(t)
        if t and t not in out and not (set(t.split()) & BLOCKED) and t not in (KW.get("never") or []):
            out.append(t)
    add(phrase)                                  # the first tag is the exact target phrase
    for t in ep.get("tags", [])[:4]:
        add(t)
    for t in (KW.get("core_tags") or [])[:6]:
        add(t)
    for t in (KW.get("hindi_tags") or [])[:2]:
        add(t)
    add("tapri gang")
    for w in dict.fromkeys(l["who"] for l in ep["lines"]):
        add(f"{config.CAST[w]['name']} comedy")
    try:
        for t in vidiq.extra_tags("desi cartoon comedy", out, 6):
            if topical(clean_tag(t)) and len(out) < 18:
                add(t)
    except Exception:
        pass
    out = out[:18]
    while sum(len(t) + 3 for t in out) > 480:   # YouTube allows about 500 characters of tags
        out.pop()
    return out


def metadata(ep: dict) -> dict:
    t = pick_title(ep)
    log.info("title %s (keyword %s, vidIQ %s)", t["title"], t["keyword"], t["vidiq"])
    return {"title": t["title"], "description": description(ep, t["hook"], t["keyword"]), "tags": tags(ep, t["keyword"]),
            "playlist": config.CHANNEL.get("playlists", {}).get(ep["location"], ""), "comment": first_comment(ep),
            "seo": {k: t[k] for k in ("hook", "keyword", "vidiq", "candidates")}}


# ======================================================================= captions
def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def srt(ep: dict, timeline: dict, field: str = "hi") -> str:
    """Captions from the exact spoken timings: Hindi (Devanagari) by default. Uploaded captions help Search indexing."""
    out = []
    for k, (ln, c) in enumerate(zip(ep["lines"], timeline["lines"]), 1):
        out.append(f"{k}\n{_ts(c['start'])} --> {_ts(c['end'])}\n{ln[field]}\n")
    return "\n".join(out)
