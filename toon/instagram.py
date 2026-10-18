"""Instagram Reels: every Tapri Gang Short also goes to Instagram once it is live on YouTube.

IG_MODE (in .env):
  off    nothing (default)
  phone  the Reel file and its caption are sent to you on Telegram when the YouTube video goes live; share it to Instagram
         from your phone (about 20 seconds). Needs Telegram only.
  api    published by itself through Instagram's own API (an Instagram professional account, a Meta app and a token:
         docs/INSTAGRAM.md, about 20 minutes once). The token is refreshed automatically every 30 days.
Other settings: IG_HANDLE=@taprigang (in the caption), IG_MAX_PER_DAY=4.
(vidIQ can publish Reels only from a signed-in Claude chat, not from this unattended factory, so it is not used here.)

`python main.py ig check` shows the state, `python main.py ig post <job>` posts one now.
"""
import datetime as dt
import json
import logging
import os

from . import config, store

log = logging.getLogger("toon.instagram")
HASHTAGS = ["#desicomedy", "#hindicomedy", "#cartoon", "#funnyreels", "#comedyreels", "#indianfunny", "#taprigang", "#reels"]


def mode() -> str:
    return os.getenv("IG_MODE", "off").strip().lower()


def caption(jid: str) -> str:
    d = config.OUTPUT / jid
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    ep = json.loads((d / "episode.json").read_text(encoding="utf-8"))
    hook = (meta.get("seo") or {}).get("hook") or ep["title"]
    handle = os.getenv("IG_HANDLE", "@taprigang").strip()
    q = (ep.get("comment") or "Tumhare group mein Pappu kaun hai? Tag karo!").strip()
    text = "\n".join([hook.replace(" | Channel Trailer", ""), "", ep.get("description", ""), "", q, "",
                      f"Roz nayi desi comedy: follow {handle} 🫖", "", " ".join(HASHTAGS)])
    return text.replace("Shorts", "Reels").replace("shorts", "reels")[:2200]  # Instagram words, not YouTube ones


def _live(j: dict, now: dt.datetime) -> bool:
    if j.get("publish_at"):
        return dt.datetime.fromisoformat(j["publish_at"]) <= now
    return j.get("privacy") == "public"


def _done_today() -> int:
    today = dt.date.today().isoformat()
    return sum(1 for j in store.jobs().values() if (j.get("ig_posted") or j.get("ig_sent") or "").startswith(today))


def post(jid: str) -> str:
    """Posts (api) or sends (phone) one Reel now. Returns a short result."""
    from . import telegram
    j = store.job(jid)
    video = config.OUTPUT / jid / "final.mp4"
    cap = caption(jid)
    now = dt.datetime.now().isoformat(timespec="minutes")
    if mode() == "phone":
        ok = telegram.send_files([str(video)], f"📸 Instagram Reel ready: {j.get('title', '')[:80]}\n"
                                               "Share → Instagram → Reels, then paste the caption below.", kind="video")
        ok = ok and telegram.send(cap)
        if ok:
            store.update(jid, ig_sent=now)
            return "sent to Telegram"
        store.update(jid, ig_tries=j.get("ig_tries", 0) + 1, ig_error="Telegram not set up")
        return "failed: Telegram is not set up"
    if mode() == "api":
        from . import ig_api
        try:
            r = ig_api.publish(jid, video, cap)
        except Exception as e:
            store.update(jid, ig_tries=j.get("ig_tries", 0) + 1, ig_error=str(e)[:300])
            if j.get("ig_tries", 0) + 1 >= 3:
                telegram.alert_failed(f"Instagram Reel for '{j.get('title', '')}'", e)
            return f"failed: {str(e)[:200]}"
        store.update(jid, ig_posted=now, ig_url=r.get("permalink", ""))
        telegram.send(f"📸 Reel posted: {j.get('title', '')}\n{r.get('permalink', '')}")
        return "posted " + r.get("permalink", "")
    return "IG_MODE is off"


def publish_due() -> list:
    """Called every autopilot round: handles each episode that is live on YouTube and has no Reel yet."""
    if mode() not in ("phone", "api"):
        return []
    now = dt.datetime.now(dt.timezone.utc)
    cap = int(os.getenv("IG_MAX_PER_DAY", "4"))
    out = []
    for jid, j in sorted(store.jobs().items(), key=lambda kv: kv[1].get("publish_at") or ""):
        if (j.get("status") != "uploaded" or j.get("kind") == "trailer" or j.get("ig_posted") or j.get("ig_sent")
                or j.get("ig_tries", 0) >= 3 or not _live(j, now)):
            continue
        if _done_today() >= cap:
            break
        out.append((jid, post(jid)))
    return out


def check() -> str:
    m = mode()
    if m == "api":
        from . import ig_api
        return ig_api.check()
    if m == "phone":
        from . import telegram
        return "IG_MODE=phone: Reels come to you on Telegram. " + ("Telegram is set up." if telegram.enabled() else "Telegram is NOT set up yet.")
    return "IG_MODE=off: set IG_MODE=phone (via Telegram) or IG_MODE=api (docs/INSTAGRAM.md) in .env"

