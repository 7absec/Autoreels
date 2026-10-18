"""One voice per character. ElevenLabs (voice ids in data/cast.json) when ELEVEN_API_KEY is set,
otherwise, or when ElevenLabs fails, the free Microsoft Edge Hindi voice with a per character pitch and speed.
Every take is cached by (engine, voice, text), so rendering an episode again costs no credits."""
import asyncio
import hashlib
import logging
from pathlib import Path

import requests

from . import config
from .media import MediaError, run

log = logging.getLogger("toon.tts")
CACHE = config.CACHE / "tts"


def _eleven(text: str, voice_id: str, out: Path) -> Path:
    if not config.ELEVEN_API_KEY:
        raise MediaError("ELEVEN_API_KEY is empty")
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
                      headers={"xi-api-key": config.ELEVEN_API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"},
                      json={"text": text, "model_id": config.ELEVEN_MODEL, "language_code": "hi",
                            "voice_settings": {"stability": 0.38, "similarity_boost": 0.8, "style": 0.55, "use_speaker_boost": True}},
                      timeout=90)
    if r.status_code == 400 and "language_code" in r.text:  # older models refuse language_code: try once without it
        r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
                          headers={"xi-api-key": config.ELEVEN_API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"},
                          json={"text": text, "model_id": config.ELEVEN_MODEL,
                                "voice_settings": {"stability": 0.38, "similarity_boost": 0.8, "style": 0.55, "use_speaker_boost": True}},
                          timeout=90)
    if r.status_code != 200 or len(r.content) < 1000:
        raise MediaError(f"ElevenLabs answered {r.status_code}: {r.text[:200]}")
    out.write_bytes(r.content)
    return out


def _edge(text: str, c: dict, out: Path) -> Path:
    import edge_tts
    asyncio.run(edge_tts.Communicate(text, c.get("edge_voice", "hi-IN-MadhurNeural"), rate=c.get("edge_rate", "+0%"),
                                     pitch=c.get("edge_pitch", "+0Hz")).save(str(out)))
    return out


def speak(who: str, text: str) -> Path:
    """A 44.1 kHz mono wav of this character saying this text."""
    c = config.CAST.get(who, {})
    CACHE.mkdir(parents=True, exist_ok=True)
    engines = ["eleven", "edge"] if (config.TTS_ENGINE in ("eleven", "elevenlabs") and config.ELEVEN_API_KEY and c.get("eleven_voice")) else ["edge"]
    last = None
    for eng in engines:
        voice = c.get("eleven_voice") if eng == "eleven" else f"{c.get('edge_voice')}{c.get('edge_rate')}{c.get('edge_pitch')}"
        key = hashlib.sha1(f"{eng}|{voice}|{config.ELEVEN_MODEL if eng == 'eleven' else ''}|{text}".encode("utf-8")).hexdigest()[:20]
        wav = CACHE / f"{who}_{key}.wav"
        if wav.exists():
            return wav
        raw = CACHE / f"{who}_{key}.mp3"
        try:
            (_eleven(text, c["eleven_voice"], raw) if eng == "eleven" else _edge(text, c, raw))
            # mono, 44.1 kHz, trim leading silence, a short breath at the end
            run(["ffmpeg", "-y", "-i", raw, "-ar", "44100", "-ac", "1",
                 "-af", "silenceremove=start_periods=1:start_threshold=-45dB,apad=pad_dur=0.12", wav])
            raw.unlink(missing_ok=True)
            return wav
        except Exception as e:
            last = e
            log.warning("%s voice for %s failed: %s", eng, who, str(e)[:200])
    raise MediaError(f"no voice could speak the line: {last}")
