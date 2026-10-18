"""Instagram Graph API publishing (Instagram Login), ported from shorts_factory_v8/shorts/instagram.py.
Sends the Reel file itself; when Instagram asks for a link instead, serves the file for a minute through a free Cloudflare quick
tunnel (cloudflared). Setup steps: docs/INSTAGRAM.md. Used when IG_MODE=api."""
import contextlib
import http.server
import json
import logging
import os
import re
import secrets
import shutil
import socket
import socketserver
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config

log = logging.getLogger("toon.ig_api")
TOKEN_FILE = config.ROOT / "ig_token.json"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _num(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def mode() -> str:
    return _env("IG_MODE", "off").lower()


def reels_dir() -> Path:
    p = config.CACHE / "ig"
    p.mkdir(parents=True, exist_ok=True)
    return p


class IGError(RuntimeError):
    def __init__(self, message, code=None, subcode=None, status=None):
        super().__init__(message)
        self.code, self.subcode, self.status = code, subcode, status


def _token() -> str:
    try:
        t = json.loads(TOKEN_FILE.read_text(encoding="utf-8")).get("token")
        if t:
            return t
    except Exception:
        pass
    return _env("IG_TOKEN")


def _base() -> str:
    over = _env("IG_GRAPH_BASE")
    if over:
        return over.rstrip("/")
    return "https://graph.instagram.com" if _env("IG_LOGIN", "instagram").lower() == "instagram" else "https://graph.facebook.com"


def _rupload() -> str:
    return (_env("IG_RUPLOAD_BASE") or "https://rupload.facebook.com").rstrip("/")


def _ver() -> str:
    return _env("IG_API_VERSION", "v25.0")


def _call(method: str, url: str, params: dict = None, headers: dict = None, body: bytes = None, timeout: int = 120) -> dict:
    data = body
    if method == "GET" and params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    elif params is not None and body is None:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        err = {}
        try:
            err = json.loads(raw).get("error") or {}
        except ValueError:
            pass
        msg = err.get("error_user_msg") or err.get("message") or raw[:300] or str(e.reason)
        raise IGError(f"Instagram answered HTTP {e.code}: {msg}", err.get("code"), err.get("error_subcode"), e.code) from None
    except urllib.error.URLError as e:
        raise IGError(f"could not reach Instagram: {e.reason}") from None
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        raise IGError(f"unexpected answer from Instagram: {raw[:200]}") from None


def _need() -> tuple:
    uid, tok = _env("IG_USER_ID"), _token()
    if tok and not uid and _env("IG_LOGIN", "instagram").lower() == "instagram":  # the token alone is enough, the id is read from it
        uid = str(_call("GET", f"{_base()}/{_ver()}/me", {"fields": "user_id", "access_token": tok}, timeout=30).get("user_id") or "")
    if not uid or not tok:
        raise IGError("IG_USER_ID and IG_TOKEN are not set in .env (see the Instagram setup steps)")
    return uid, tok


def check() -> str:
    """Plain language status of the setup. Never raises."""
    lines = [f"IG_MODE: {mode()}", f"login type: {_env('IG_LOGIN', 'instagram')}  api: {_base()} {_ver()}"]
    try:
        uid, tok = _need()
        me = _call("GET", f"{_base()}/{_ver()}/{uid}", {"fields": "username,account_type" if _env("IG_LOGIN", "instagram").lower() == "instagram" else "username,followers_count,media_count",
                                                       "access_token": tok}, timeout=30)
        lines.append(f"account: @{me.get('username', '?')} ({me.get('account_type') or str(me.get('followers_count', '?')) + ' followers'})")
        try:
            lim = _call("GET", f"{_base()}/{_ver()}/{uid}/content_publishing_limit", {"fields": "quota_usage,config", "access_token": tok}, timeout=30)
            row = (lim.get("data") or [{}])[0]
            lines.append(f"posts used in the last 24h: {row.get('quota_usage', '?')} of {(row.get('config') or {}).get('quota_total', '?')}")
        except IGError as e:
            lines.append(f"publishing limit not readable: {e}")
        lines.append("token works")
        msg = refresh_token()
        if msg:
            lines.append(msg)
    except IGError as e:
        lines.append(f"PROBLEM: {e}")
        if e.code == 190:
            lines.append("the token is expired or revoked: generate a new one and put it in IG_TOKEN")
    return "\n".join(lines)


def refresh_token(force: bool = False) -> str:
    """Instagram Login tokens last 60 days and can be refreshed after 24 hours. Refresh when more than 30 days old. Returns a note or ''."""
    if _env("IG_LOGIN", "instagram").lower() != "instagram" or not _token():
        return ""
    info = {}
    try:
        info = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    age = time.time() - float(info.get("saved_at", 0) or 0)
    if info.get("saved_at") and age < 30 * 86400 and not force:
        return ""
    try:
        r = _call("GET", f"{_base()}/refresh_access_token", {"grant_type": "ig_refresh_token", "access_token": _token()}, timeout=30)
    except IGError as e:
        return f"token refresh not done: {e}"
    if r.get("access_token"):
        TOKEN_FILE.write_text(json.dumps({"token": r["access_token"], "saved_at": time.time(), "expires_in": r.get("expires_in")}), encoding="utf-8")
        return "token refreshed (kept in ig_token.json)"
    return ""


def _create(uid: str, tok: str, cap: str, video_url: str = None) -> dict:
    params = {"media_type": "REELS", "caption": cap, "share_to_feed": _env("IG_SHARE_TO_FEED", "true").lower(), "thumb_offset": _env("IG_THUMB_MS", "0"), "access_token": tok}  # cover = first frame
    if video_url:
        params["video_url"] = video_url
    else:
        params["upload_type"] = "resumable"
    return _call("POST", f"{_base()}/{_ver()}/{uid}/media", params)


def _upload_file(container: dict, tok: str, path: Path):
    cid = container.get("id")
    uri = container.get("uri") or f"{_rupload()}/ig-api-upload/{_ver()}/{cid}"
    size = path.stat().st_size
    r = _call("POST", uri, headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size), "Content-Type": "application/octet-stream"},
              body=path.read_bytes(), timeout=600)
    if r.get("success") is False:
        raise IGError(f"upload was not accepted: {r}")


