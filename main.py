"""Autoreels factory. Run `python main.py -h` for every command."""
import argparse
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

from toon import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(config.LOGS / "factory.log", encoding="utf-8")])
for noisy in ("httpx", "googleapiclient", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


def cmd_make(a):
    from toon import pipeline
    jid = pipeline.make(a.idea or "", a.location or "", Path(a.script) if a.script else None, a.sample)
    d = pipeline.job_dir(jid)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    print(f"\nDone: {d / 'final.mp4'}\nTitle: {meta['title']}\nJob: {jid}")
    if a.upload:
        rec = pipeline.upload(jid, a.privacy)
        print("Uploaded:", rec.get("url"))
    else:
        print(f"Watch it, then: python main.py approve {jid}")


def cmd_approve(a):
    from toon import autopilot, pipeline
    when = datetime.fromisoformat(a.at) if a.at else autopilot.publish_time_for(a.job)
    rec = pipeline.upload(a.job, a.privacy, when)
    print("Uploaded:", rec.get("url"), "| publishes at", rec.get("publish_at") or "now (per privacy)")


def cmd_comments(a):
    from toon import pipeline, store
    if a.force:
        store.update(a.force, privacy="public")
    done = pipeline.post_comments()
    print("Posted on:", ", ".join(done) if done else "nothing to post (videos still private or scheduled)")
    if done:
        print("Pin them: YouTube Studio > Comments > three dots > Pin. The API cannot pin.")


def cmd_post(a):
    from toon import community
    d = community.OUT / community._now().date().isoformat()
    if a.new or a.kind or not (d / "post.txt").exists():
        d = community.make_kit(kind=a.kind)
    print((d / "post.txt").read_text(encoding="utf-8"))
    print(f"Folder: {d}")


def cmd_replies(a):
    from toon import community
    n = community.reply_round(dry=a.dry)
    st = community._load()
    if a.dry:
        for dft in st.get("drafts", [])[-n:] if n else []:
            print(f"- comment: {dft['comment'][:80]}")
            print(f"  reply:   {dft['reply']}")
    print(f"{'Drafted' if a.dry else 'Posted'} {n} replies.")


def cmd_analytics(a):
    from toon import analytics
    if a.update:
        analytics.update()
    print(analytics.report())


def cmd_telegram(a):
    from toon import telegram
    if a.action == "setup":
        print(telegram.setup())
    else:
        print("sent" if telegram.send(telegram.status_text("🧪 Test from your PC")) else "not sent: check TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")


def cmd_ig(a):
    from toon import instagram
    if a.action == "check":
        print(instagram.check())
    elif a.action == "meta-setup":
        from toon import ig_api
        print(ig_api.setup_meta())
    elif not a.job:
        print("Which job? python main.py ig post <job>   (python main.py list shows them)")
    else:
        print(instagram.post(a.job))


def cmd_trailer(a):
    from tools import trailer
    if a.publish:
        rec = trailer.publish(a.publish)
        print("Trailer live:", rec.get("url"), "| set as channel trailer:", rec.get("trailer_set"), rec.get("trailer_note", ""))
        return
    jid = trailer.make()
    d = config.OUTPUT / jid
    print(f"Trailer rendered: {d / 'trailer_16x9.mp4'} (vertical: {d / 'final.mp4'})")
    print(f"Publish: python main.py trailer --publish {jid}")


def cmd_list(a):
    from toon import store
    for jid, j in sorted(store.jobs().items()):
        print(f"{jid:55} {j.get('status', ''):10} {j.get('duration', ''):>5}s  {j.get('slot', '') or ''}  {j.get('url', '') or ''}")


def cmd_ideas(a):
    from toon import store
    used = store.used_ideas()
    for i in config.load_json("ideas.json", []):
        print(("[used] " if i["idea"] in used else "       ") + f"{i['location']:7} {i['idea']}")


def cmd_doctor(a):
    ok = True

    def line(good, what, fix=""):
        nonlocal ok
        ok &= bool(good)
        print(("  OK   " if good else "  FIX  ") + what + ("" if good else f"\n         -> {fix}"))
    print("Autoreels doctor")
    line(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg on PATH", "winget install Gyan.FFmpeg")
    if config.LLM_PROVIDER == "anthropic":
        line(bool(config.ANTHROPIC_API_KEY), f"Claude key for {config.ANTHROPIC_MODEL}", "set ANTHROPIC_API_KEY in .env")
    else:
        try:
            import ollama
            names = [m.model for m in ollama.Client(host=config.OLLAMA_HOST).list().models]
            line(any(n.startswith(config.OLLAMA_MODEL) for n in names), f"Ollama model {config.OLLAMA_MODEL}", f"ollama pull {config.OLLAMA_MODEL}")
        except Exception as e:
            line(False, "Ollama running", f"start Ollama ({str(e)[:80]})")
    line(bool(config.ELEVEN_API_KEY) or config.TTS_ENGINE == "edge", "ElevenLabs key (else free Edge voices are used)",
         "set ELEVEN_API_KEY in .env, or TTS_ENGINE=edge")
    if config.ELEVEN_API_KEY:
        import requests
        try:
            r = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": config.ELEVEN_API_KEY}, timeout=15)
            js = r.json() if r.ok else {}
            line(r.ok, f"ElevenLabs answers ({js.get('character_count', '?')}/{js.get('character_limit', '?')} characters used)",
                 f"HTTP {r.status_code}: check the key")
            for who, c in config.CAST.items():
                rv = requests.get(f"https://api.elevenlabs.io/v1/voices/{c['eleven_voice']}", headers={"xi-api-key": config.ELEVEN_API_KEY}, timeout=15)
                good = rv.ok
                if not good:  # library voices are not listed under My Voices but can still speak: try one word
                    from toon import tts
                    try:
                        tts._eleven("हाँ", c["eleven_voice"], config.CACHE / "doctor_probe.mp3")
                        good = True
                    except Exception:
                        pass
                line(good, f"voice for {c['name']}: {c['eleven_voice_name']}",
                     "add it to My Voices in the ElevenLabs Voice Library (search the name), or put another voice id in data/cast.json")
        except Exception as e:
            line(False, "ElevenLabs reachable", str(e)[:100])
    from toon import vidiq
    if vidiq.enabled():
        b = vidiq.call("vidiq_balance", {})  # free call
        line(b is not None, f"vidIQ ({(b or {}).get('totalCredits', '?')} credits)", "check VIDIQ_API_KEY")
    else:
        print("  ..   vidIQ off (optional): no VIDIQ_API_KEY")
    line(config.CLIENT_SECRET.exists(), "YouTube client_secret.json", "README: YouTube setup (Google Cloud OAuth desktop client)")
    line(config.TOKEN_FILE.exists(), "YouTube sign in (token.json)", "python main.py auth")
    if config.TOKEN_FILE.exists():
        try:
            from toon import analytics
            analytics._services().reports().query(ids="channel==MINE", startDate="2026-01-01", endDate="2026-01-02", metrics="views").execute()
            line(True, "YouTube Analytics API")
        except Exception as e:
            line(False, "YouTube Analytics API", "enable 'YouTube Analytics API' in your Google Cloud project" if "accessNotConfigured" in str(e) else str(e)[:120])
    from toon import instagram, telegram
    print("  " + ("OK   " if telegram.enabled() else "..   ") + "Telegram alerts" + ("" if telegram.enabled() else " off (optional): README: Telegram"))
    print("  ..   " + instagram.check().splitlines()[0][:160])
    print("\nAll good." if ok else "\nFix the items above, then run doctor again.")


def main():
    ap = argparse.ArgumentParser(description="Autoreels: desi stickman comedy Shorts, made locally.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="make one video")
    m.add_argument("idea", nargs="?", help="episode idea (default: next unused one from data/ideas.json)")
    m.add_argument("--location", choices=["tapri", "kirana", "school", "gali", "chhat"])
    m.add_argument("--script", help="render a ready episode JSON (e.g. written by Claude) instead of asking the model")
    m.add_argument("--sample", action="store_true", help="render the built-in sample episode (no model needed)")
    m.add_argument("--upload", action="store_true")
    m.add_argument("--privacy", choices=["private", "unlisted", "public"])
    m.set_defaults(fn=cmd_make)
    p = sub.add_parser("approve", help="upload a made video (to its slot time if it has one)")
    p.add_argument("job")
    p.add_argument("--privacy", choices=["private", "unlisted", "public"])
    p.add_argument("--at", help="publish time, ISO e.g. 2026-10-19T19:30:00+05:30")
    p.set_defaults(fn=cmd_approve)
    sub.add_parser("list", help="every job").set_defaults(fn=cmd_list)
    c = sub.add_parser("comments", help="post the first comment on uploaded videos that are public now")
    c.add_argument("--force", help="post on this job even if it was uploaded private (after you published it in Studio)")
    c.set_defaults(fn=cmd_comments)
    sub.add_parser("ideas", help="the idea list").set_defaults(fn=cmd_ideas)
    sub.add_parser("doctor", help="check the setup").set_defaults(fn=cmd_doctor)
    sub.add_parser("auth", help="sign in to YouTube once").set_defaults(fn=lambda a: print(__import__("toon.youtube", fromlist=["x"]).authenticate()))
    sub.add_parser("autopilot", help="run the daily schedule forever").set_defaults(fn=lambda a: __import__("toon.autopilot", fromlist=["x"]).run_forever())
    sub.add_parser("once", help="one autopilot round, then exit (for Task Scheduler)").set_defaults(
        fn=lambda a: print(__import__("toon.autopilot", fromlist=["x"]).once()))
    s = sub.add_parser("api", help="HTTP API for n8n")
    s.add_argument("--port", type=int)
    s.set_defaults(fn=lambda a: __import__("toon.api", fromlist=["x"]).serve(a.port))
    po = sub.add_parser("post", help="today's community post kit (made if missing); --new makes a fresh one")
    po.add_argument("--new", action="store_true")
    po.add_argument("--kind", choices=["text_poll", "quiz", "image_poll", "image_post", "video_promo"])
    po.set_defaults(fn=cmd_post)
    rp = sub.add_parser("replies", help="answer new comments now (--dry only shows what it would post)")
    rp.add_argument("--dry", action="store_true")
    rp.set_defaults(fn=cmd_replies)
    an = sub.add_parser("analytics", help="YouTube Analytics report (--update reads fresh numbers)")
    an.add_argument("--update", action="store_true")
    an.set_defaults(fn=cmd_analytics)
    sub.add_parser("bot", help="run the Telegram command bot").set_defaults(fn=lambda a: __import__("toon.telegram", fromlist=["x"]).run_bot())
    tg = sub.add_parser("telegram", help="telegram setup | test")
    tg.add_argument("action", choices=["setup", "test"])
    tg.set_defaults(fn=cmd_telegram)
    ig = sub.add_parser("ig", help="instagram check | post <job>")
    ig.add_argument("action", choices=["check", "post", "meta-setup"])
    ig.add_argument("job", nargs="?")
    ig.set_defaults(fn=cmd_ig)
    t = sub.add_parser("trailer", help="render the channel trailer (data/trailer.json); --publish uploads it public and sets it")
    t.add_argument("--publish", metavar="JOB", help="upload this rendered trailer job and set it as the channel trailer")
    t.set_defaults(fn=cmd_trailer)
    sub.add_parser("branding", help="draw logo and banner into branding/").set_defaults(
        fn=lambda a: print(__import__("tools.make_branding", fromlist=["x"]).main()))
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
