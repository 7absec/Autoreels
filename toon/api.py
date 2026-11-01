"""A small HTTP API so n8n (or anything else) can drive the factory. Listens on 127.0.0.1 only; every call needs the token
from FACTORY_API_TOKEN (header 'Authorization: Bearer <token>' or '?token='). Heavy work runs one job at a time.

GET  /api/health                       is it up, which model and voice engine
GET  /api/idea                         the next unused episode idea
POST /api/make     {idea?, location?}  start a video, returns {job_id}; poll /api/job
GET  /api/job?id=JOB                   status, title, duration, url
GET  /api/jobs                         every job
POST /api/approve  {job_id, privacy?, publish_at?}   upload (publish_at: ISO time or "slot")
GET  /api/video?id=JOB                 the mp4 (for previews / email attachments)
GET  /api/thumb?id=JOB                 the thumbnail
"""
import hmac
import json
import logging
import secrets
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import autopilot, config, pipeline, provider, store, writer

log = logging.getLogger("toon.api")
HEAVY = threading.Lock()
MAX_BODY = 100_000


def ensure_token() -> str:
    """The token from .env; makes one and appends it to .env the first time."""
    if config.API_TOKEN:
        return config.API_TOKEN
    tok = secrets.token_urlsafe(32)
    env = config.ROOT / ".env"
    with open(env, "a", encoding="utf-8") as f:
        f.write(f"\nFACTORY_API_TOKEN={tok}\n")
    config.API_TOKEN = tok
    print(f"New API token written to .env: FACTORY_API_TOKEN={tok}")
    return tok


def _bg(name, fn):
    def run():
        with HEAVY:
            try:
                fn()
            except Exception as e:
                log.exception("%s failed: %s", name, e)
    threading.Thread(target=run, name=name, daemon=True).start()


def do_make(body: dict) -> dict:
    idea, loc = str(body.get("idea", ""))[:300], str(body.get("location", ""))[:20]
    ticket = "pending-" + secrets.token_hex(4)
    store.update(ticket, status="queued", idea=idea)

    def work():
        store.update(ticket, status="writing")
        try:
            jid = pipeline.make(idea, loc)
            store.update(ticket, status="done", job_id=jid)
        except Exception as e:
            store.update(ticket, status="failed", error=str(e)[:300])
            raise
    _bg("make", work)
    return {"ticket": ticket, "poll": f"/api/job?id={ticket}"}


def do_approve(body: dict) -> dict:
    jid = str(body.get("job_id", ""))
    pipeline.job_dir(jid)  # validates the id
    privacy = body.get("privacy") or None
    if privacy not in (None, "private", "unlisted", "public"):
        raise ValueError("privacy must be private, unlisted or public")
    at = body.get("publish_at")
    when = autopilot.publish_time_for(jid) if at == "slot" else (datetime.fromisoformat(at) if at else None)
    store.update(jid, status="uploading")
    _bg("upload", lambda: pipeline.upload(jid, privacy, when))
    return {"job_id": jid, "status": "uploading", "publish_at": when.isoformat() if when else None}


class Handler(BaseHTTPRequestHandler):
    server_version = "Autoreels/1"

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)

    def _send(self, code, obj=None, raw=None, ctype="application/json"):
        data = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authed(self, q) -> bool:
        got = (self.headers.get("Authorization", "").removeprefix("Bearer ").strip() or (q.get("token") or [""])[0])
        return bool(config.API_TOKEN) and hmac.compare_digest(got.encode(), config.API_TOKEN.encode())

    def _route(self, method):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._authed(q):
            return self._send(401, {"error": "token required"})
        body = {}
        if method == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._send(413, {"error": "body too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
        p = u.path.rstrip("/")
        try:
            if p == "/api/health":
                return self._send(200, {"ok": True, "model": provider.describe(), "voice": config.TTS_ENGINE,
                                        "busy": HEAVY.locked(), "review": config.REVIEW_MODE})
            if p == "/api/idea":
                return self._send(200, writer.pick_idea(store.used_ideas()))
            if p == "/api/make" and method == "POST":
                return self._send(202, do_make(body))
            if p == "/api/job":
                jid = (q.get("id") or [""])[0]
                j = store.job(jid)
                return self._send(200 if j else 404, {"id": jid, **j} if j else {"error": "no such job"})
            if p == "/api/jobs":
                return self._send(200, store.jobs())
            if p == "/api/approve" and method == "POST":
                return self._send(202, do_approve(body))
            if p in ("/api/video", "/api/thumb"):
                d = pipeline.job_dir((q.get("id") or [""])[0])
                f = d / ("final.mp4" if p == "/api/video" else "thumb.jpg")
                if not f.exists():
                    return self._send(404, {"error": "not rendered yet"})
                return self._send(200, raw=f.read_bytes(), ctype="video/mp4" if f.suffix == ".mp4" else "image/jpeg")
            return self._send(404, {"error": "unknown endpoint"})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:
            log.exception("api error")
            return self._send(500, {"error": str(e)[:300]})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


def serve(port: int = None, host: str = "127.0.0.1"):
    ensure_token()
    port = port or config.API_PORT
    print(f"Autoreels API on http://{host}:{port}  (token in .env as FACTORY_API_TOKEN)")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
