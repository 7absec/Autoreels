import shutil
import subprocess
import sys

# On Windows every child console program (ffmpeg, ffprobe, piper) opens a visible window unless this flag is set.
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

class MediaError(RuntimeError):
    pass



def check_tools():
    missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
    if missing:
        raise MediaError(f"Missing required tools on PATH: {', '.join(missing)}")


def run(cmd, cwd=None):
    """Run a command given as a list (never a shell string)."""
    
    cmd = [str(c) for c in cmd]
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, **NO_WINDOW)
    if p.returncode != 0:
        raise MediaError(f"{cmd[0]} failed:\n{p.stderr[-2000:]}")
    return p.stdout


def duration(path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", path])
    return float(out.strip())