def _wait(cid: str, tok: str):
    poll = max(0.2, _num("IG_POLL_SEC", 15))
    deadline = time.time() + _num("IG_POLL_MAX", 600)
    last = ""
    while time.time() < deadline:
        r = _call("GET", f"{_base()}/{_ver()}/{cid}", {"fields": "status_code,status", "access_token": tok}, timeout=30)
        last = r.get("status_code", "")
        if last in ("FINISHED", "PUBLISHED"):
            return
        if last in ("ERROR", "EXPIRED"):
            raise IGError(f"Instagram could not process the video ({last}): {r.get('status', '')}")
        time.sleep(poll)
    raise IGError(f"Instagram was still processing after {int(_num('IG_POLL_MAX', 600))} seconds (last status {last or 'none'})")


def _public_copy(path: Path) -> str:
    pd, pb = _env("IG_PUBLIC_DIR"), _env("IG_PUBLIC_BASE")
    if not pd or not pb:
        return ""
    Path(pd).mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", path.parent.name) + ".mp4"
    shutil.copy2(path, Path(pd) / name)
    return pb.rstrip("/") + "/" + name


# ---- a short lived public link: a tiny web server for ONE file, behind a free Cloudflare quick tunnel (no account, random address, closed after use)
TUNNEL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


class _OneFile(http.server.BaseHTTPRequestHandler):
    path_ok = ""
    file = None

    def log_message(self, *a):
        pass

    def _serve(self, head: bool):
        if self.path.split("?")[0] != "/" + self.path_ok:
            self.send_response(404)
            self.end_headers()
            return
        size = self.file.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        m = re.match(r"bytes=(\d*)-(\d*)$", rng or "")
        code = 200
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head:
            return
        with open(self.file, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def do_GET(self):
        self._serve(False)

    def do_HEAD(self):
        self._serve(True)


def _open_tunnel(port: int):
    """Start cloudflared for the local port. Returns (process, public https base). Raises IGError when it is not installed or does not come up."""
    exe = _env("IG_CLOUDFLARED") or shutil.which("cloudflared") or shutil.which("cloudflared.exe")
    if not exe:
        raise IGError("Instagram wants a link to the video and cloudflared is not installed. Install it once with: winget install --id Cloudflare.cloudflared "
                      "(then open a new terminal), or set IG_PUBLIC_DIR and IG_PUBLIC_BASE to a web folder of yours.")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen([exe, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, creationflags=flags)
    found = {}

    def reader():
        for line in proc.stdout:
            m = TUNNEL_RE.search(line)
            if m and "url" not in found:
                found["url"] = m.group(0)

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.time() + _num("IG_TUNNEL_WAIT", 45)
    while time.time() < deadline and "url" not in found and proc.poll() is None:
        time.sleep(0.3)
    if "url" not in found:
        with contextlib.suppress(Exception):
            proc.terminate()
        raise IGError("the Cloudflare tunnel did not start (no address within 45 seconds). Check your internet and that cloudflared runs.")
    return proc, found["url"]


@contextlib.contextmanager
def public_link(path: Path):
    """Yields a public https link to the file for as long as the block runs. The server and the tunnel are closed afterwards."""
    token = secrets.token_urlsafe(18)
    handler = type("H", (_OneFile,), {"path_ok": token + ".mp4", "file": Path(path)})
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    proc = None
    try:
        proc, base = _open_tunnel(srv.server_address[1])
        url = f"{base}/{token}.mp4"
        # a new address needs a few seconds before it answers. Some home networks cache "no such name" for a new address for minutes: that
        # is only OUR resolver, Instagram looks the name up from outside. So a pure name lookup failure is not a reason to stop.
        ready = _num("IG_TUNNEL_READY", 40)
        t0, last, only_dns = time.time(), "", True
        while True:
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=10) as r:
                    if r.status == 200:
                        break
            except Exception as e:
                last = str(e)
                if not isinstance(getattr(e, "reason", None), socket.gaierror):
                    only_dns = False
            waited = time.time() - t0
            if (only_dns and last and waited >= min(20.0, ready)) or waited >= ready:
                if only_dns and last:
                    log.warning("this computer cannot look up the tunnel name yet (%s), going on anyway: Instagram resolves it from outside", last[:80])
                    break
                raise IGError(f"the tunnel address never answered ({last[:120]})")
            time.sleep(min(2.0, max(0.05, ready / 20)))
        yield url
    finally:
        srv.shutdown()
        srv.server_close()
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.terminate()


def _state_file() -> Path:
    return reels_dir() / "state.json"


def _resumable_refused() -> bool:
    try:
        return bool(json.loads(_state_file().read_text(encoding="utf-8")).get("resumable_refused"))
    except Exception:
        return False


def _remember_refused():
    with contextlib.suppress(Exception):
        _state_file().write_text(json.dumps({"resumable_refused": True}), encoding="utf-8")


def _finish(uid: str, tok: str, cid: str, job_id: str) -> dict:
    _wait(cid, tok)
    pub = _call("POST", f"{_base()}/{_ver()}/{uid}/media_publish", {"creation_id": cid, "access_token": tok})
    media_id = pub.get("id", "")
    link = ""
    with contextlib.suppress(IGError):
        link = _call("GET", f"{_base()}/{_ver()}/{media_id}", {"fields": "permalink", "access_token": tok}, timeout=30).get("permalink", "")
    log.info("Reel published for %s: %s", job_id, link)
    return {"media_id": media_id, "permalink": link}


def publish(job_id: str, reel: Path, cap: str) -> dict:
    """Build the Reel if needed and publish it now. Returns {'media_id', 'permalink'}. Raises IGError.
    Order: send the file itself (resumable). Instagram Login apps are often refused that way and asked for a link instead;
    then the link comes from IG_PUBLIC_DIR/IG_PUBLIC_BASE if set, else from a short lived Cloudflare tunnel. The choice is remembered."""
    uid, tok = _need()
    way = _env("IG_UPLOAD", "auto").lower()
    if way in ("auto", "resumable") and not (way == "auto" and _resumable_refused()):
        try:
            container = _create(uid, tok, cap)
            _upload_file(container, tok, reel)
            return _finish(uid, tok, container["id"], job_id)
        except IGError as e:
            if e.code == 190 or way == "resumable":
                raise
            log.warning("direct upload was refused (%s), using a link instead from now on", e)
            _remember_refused()
    url = _public_copy(reel)
    if url:
        return _finish(uid, tok, _create(uid, tok, cap, video_url=url)["id"], job_id)
    with public_link(reel) as link:
        for attempt in (1, 2):  # the new address is sometimes not reachable for Instagram in the first seconds: one more try
            try:
                return _finish(uid, tok, _create(uid, tok, cap, video_url=link)["id"], job_id)
            except IGError as e:
                if attempt == 2 or e.code == 190 or e.status:
                    raise
                log.warning("Instagram could not use the link (%s), trying once more", e)
                time.sleep(_num("IG_RETRY_SEC", 20))



# ======================================================================= Meta Business (Facebook Page) setup
def _set_env(values: dict, remove: tuple = ()):
    env = config.ROOT / ".env"
    text = env.read_text(encoding="utf-8")
    for k in remove:
        text = re.sub(rf"^{k}=.*\n?", "", text, flags=re.M)
    for k, v in values.items():
        line = f"{k}={v}"
        text = re.sub(rf"^{k}=.*$", line, text, flags=re.M) if re.search(rf"^{k}=", text, flags=re.M) else text.rstrip("\n") + f"\n{line}\n"
        os.environ[k] = str(v)
    env.write_text(text, encoding="utf-8")


def setup_meta() -> str:
    """Turns the short lived Graph API Explorer token (META_USER_TOKEN in .env) into a Page token that does not expire,
    finds the Instagram professional account linked to your Facebook Page, and saves IG_LOGIN, IG_USER_ID, IG_TOKEN and
    IG_MODE=api in .env. The short lived token is removed afterwards. Secrets never leave this PC."""
    app_id, secret, short = _env("META_APP_ID"), _env("META_APP_SECRET"), _env("META_USER_TOKEN")
    if not (app_id and secret and short):
        return "Put META_APP_ID, META_APP_SECRET and META_USER_TOKEN in .env first (docs/INSTAGRAM.md, Meta Business route)."
    g = f"https://graph.facebook.com/{_ver()}"
    long_user = _call("GET", f"{g}/oauth/access_token", {"grant_type": "fb_exchange_token", "client_id": app_id,
                                                          "client_secret": secret, "fb_exchange_token": short}, timeout=30)["access_token"]
    pages = _call("GET", f"{g}/me/accounts", {"fields": "name,access_token,instagram_business_account{id,username}",
                                              "access_token": long_user}, timeout=30).get("data", [])
    want = _env("IG_HANDLE", "").lstrip("@").lower()
    linked = [p for p in pages if p.get("instagram_business_account")]
    if not linked:
        names = ", ".join(p.get("name", "?") for p in pages) or "none"
        return (f"No Facebook Page with a linked Instagram professional account was found (pages seen: {names}). "
                "Link Instagram to the Page in Meta Business Suite > Settings > Instagram accounts, then get a new token.")
    page = next((p for p in linked if p["instagram_business_account"].get("username", "").lower() == want), linked[0])
    ig = page["instagram_business_account"]
    _set_env({"IG_LOGIN": "facebook", "IG_USER_ID": ig["id"], "IG_TOKEN": page["access_token"], "IG_MODE": "api"},
             remove=("META_USER_TOKEN",))
    TOKEN_FILE.unlink(missing_ok=True)  # a token from the Instagram Login route would override this one
    return f"Connected: Instagram @{ig.get('username')} through the Facebook Page '{page.get('name')}'. IG_MODE=api is on. Test: python main.py ig check"
