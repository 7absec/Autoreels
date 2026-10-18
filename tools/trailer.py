"""The channel trailer: renders data/trailer.json like an episode, makes a 16:9 version (the vertical video centred on a
blurred copy of itself, so YouTube treats it as a normal video and shows it full width on the channel page), and can
upload it publicly and set it as the trailer for non-subscribers."""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from toon import config, media, pipeline, seo, store, youtube  # noqa: E402

log = logging.getLogger("toon.trailer")


def landscape(vertical: Path, out: Path) -> Path:
    media.run(["ffmpeg", "-y", "-loglevel", "error", "-i", vertical, "-filter_complex",
               "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=30:3,eq=brightness=-0.08[bg];"
               "[0:v]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0,setsar=1[v]",
               "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
               "-c:a", "copy", "-movflags", "+faststart", out])
    return out


def make() -> str:
    jid = pipeline.make(script=config.DATA / "trailer.json")
    d = pipeline.job_dir(jid)
    landscape(d / "final.mp4", d / "trailer_16x9.mp4")
    store.update(jid, kind="trailer")
    return jid


def publish(jid: str) -> dict:
    d = pipeline.job_dir(jid)
    ep = json.loads((d / "episode.json").read_text(encoding="utf-8"))
    meta = seo.metadata(ep)
    desc = config.CHANNEL.get("about", "") + "\n\n" + " ".join(h for h in config.CHANNEL.get("hashtags", []) if h.lower() != "#shorts")
    url, vid = youtube.upload(d / "trailer_16x9.mp4", ep["title"], desc, meta["tags"], "public", with_id=True, shorts=False)
    ok, note = youtube.set_channel_trailer(vid)
    rec = store.update(jid, status="uploaded", url=url, video_id=vid, privacy="public", trailer_set=ok, trailer_note=note)
    pipeline.post_comments()
    return rec


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    j = make()
    print("trailer job:", j)
