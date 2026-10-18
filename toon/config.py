"""All settings in one place. Values come from .env (see .env.example); everything has a working default."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _s(k, d=""):
    return os.getenv(k, d).strip()


def _b(k, d="false"):
    return _s(k, d).lower() in ("1", "true", "yes", "on")


def _i(k, d):
    try:
        return int(_s(k, str(d)))
    except ValueError:
        return d


DATA = ROOT / "data"
OUTPUT = ROOT / "output"
CACHE = ROOT / "cache"
LOGS = ROOT / "logs"
INBOX = ROOT / "inbox"
FONTS = ROOT / "assets" / "fonts"
for _d in (OUTPUT, CACHE, LOGS, INBOX):
    _d.mkdir(parents=True, exist_ok=True)

# --- language model: local Ollama by default, Claude when LLM_PROVIDER=anthropic
LLM_PROVIDER = _s("LLM_PROVIDER", "auto").lower()           # auto = Claude when a key is set, else Ollama
OLLAMA_HOST = _s("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = _s("OLLAMA_MODEL", "qwen2.5:14b")
ANTHROPIC_API_KEY = _s("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = _s("ANTHROPIC_MODEL", "claude-sonnet-5-5")
if LLM_PROVIDER == "auto":
    LLM_PROVIDER = "anthropic" if ANTHROPIC_API_KEY else "ollama"

# --- voices: ElevenLabs per character, free Edge voices as the fallback
TTS_ENGINE = _s("TTS_ENGINE", "eleven").lower()          # eleven | edge
ELEVEN_API_KEY = _s("ELEVEN_API_KEY")
ELEVEN_MODEL = _s("ELEVEN_MODEL", "eleven_multilingual_v2")

# --- video
FPS = _i("FPS", 30)
MUSIC_FILE = _s("MUSIC_FILE")                             # optional royalty free loop, mixed quietly
MUSIC_VOLUME = float(_s("MUSIC_VOLUME", "0.10") or 0.10)

# --- YouTube
CLIENT_SECRET = ROOT / "client_secret.json"
TOKEN_FILE = ROOT / "token.json"
YT_PRIVACY = _s("YT_PRIVACY", "private")
YT_CATEGORY = _s("YT_CATEGORY", "23")                    # 23 = Comedy
YT_SYNTHETIC = _b("YT_SYNTHETIC", "false")                # cartoons are obviously animated, disclosure is not required
LANGUAGE = _s("VIDEO_LANGUAGE", "hi")

# --- autopilot
TZ_NAME = _s("TZ_NAME", "Asia/Kolkata")
SLOTS = [s.strip() for s in _s("SLOTS", "07:00-07:30,12:00-12:30,19:00-19:30").split(",") if s.strip()]
REVIEW_MODE = _s("REVIEW_MODE", "hold").lower()           # hold = wait for `approve`, auto = upload when checks pass

# --- local API for n8n
API_PORT = _i("API_PORT", 8770)
API_TOKEN = _s("FACTORY_API_TOKEN")


def load_json(name: str, default=None):
    p = DATA / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


CHANNEL = load_json("channel.json", {})
CAST = load_json("cast.json", {})
