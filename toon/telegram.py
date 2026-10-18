"""Telegram: alerts to your phone and a few commands back.

Alerts (sent by the autopilot): every scheduled upload, every failure, the 9 PM community post kit (text + images, ready to
copy into the YouTube app), a morning summary of today's schedule, and Instagram Reels posted.

Commands (the bot process, `python main.py bot`, started at sign in by install_autostart.ps1). Only your chat is answered:
  /status        what is scheduled, anything failed, paused or not
  /post          today's community post kit
  /make <idea>   render an episode now; it gets the next free slot (preview sent to you first)
  /pause /resume stop or restart making new videos (scheduled ones still publish)
  /stats         the analytics report
  /help

Setup: create a bot with @BotFather, put TELEGRAM_BOT_TOKEN in .env, send any message to the bot, then run
`python main.py telegram setup` (it finds your chat id and saves it).
"""
import datetime as dt
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

import requests

from . import config

log = logging.getLogger("toon.telegram")
API = "https://api.telegram.org/bot{token}/{method}"
PAUSE_FLAG = config.DATA / "paused"


def _token():
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _chat():
    return os.getenv("TELEGRAM_CHAT_ID", "").strip()


def enabled() -> bool:
    return bool(_token() and _chat())


def _call(method: str, data: dict = None, files: dict = None, timeout: int = 60) -> dict:
    r = requests.post(API.format(token=_token(), method=method), data=data or {}, files=files, timeout=timeout)
    js = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"ok": False, "description": r.text[:200]}
    if not js.get("ok"):
        raise RuntimeError(f"Telegram {method}: {js.get('description')}")
    return js["result"]


def send(text: str, chat: str = None) -> bool:
    """Never raises: an alert that fails must not stop the factory."""
    if not _token() or not (chat or _chat()):
        return False
    try:
        for i in range(0, len(text), 3900):
            _call("sendMessage", {"chat_id": chat or _chat(), "text": text[i:i + 3900], "disable_web_page_preview": "true"})
        return True
    except Exception as e:
        log.warning("telegram send failed: %s", str(e)[:150])
        return False


def send_files(paths: list, caption: str = "", chat: str = None, kind: str = "photo") -> bool:
    if not _token() or not (chat or _chat()) or not paths:
        return False
    try:
        if len(paths) == 1 or kind == "video":
            for k, p in enumerate(paths):
                method, field = ("sendVideo", "video") if kind == "video" else ("sendPhoto", "photo")
                with open(p, "rb") as f:
                    _call(method, {"chat_id": chat or _chat(), "caption": caption[:1000] if k == 0 else ""}, {field: f}, timeout=300)
            return True
        media, files = [], {}
        for k, p in enumerate(paths[:10]):
            media.append({"type": "photo", "media": f"attach://f{k}", **({"caption": caption[:1000]} if k == 0 else {})})
            files[f"f{k}"] = open(p, "rb")
        try:
            _call("sendMediaGroup", {"chat_id": chat or _chat(), "media": json.dumps(media)}, files, timeout=300)
        finally:
            for f in files.values():
                f.close()
        return True
    except Exception as e:
        log.warning("telegram file send failed: %s", str(e)[:150])
        return False


# ======================================================================= alerts used by the factory
def alert_uploaded(rec: dict, title: str):
    when = rec.get("publish_at")
    t = dt.datetime.fromisoformat(when).astimezone().strftime("%a %d %b %I:%M %p") if when else "now"
    send(f"✅ Scheduled: {title}\nGoes live: {t}\n{rec.get('url', '')}")


def alert_failed(what: str, err: str):
    send(f"⚠️ {what} failed\n{str(err)[:500]}")


def send_post_kit(folder: Path):
    p = json.loads((folder / "post.json").read_text(encoding="utf-8"))
    imgs = sorted(str(x) for x in folder.glob("*.jpg"))
    kind = p["kind"].replace("_", " ")
    head = f"📣 Community post time ({kind})\nYouTube app → Create → Post\n\n"
    text = p["text"] + (f"\n{p['link']}" if p.get("link") else "")
    opts = "\n".join(f"{i + 1}. {o}" + (" ✔" if p["kind"] == "quiz" and i == p.get("correct") else "") for i, o in enumerate(p.get("options", [])))
    send(head + "Text (long-press to copy) 👇")
    send(text)
    if opts:
        send("Options:\n" + opts + (f"\n\nExplanation: {p['explanation']}" if p["kind"] == "quiz" and p.get("explanation") else ""))
    if imgs:
        send_files(imgs, "Images for the post (save and attach)")


def morning_summary():
    send(status_text(header="☀️ Good morning! Today on Tapri Gang:"))


