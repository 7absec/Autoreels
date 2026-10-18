"""idea -> episode script (Ollama or Claude) -> review -> voices + render -> metadata -> (approve) -> YouTube."""
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from . import config, media, render, seo, store, writer

log = logging.getLogger("toon.pipeline")
MAX_WORDS = 80  # Hinglish is spoken at about 2.5 words a second: 80 words is about 32 seconds plus gaps
JOB_RE = re.compile(r"^[0-9]{8}-[0-9]{4}-[a-z0-9-]{1,40}$")
BANNED = ["saala", "kamina", "chutiya", "bhenchod", "madarchod", "harami", "gaand", "bc", "mc", "kutte ki",
          "हरामी", "कमीना", "साला", "चूतिया", "गांड", "मादर", "भेन"]
SENSITIVE = ["hindu", "muslim", "sikh", "christian", "mandir", "masjid", "caste", "jaat", "modi", "rahul gandhi", "bjp", "congress",
             "pakistan", "मोदी", "मंदिर", "मस्जिद"]


def job_dir(job_id: str) -> Path:
    if not JOB_RE.match(job_id or ""):
        raise ValueError(f"bad job id: {job_id!r}")
    return config.OUTPUT / job_id


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40].strip("-") or "episode"


def review(ep: dict) -> list:
    """Fixed rules every episode must pass. Returns the problems (empty list = fine)."""
    problems = []
    text = " ".join(l["hi"] + " " + l["caption"] for l in ep["lines"]).lower() + " " + ep["title"].lower()
    def has(w):
        return re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", text) if w.isascii() else w in text
    problems += [f"bad word: {w}" for w in BANNED if has(w)]
    problems += [f"sensitive topic: {w}" for w in SENSITIVE if has(w)]
    if not 4 <= len(ep["lines"]) <= 8:
        problems.append(f"{len(ep['lines'])} lines, want 5 to 7")
    words = sum(len(l["caption"].split()) for l in ep["lines"])
    if words > MAX_WORDS:
        problems.append(f"{words} words is longer than 35 seconds, cut to about 70 words")
    long = [l["caption"] for l in ep["lines"] if len(l["caption"].split()) > 15]
    if long:
        problems.append(f"lines too long: {long[0][:40]}")
    if ep["lines"][-1]["who"] == "pappu" and ep["lines"][-1]["fx"] != "laugh":
        problems.append("the last line should be a punchline (Chhotu or a twist)")
    return problems


