"""Fully local daily automation. Every 20 minutes: for each publishing slot today and tomorrow (SLOTS, India time)
that has no video yet, make one. REVIEW_MODE=auto uploads it straight away with that publish time (YouTube then
publishes it by itself, even when this PC is off). REVIEW_MODE=hold leaves it for `python main.py approve <job>`."""
import logging
import time
import zlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, pipeline, store

log = logging.getLogger("toon.autopilot")
LEAD = timedelta(minutes=90)  # never schedule closer than this to now


def slot_time(day, spec: str, tz) -> datetime:
    """'19:30' is an exact time. '19:00-19:30' is a window: a minute inside it is picked per day (the same minute every time
    it is asked, so the slot keeps its identity), which keeps posting times from looking robotic."""
    a, _, b = spec.partition("-")
    h1, m1 = (int(x) for x in a.strip().split(":"))
    start = datetime(day.year, day.month, day.day, h1, m1, tzinfo=tz)
    if not b:
        return start
    h2, m2 = (int(x) for x in b.strip().split(":"))
    span = max(0, (h2 * 60 + m2) - (h1 * 60 + m1))
    pick = zlib.crc32(f"{day.isoformat()}|{spec}".encode()) % (span + 1)
    return start + timedelta(minutes=pick)


def slots(now: datetime) -> list:
    tz = ZoneInfo(config.TZ_NAME)
    out = []
    for day in (0, 1):
        d = (now + timedelta(days=day)).date()
        out += [slot_time(d, s, tz) for s in config.SLOTS]
    return [s for s in out if s - now >= LEAD]


def filled() -> set:
    return {j.get("slot") for j in store.jobs().values() if j.get("slot") and j.get("status") not in ("failed",)}


def _safe(name, fn):
    try:
        return fn()
    except Exception as e:  # one side job failing never stops the round
        log.warning("%s failed: %s", name, str(e)[:200])
        return None


def _morning(now: datetime):
    """The Telegram morning summary, once a day after 06:30."""
    from . import telegram
    flag = config.DATA / "tg_morning.txt"
    today = now.date().isoformat()
    if now.hour * 60 + now.minute >= 390 and (not flag.exists() or flag.read_text() != today):
        telegram.morning_summary()
        flag.write_text(today)


def once() -> list:
    from . import analytics, community, instagram, telegram
    now = datetime.now(ZoneInfo(config.TZ_NAME))
    _safe("first comments", pipeline.post_comments)
    retry_uploads(now)
    log.info("community: %s", _safe("community", community.round_))
    _safe("instagram", instagram.publish_due)
    if now.hour >= 10 and analytics.due():
        _safe("analytics", analytics.update)
    _safe("morning summary", lambda: _morning(now))
    if telegram.PAUSE_FLAG.exists():
        log.info("paused from Telegram: no new videos this round")
        return []
    done = []
    have = filled()
    for s in slots(now):
        key = s.isoformat()
        if key in have:
            continue
        queued = [jid for jid, j in sorted(store.jobs().items()) if j.get("queued") and not j.get("slot") and j.get("status") in ("rendered", "approved")]
        if queued:  # a video made from Telegram (/make) takes the next free slot
            jid = queued[0]
            log.info("queued video %s takes the slot %s", jid, key)
        else:
            log.info("making a video for %s", key)
            try:
                jid = pipeline.make()
            except Exception as e:
                log.error("could not make a video for %s: %s", key, e)
                telegram.alert_failed(f"Making the video for {s.strftime('%a %I:%M %p')}", e)
                continue
        store.update(jid, slot=key)
        if config.REVIEW_MODE == "auto":
            try:
                pipeline.upload(jid, publish_at=s)
            except Exception as e:
                log.error("upload of %s failed: %s", jid, e)
                store.update(jid, status="upload_failed", error=str(e)[:300])
                if "uploadLimitExceeded" not in str(e):
                    telegram.alert_failed(f"Uploading '{store.job(jid).get('title', '')}'", e)
        done.append(jid)
        have.add(key)
    return done


def retry_uploads(now: datetime) -> list:
    """Uploads made videos whose slot is still ahead but that are not on YouTube yet (for example after YouTube's daily
    upload limit). Stops for this round at the first limit error."""
    done = []
    for jid, j in sorted(store.jobs().items(), key=lambda kv: kv[1].get("slot") or ""):
        if not j.get("slot") or j.get("video_id") or j.get("status") not in ("rendered", "approved", "upload_failed"):
            continue
        if j.get("status") == "rendered" and config.REVIEW_MODE != "auto" and not j.get("approved"):
            continue
        slot = datetime.fromisoformat(j["slot"])
        if slot - now < timedelta(minutes=20):
            continue
        try:
            pipeline.upload(jid, publish_at=slot)
            done.append(jid)
        except Exception as e:
            store.update(jid, status="upload_failed", error=str(e)[:300])
            if "uploadLimitExceeded" in str(e) or "quota" in str(e).lower():
                log.warning("YouTube upload limit reached, will retry next round")
                break
            log.error("retry upload of %s failed: %s", jid, e)
    return done


def run_forever(every_min: int = 20):
    log.info("autopilot started, slots %s %s, review %s", ",".join(config.SLOTS), config.TZ_NAME, config.REVIEW_MODE)
    while True:
        try:
            once()
        except Exception as e:  # never die: log and try again next round
            log.exception("autopilot round failed: %s", e)
        time.sleep(every_min * 60)


def publish_time_for(jid: str):
    """The slot the job was made for, or 30 minutes from now if that slot already passed."""
    tz = ZoneInfo(config.TZ_NAME)
    now = datetime.now(tz)
    s = store.job(jid).get("slot")
    if s:
        t = datetime.fromisoformat(s)
        if t - now > timedelta(minutes=20):
            return t
    return None