# ======================================================================= commands
def status_text(header: str = "📋 Tapri Gang status") -> str:
    from zoneinfo import ZoneInfo
    from . import store
    tz = ZoneInfo(config.TZ_NAME)
    now = dt.datetime.now(tz)
    rows, failed = [], []
    for jid, j in store.jobs().items():
        if j.get("slot") and dt.datetime.fromisoformat(j["slot"]) > now - dt.timedelta(hours=1):
            rows.append((j["slot"], j))
        if j.get("status") in ("failed", "upload_failed") and j.get("slot") and dt.datetime.fromisoformat(j["slot"]) > now:
            failed.append(j)
    lines = [header, f"Autopilot: {'⏸ PAUSED' if PAUSE_FLAG.exists() else '▶️ running'}", ""]
    for slot, j in sorted(rows, key=lambda r: r[0]):
        t = dt.datetime.fromisoformat(slot).astimezone(tz).strftime("%a %I:%M %p")
        mark = {"uploaded": "✅", "upload_failed": "⏳ waiting to upload", "failed": "❌"}.get(j.get("status"), j.get("status", ""))
        lines.append(f"{t}  {mark}  {j.get('title', '')[:60]}")
    if not rows:
        lines.append("Nothing scheduled yet.")
    if failed:
        lines += ["", f"⚠️ {len(failed)} need attention: " + ", ".join(f.get("title", "")[:30] for f in failed)]
    return "\n".join(lines)


def _make_job(idea: str, chat: str):
    from . import pipeline, store
    send(f"🎬 Making: {idea}\nAbout 2 minutes…", chat)
    try:
        jid = pipeline.make(idea)
        store.update(jid, queued=True)  # the autopilot gives it the next free slot
        d = pipeline.job_dir(jid)
        title = json.loads((d / "meta.json").read_text(encoding="utf-8"))["title"]
        send_files([str(d / "final.mp4")], f"{title}\n\nIt takes the next free slot. Send /status to see when.", chat, kind="video")
    except Exception as e:
        send(f"❌ Could not make it: {str(e)[:300]}", chat)


def handle(text: str, chat: str):
    cmd, _, arg = text.strip().partition(" ")
    cmd = cmd.lower().split("@")[0]
    if cmd in ("/start", "/help"):
        send(__doc__.split("Commands")[1].split("Setup:")[0].strip(), chat)
    elif cmd == "/status":
        send(status_text(), chat)
    elif cmd == "/post":
        from . import community
        d = community.OUT / community._now().date().isoformat()
        if not (d / "post.json").exists():
            d = community.make_kit()
        send_post_kit(d)
    elif cmd == "/make":
        if not arg.strip():
            send("Tell me the idea: /make Golu ki Diwali shopping", chat)
        else:
            threading.Thread(target=_make_job, args=(arg.strip()[:300], chat), daemon=True).start()
    elif cmd == "/pause":
        PAUSE_FLAG.write_text(dt.datetime.now().isoformat(), encoding="utf-8")
        send("⏸ Paused: no new videos will be made. Already scheduled ones still go live. /resume to restart.", chat)
    elif cmd == "/resume":
        PAUSE_FLAG.unlink(missing_ok=True)
        send("▶️ Resumed.", chat)
    elif cmd == "/stats":
        from . import analytics
        send(analytics.report(), chat)
    else:
        send("I know /status /post /make /pause /resume /stats /help", chat)


def run_bot():
    """Long-polls Telegram for commands. Answers only TELEGRAM_CHAT_ID."""
    from dotenv import load_dotenv
    while not enabled():  # started at sign in before setup: wait for the token and chat id to appear in .env
        time.sleep(300)
        load_dotenv(config.ROOT / ".env", override=True)
    log.info("telegram bot listening")
    offset = None
    while True:
        try:
            ups = _call("getUpdates", {"timeout": 50, **({"offset": offset} if offset else {})}, timeout=70)
            for u in ups:
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                chat = str((msg.get("chat") or {}).get("id", ""))
                if chat != _chat():
                    continue  # strangers are ignored
                if msg.get("text", "").startswith("/"):
                    handle(msg["text"], chat)
        except Exception as e:
            log.warning("telegram poll: %s", str(e)[:150])
            time.sleep(15)


def setup() -> str:
    """Finds the chat id of whoever messaged the bot last and saves it to .env."""
    if not _token():
        return "Put TELEGRAM_BOT_TOKEN=... in .env first (from @BotFather)."
    ups = _call("getUpdates", {"timeout": 0})
    chats = [u["message"]["chat"] for u in ups if u.get("message")]
    if not chats:
        return "No messages found. Open your bot in Telegram, press Start (or send 'hi'), then run this again."
    chat = chats[-1]
    env = config.ROOT / ".env"
    text = env.read_text(encoding="utf-8")
    line = f"TELEGRAM_CHAT_ID={chat['id']}"
    text = re.sub(r"^TELEGRAM_CHAT_ID=.*$", line, text, flags=re.M) if re.search(r"^TELEGRAM_CHAT_ID=", text, flags=re.M) else text + f"\n{line}\n"
    env.write_text(text, encoding="utf-8")
    os.environ["TELEGRAM_CHAT_ID"] = str(chat["id"])
    send("🎉 Tapri Gang alerts are connected. Send /help for commands.")
    return f"Saved chat {chat.get('first_name', '')} ({chat['id']}). A test message was sent."