def next_inbox():
    """The oldest ready episode JSON in inbox/ (written by hand or by the Claude Code skill), or None."""
    files = sorted(config.INBOX.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return files[0] if files else None


def write_episode(idea: str, location: str = "", tries: int = 3) -> dict:
    feedback = ""
    for k in range(tries):
        ep = writer.write(idea, location, feedback)
        problems = review(ep)
        if not problems:
            return ep
        feedback = "; ".join(problems)
        log.warning("draft %d rejected: %s", k + 1, feedback)
    raise RuntimeError(f"no clean episode after {tries} drafts: {feedback}")


def make(idea: str = "", location: str = "", script: Path = None, sample: bool = False) -> str:
    """Makes one finished video. Returns the job id. The job folder has episode.json, final.mp4, thumb.jpg and meta.json."""
    media.check_tools()
    if script:
        ep = writer.clean(json.loads(Path(script).read_text(encoding="utf-8")))
        idea = idea or ep["title"]
    elif sample:
        ep = writer.clean(writer.SAMPLE)
        idea = idea or "sample: cutting chai"
    elif not idea and next_inbox():
        src = next_inbox()
        ep = writer.clean(json.loads(src.read_text(encoding="utf-8")))
        problems = review(ep)
        dest = config.INBOX / ("needs-review" if problems else "done")
        dest.mkdir(exist_ok=True)
        src.replace(dest / src.name)
        if problems:
            raise RuntimeError(f"inbox episode {src.name} failed review: {'; '.join(problems)}")
        idea = "inbox: " + src.stem
    else:
        if not idea:
            pick = writer.pick_idea(store.used_ideas())
            idea, location = pick["idea"], location or pick.get("location", "")
        ep = write_episode(idea, location)
    jid = datetime.now().strftime("%Y%m%d-%H%M") + "-" + _slug(ep["title"])
    d = job_dir(jid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "episode.json").write_text(json.dumps(ep, ensure_ascii=False, indent=1), encoding="utf-8")
    store.update(jid, status="rendering", idea=idea, title=ep["title"], location=ep["location"])
    t0 = time.time()
    try:
        video = render.render(ep, d)
    except Exception as e:
        store.update(jid, status="failed", error=str(e)[:400])
        raise
    dur = media.duration(video)
    meta = seo.metadata(ep)
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    store.mark_used(idea)
    status = "approved" if config.REVIEW_MODE == "auto" else "rendered"
    store.update(jid, status=status, duration=round(dur, 1), render_seconds=round(time.time() - t0), video=str(video))
    log.info("made %s (%.1fs) in %.0fs", jid, dur, time.time() - t0)
    return jid


def upload(jid: str, privacy: str = None, publish_at: datetime = None) -> dict:
    """Uploads the job's video. With publish_at the video is private until YouTube publishes it at that time."""
    from . import youtube
    d = job_dir(jid)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    url, vid = youtube.upload(d / "final.mp4", meta["title"], meta["description"], meta["tags"], privacy, publish_at, with_id=True)
    rec = store.update(jid, status="uploaded", url=url, video_id=vid,
                       publish_at=publish_at.isoformat() if publish_at else None)
    add_captions(jid, vid)
    if (d / "thumb.jpg").exists():
        youtube.set_thumbnail(vid, d / "thumb.jpg")  # Shorts may ignore it; never fails the upload
    if meta.get("playlist"):
        pid, _ = youtube.ensure_playlist(meta["playlist"], f"{config.CHANNEL.get('name')} : {meta['playlist']}")
        if pid:
            youtube.add_to_playlist(vid, pid)
    store.update(jid, privacy=(privacy or config.YT_PRIVACY) if not publish_at else "scheduled")
    post_comments()  # posts straight away when the video is already public
    from . import telegram
    telegram.alert_uploaded(rec, meta["title"])
    return rec


def add_captions(jid: str, video_id: str) -> bool:
    """Uploads the Hindi captions (exact spoken timings) for the job's video. Never raises."""
    from . import youtube
    d = job_dir(jid)
    try:
        ep = json.loads((d / "episode.json").read_text(encoding="utf-8"))
        tl = json.loads((d / "timeline.json").read_text(encoding="utf-8"))
        ok, info = youtube.upload_captions(video_id, seo.srt(ep, tl, "hi"), "hi", "Hindi")
    except Exception as e:
        ok, info = False, str(e)[:200]
    store.update(jid, captions=ok, captions_note=info)
    if not ok:
        log.warning("captions for %s not added: %s", jid, info)
    return ok


def post_comments(max_tries: int = 6) -> list:
    """Posts the channel's first comment on every uploaded video that is public by now and has none yet.
    Private videos do not take comments, so scheduled ones are tried again on later autopilot rounds."""
    from datetime import timezone
    from . import youtube
    posted = []
    now = datetime.now(timezone.utc)
    for jid, j in store.jobs().items():
        if j.get("status") != "uploaded" or not j.get("video_id") or j.get("comment_id") or j.get("comment_tries", 0) >= max_tries:
            continue
        if j.get("publish_at"):
            if datetime.fromisoformat(j["publish_at"]) > now:
                continue
        elif j.get("privacy") == "private":
            continue  # a private upload stays private until you publish it; `python main.py comments` after that
        try:
            meta = json.loads((job_dir(jid) / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ok, info = youtube.post_comment(j["video_id"], meta.get("comment") or "Tumhare group mein Pappu kaun hai?")
        if ok:
            store.update(jid, comment_id=info)
            posted.append(jid)
            log.info("first comment posted on %s: pin it in Studio", j.get("url"))
        else:
            store.update(jid, comment_tries=j.get("comment_tries", 0) + 1, comment_error=info)
    return posted
