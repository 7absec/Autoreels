"""Turns an episode into final.mp4 (1080x1920, 30 fps): voices on a timeline, every frame drawn with Pillow
(set, three characters with lip sync, camera cuts, captions, hook, outro) and piped straight into FFmpeg."""
import json
import logging
import math
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import config, sets, tts
from .draw import (GROUND, H, INK, STAGE_Y0, W, Pen, draw_character, draw_fx, ease_out_back, font, skeleton)
from .media import NO_WINDOW, MediaError

log = logging.getLogger("toon.render")
SR = 44100
LEAD, GAP, HOLD, OUTRO = 0.10, 0.10, 1.1, 0.0
LOOP_BACK = 0.3  # the last moments of the hold match frame one, so the Short loops without a visible jump
CHAR_SCALE = 1.12
X = {"pappu": 230, "golu": 545, "chhotu": 860}
REACT_POSE = {"laugh": "hips", "angry": "cross", "confused": "think", "shocked": "shrug", "sleepy": "idle", "happy": "idle"}
CAP_FONT = "Bangers.ttf"
HOOK_Y = 250  # inside the 3:4 area Instagram's profile grid keeps (y 240..1680)


# ======================================================================= audio
def _read(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        n, ch, sw = w.getnframes(), w.getnchannels(), w.getsampwidth()
        data = np.frombuffer(w.readframes(n), dtype=np.int16 if sw == 2 else np.int32).astype(np.float32)
    data /= 32768.0 if sw == 2 else 2147483648.0
    return data.reshape(-1, ch).mean(axis=1) if ch > 1 else data


def _write(path: Path, x: np.ndarray):
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def _env(n, attack=0.004, decay=10.0):
    t = np.arange(n) / SR
    return np.minimum(1.0, t / attack) * np.exp(-t * decay)


def sfx(name: str) -> np.ndarray:
    """Tiny sounds made from sine waves and noise, so there is nothing to license."""
    if name == "pop":
        n = int(0.07 * SR)
        f = np.linspace(500, 950, n)
        return 0.12 * np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, decay=40)
    if name == "boing":
        n = int(0.45 * SR)
        t = np.arange(n) / SR
        f = 220 + 140 * np.sin(2 * np.pi * 9 * t) * np.exp(-t * 5)
        return 0.22 * np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, decay=6)
    if name == "rimshot":  # ba-dum-tss
        out = np.zeros(int(0.9 * SR))
        for at, fr in ((0.0, 120), (0.16, 90)):
            n = int(0.18 * SR)
            t = np.arange(n) / SR
            s = 0.45 * np.sin(2 * np.pi * fr * t * (1 - t)) * _env(n, decay=18)
            i = int(at * SR)
            out[i:i + n] += s
        n = int(0.55 * SR)
        rng = np.random.default_rng(7)
        noise = rng.standard_normal(n) * _env(n, decay=7)
        noise = np.diff(noise, prepend=0)  # brighter, like a cymbal
        i = int(0.34 * SR)
        out[i:i + n] += 0.18 * noise
        return out
    if name == "jingle":
        out = np.zeros(int(1.2 * SR))
        for k, fr in enumerate((523.25, 659.25, 783.99, 1046.5)):
            n = int(0.35 * SR)
            t = np.arange(n) / SR
            tone = (np.sin(2 * np.pi * fr * t) + 0.3 * np.sin(4 * np.pi * fr * t)) * _env(n, decay=7) * 0.12
            i = int(k * 0.13 * SR)
            out[i:i + n] += tone
        return out
    return np.zeros(1)


def _add(track: np.ndarray, clip: np.ndarray, at: float):
    i = int(at * SR)
    j = min(len(track), i + len(clip))
    if i < j:
        track[i:j] += clip[:j - i]


def build_timeline(ep: dict, job_dir: Path) -> dict:
    """Speaks every line, lays them out with gaps, mixes the sound effects. Returns the plan used for drawing."""
    fps = config.FPS
    clips, t = [], LEAD
    for i, ln in enumerate(ep["lines"]):
        wav = tts.speak(ln["who"], ln["hi"])
        x = _read(wav)
        clips.append({"i": i, "start": t, "end": t + len(x) / SR, "audio": x, "wav": str(wav)})
        t += len(x) / SR + GAP
    end_lines = clips[-1]["end"]
    total = end_lines + HOLD + OUTRO
    track = np.zeros(int(total * SR) + SR)
    for c in clips:
        _add(track, c["audio"], c["start"])
        _add(track, sfx("pop"), max(0, c["start"] - 0.06))
    _add(track, sfx("rimshot"), end_lines + 0.05)
    peak = np.max(np.abs(track)) or 1.0
    track = track / peak * 0.92
    voice = job_dir / "voice.wav"
    _write(voice, track[:int(total * SR)])
    # mouth openness per frame for each line: loudness of the voice, smoothed
    for c in clips:
        hop = SR // fps
        a = c["audio"]
        n = max(1, len(a) // hop)
        rms = np.array([np.sqrt(np.mean(a[k * hop:(k + 1) * hop] ** 2) + 1e-9) for k in range(n)])
        rms = rms / (np.percentile(rms, 95) or 1.0)
        c["env"] = np.clip(rms, 0, 1).tolist()
        del c["audio"]
    return {"lines": clips, "total": total, "end_lines": end_lines, "voice": str(voice)}


# ======================================================================= text layers
_CACHE = {}


def _wrap(text: str, fnt, max_w: int) -> list:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if fnt.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def caption_chunks(text: str, max_words: int = 5, max_chars: int = 28) -> list:
    words, out, cur = text.split(), [], []
    for w in words:
        if cur and (len(cur) >= max_words or len(" ".join(cur + [w])) > max_chars):
            out.append(" ".join(cur))
            cur = []
        cur.append(w)
    if cur:
        out.append(" ".join(cur))
    return out


def caption_layer(text: str, who: str) -> Image.Image:
    key = ("cap", text, who)
    if key in _CACHE:
        return _CACHE[key]
    col = tuple(config.CAST.get(who, {}).get("color", (255, 200, 0)))
    name = config.CAST.get(who, {}).get("name", who).upper()
    f = font(CAP_FONT, 92)
    fn = font(CAP_FONT, 46)
    lines = _wrap(text.upper(), f, 960)
    im = Image.new("RGBA", (W, 120 + 100 * len(lines)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    nw = fn.getlength(name) + 50
    d.rounded_rectangle(((W - nw) / 2, 0, (W + nw) / 2, 62), radius=30, fill=col + (255,), outline=INK, width=5)
    d.text((W / 2, 32), name, font=fn, fill=(255, 255, 255), anchor="mm", stroke_width=3, stroke_fill=INK)
    for k, ln in enumerate(lines):
        d.text((W / 2, 130 + k * 100), ln, font=f, fill=(255, 255, 255) if k % 2 == 0 else (255, 230, 90), anchor="mm",
               stroke_width=9, stroke_fill=INK)
    _CACHE[key] = im
    return im


def hook_layer(text: str) -> Image.Image:
    key = ("hook", text)
    if key in _CACHE:
        return _CACHE[key]
    f = font(CAP_FONT, 120)
    lines = _wrap(text.upper(), f, 980)
    im = Image.new("RGBA", (W, 40 + 130 * len(lines)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    wmax = max(f.getlength(ln) for ln in lines)
    x0, x1 = max(20, (W - wmax) / 2 - 40), min(W - 20, (W + wmax) / 2 + 40)
    d.rounded_rectangle((x0, 6, x1, 30 + 130 * len(lines)), radius=34, fill=(178, 44, 44, 245), outline=INK, width=8)
    for k, ln in enumerate(lines):
        d.text((W / 2, 80 + k * 130), ln, font=f, fill=(255, 214, 0), anchor="mm", stroke_width=11, stroke_fill=INK)
    _CACHE[key] = im
    return im


def badge_layer() -> Image.Image:
    if "badge" not in _CACHE:
        name = config.CHANNEL.get("name", "Autoreels").upper()
        f = font(CAP_FONT, 44)
        w = int(f.getlength(name)) + 50
        im = Image.new("RGBA", (w, 70), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, 69), radius=18, fill=(178, 44, 44, 220), outline=INK, width=4)
        d.text((w / 2, 36), name, font=f, fill=(255, 255, 255), anchor="mm")
        _CACHE["badge"] = im
    return _CACHE["badge"]


def outro_layer() -> Image.Image:
    if "outro" not in _CACHE:
        im = Image.new("RGBA", (W, 420), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((90, 20, 990, 400), radius=40, fill=(178, 44, 44, 240), outline=INK, width=8)
        d.text((W / 2, 130), "SUBSCRIBE KARO!", font=font(CAP_FONT, 110), fill=(255, 214, 0), anchor="mm", stroke_width=8, stroke_fill=INK)
        d.text((W / 2, 260), config.CHANNEL.get("handle", "@Yourchannel"), font=font(CAP_FONT, 80), fill=(255, 255, 255), anchor="mm",
               stroke_width=6, stroke_fill=INK)
        d.text((W / 2, 345), "chai thandi ho rahi hai...", font=font("PatrickHand.ttf", 50), fill=(255, 255, 255), anchor="mm")
        _CACHE["outro"] = im
    return _CACHE["outro"]


# ======================================================================= one frame
class Scene:
    def __init__(self, ep: dict, plan: dict):
        self.ep, self.plan = ep, plan
        self.bg = sets.background(ep["location"])
        self.fps = config.FPS
        self.n_lines = len(ep["lines"])
        self.held = {"chhotu": "kettle" if ep["location"] == "tapri" else "none", "pappu": "none", "golu": "none"}
        self._held_at = {}
        held = dict(self.held)
        for i, ln in enumerate(ep["lines"]):  # what each one holds at each line: the prop from their own last line stays
            if ln["prop"] != "none":
                held[ln["who"]] = ln["prop"]
            self._held_at[i] = dict(held)
        # camera: wide for the hook and the punchline, close-ups on the speaker in between
        self.shots = []
        for i, ln in enumerate(ep["lines"]):
            wide = i == 0 or i == self.n_lines - 1 or i % 3 == 2
            self.shots.append(None if wide else X[ln["who"]])
        self.chunks = [caption_chunks(ln["caption"]) for ln in ep["lines"]]

    def _line_at(self, t):
        cur = None
        for c in self.plan["lines"]:
            if t >= c["start"] - 0.05:
                cur = c
        return cur

    def frame(self, t: float) -> Image.Image:
        lines = self.ep["lines"]
        c = self._line_at(t)
        i = c["i"] if c else 0
        ln = lines[i]
        speaking = bool(c) and c["start"] <= t <= c["end"]
        age = t - (c["start"] if c else 0)
        in_hold = t > self.plan["end_lines"]
        in_outro = OUTRO > 0 and t > self.plan["end_lines"] + HOLD
        if in_hold and t > self.plan["total"] - LOOP_BACK:  # back to how the video starts
            c, i, ln, age, in_hold, speaking = None, 0, lines[0], 0.0, False, False
        mouth = 0.0
        if speaking:
            k = int((t - c["start"]) * self.fps)
            env = c["env"]
            mouth = env[min(k, len(env) - 1)] if env else 0.0
        im = self.bg.copy()
        pen = Pen()
        held = self._held_at[i] if c is not None or i else self.held
        for who in ("pappu", "golu", "chhotu"):
            s = config.CAST.get(who, {}).get("scale", 1.0) * CHAR_SCALE
            is_spk = who == ln["who"] and not in_hold
            if who == "pappu":
                flip = 1
            elif who == "chhotu":
                flip = -1
            else:
                flip = -1 if ln["who"] == "chhotu" else 1
            if in_outro:
                pose, face = ("wave" if who != "golu" else "cheer"), "happy"
            elif in_hold:
                pose = "hips" if who == ln["who"] else "cheer"
                face = "smug" if who == ln["who"] else "laugh"
            elif is_spk:
                pose, face = ln["pose"], ln["face"]
            else:
                face = ln["react"] if age > 0.25 else (lines[i - 1]["react"] if i else "neutral")
                pose = REACT_POSE.get(face, "idle")
            hop = math.sin(math.pi * min(1.0, age / 0.25)) * 16 * s if (is_spk and age < 0.25) else 0.0
            sk = skeleton(X[who], GROUND, pose, t + X[who] * 0.01, flip, s, hop=hop, talking=mouth if is_spk else 0.0)
            prop = held.get(who, "none")
            if pose in ("cheer", "panic", "facepalm", "wave", "shrug"):
                prop = "none" if prop in ("kettle", "bat", "umbrella") else prop
            draw_character(pen, who, sk, face, t, mouth if is_spk else 0.0, is_spk and speaking, prop)
            if is_spk and speaking:
                draw_fx(pen, ln["fx"], sk["head"], sk["r"], t, age)
            if in_hold and who != ln["who"]:
                draw_fx(pen, "laugh", sk["head"], sk["r"], t, t - self.plan["end_lines"])
        layer = pen.done()
        im.paste(layer, (0, STAGE_Y0), layer)
        # camera
        zoom, cx = 1.0, W / 2
        shot = self.shots[i] if not in_hold else None
        if shot is not None:
            zoom, cx = 1.32, shot
        if i == self.n_lines - 1 and speaking:  # punch in on the punchline
            zoom = 1.0 + 0.12 * ease_out_back(min(1.0, age / 0.35))
            cx = X[ln["who"]] * 0.5 + W / 4
        if zoom > 1.001:
            cw, ch = W / zoom, H / zoom
            x0 = min(max(0, cx - cw / 2), W - cw)
            y0 = min(max(0, 1150 - ch * 0.56), H - ch)
            im = im.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
        if in_hold and t - self.plan["end_lines"] < 0.25:  # a little shake on the rimshot
            dx = int(math.sin(t * 90) * 10)
            im = im.transform(im.size, Image.AFFINE, (1, 0, dx, 0, 1, 0), fillcolor=(0, 0, 0))
        # overlays
        im.paste(badge_layer(), (30, 40), badge_layer())
        looping = t > self.plan["total"] - LOOP_BACK
        if t < 3.2 or looping:
            hk = hook_layer(self.ep["hook"])  # full size from frame one: frame one is the thumbnail, the Reel cover and the loop point
            im.paste(hk, ((W - hk.width) // 2, HOOK_Y), hk)
        if in_outro:
            o = outro_layer()
            pop = ease_out_back(min(1.0, (t - self.plan["end_lines"] - HOLD) / 0.4))
            o2 = o.resize((max(1, int(W * pop)), max(1, int(o.height * pop))), Image.BILINEAR)
            im.paste(o2, ((W - o2.width) // 2, 1560), o2)
        elif c and not in_hold:
            chunks = self.chunks[i]
            dur = max(0.3, c["end"] - c["start"])
            total_chars = sum(len(x) for x in chunks) or 1
            acc, k = 0.0, 0
            pos = max(0.0, t - c["start"]) / dur
            for k, ch_ in enumerate(chunks):
                acc += len(ch_) / total_chars
                if pos <= acc:
                    break
            cap = caption_layer(chunks[k], ln["who"])
            im.paste(cap, (0, 1585), cap)
        return im


# ======================================================================= encode
def render(ep: dict, job_dir: Path) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)
    plan = build_timeline(ep, job_dir)
    (job_dir / "timeline.json").write_text(json.dumps({k: v for k, v in plan.items()}, ensure_ascii=False)[:200000], encoding="utf-8")
    scene = Scene(ep, plan)
    fps = config.FPS
    n = int(plan["total"] * fps)
    out = job_dir / "final.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-i", plan["voice"]]
    music = Path(config.MUSIC_FILE) if config.MUSIC_FILE else None
    if music and music.exists():
        cmd += ["-stream_loop", "-1", "-i", str(music), "-filter_complex",
                f"[2:a]volume={config.MUSIC_VOLUME}[m];[1:a][m]amix=inputs=2:duration=first:normalize=0[a]", "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", "-shortest", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, **NO_WINDOW)
    try:
        for f in range(n):
            p.stdin.write(scene.frame(f / fps).tobytes())
            if f % (fps * 5) == 0:
                log.info("frame %d / %d", f, n)
        p.stdin.close()
    except BrokenPipeError:
        pass
    err = p.stderr.read().decode("utf-8", "replace")
    if p.wait() != 0:
        raise MediaError(f"ffmpeg failed: {err[-1500:]}")
    thumbnail(scene, plan, job_dir / "thumb.jpg")
    return out


def thumbnail(scene: Scene, plan: dict, path: Path) -> Path:
    """The thumbnail is the video's first frame (hook text, the three characters, the location), so the YouTube thumbnail,
    the Instagram Reel cover and what viewers see first are the same picture."""
    scene.frame(0.0).convert("RGB").save(path, quality=92)
    return path
