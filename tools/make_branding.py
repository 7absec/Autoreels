"""Draws the channel logo (800x800) and banner (2560x1440, text inside the 1546x423 safe area) into branding/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw  # noqa: E402

from toon import config  # noqa: E402
from toon.draw import INK, Pen, draw_character, skeleton  # noqa: E402

OUT = config.ROOT / "branding"
RED, CREAM, YELLOW = (178, 44, 44), (255, 236, 200), (255, 214, 0)


def _trio(pen, cx, ground, scale, spread, poses=("point", "cheer", "hips"), faces=("smug", "laugh", "smug"), t=0.4):
    for (who, dx, flip), pose, face in zip((("pappu", -spread, 1), ("golu", 0, 1), ("chhotu", spread, -1)), poses, faces):
        s = config.CAST[who]["scale"] * scale
        sk = skeleton(cx + dx, ground, pose, t, flip, s)
        draw_character(pen, who, sk, face, t, prop="chai" if who == "golu" else ("kettle" if who == "chhotu" else "none"))


def logo() -> Path:
    S = 800
    pen = Pen(0, 0, S, S)
    pen.circle((S / 2, S / 2), S / 2 - 6, fill=RED)
    pen.circle((S / 2, S / 2), S / 2 - 40, fill=CREAM, outline=INK, width=10)
    # the three heads, close together
    for who, x, y, r in (("pappu", 250, 380, 105), ("golu", 410, 440, 115), ("chhotu", 560, 390, 92)):
        sk = {"s": r / 64, "flip": 1 if x < 400 else -1, "r": r, "neck": (x, y + r + 30), "hip": (x, y + r + 60),
              "head": (x, y), "legs": [], "arms": [((x, y + r + 40), (x, y + r + 40), (x, y + r + 40))] * 2}
        draw_character(pen, who, sk, {"pappu": "smug", "golu": "happy", "chhotu": "laugh"}[who], 0.4)
    pen.rrect((90, 560, 710, 700), 30, fill=RED, outline=INK, width=8)
    pen.text((S / 2, 632), "AUTOREELS", "Bangers.ttf", 104, fill=YELLOW, stroke=6, stroke_fill=INK)
    im = pen.done()
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, S - 1, S - 1), fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    p = OUT / "logo.png"
    out.save(p)
    return p


def banner() -> Path:
    Wb, Hb = 2560, 1440
    from toon import sets
    bg = sets.background("tapri").resize((Wb, int(1920 * Wb / 1080)))
    im = bg.crop((0, 300, Wb, 300 + Hb)).convert("RGB")
    shade = Image.new("RGBA", (Wb, Hb), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.rectangle((0, 470, Wb, 970), fill=(255, 236, 200, 255))
    for y in (470, 958):
        sd.rectangle((0, y, Wb, y + 12), fill=RED + (255,))
    im.paste(shade, (0, 0), shade)
    pen = Pen(0, 0, Wb, Hb)
    _trio(pen, 640, 960, 0.80, 165)
    pen.text((1520, 600), "AUTOREELS", "Bangers.ttf", 210, fill=YELLOW, stroke=12, stroke_fill=INK)
    pen.text((1520, 760), config.CHANNEL.get("tagline", ""), "PatrickHand.ttf", 84, fill=RED, stroke=4, stroke_fill=(255, 255, 255))
    pen.rrect((1150, 830, 1890, 920), 30, fill=RED, outline=INK, width=6)
    pen.text((1520, 876), "Roz 3 Shorts: 7 AM | 12 PM | 7 PM", "Bangers.ttf", 58, fill=(255, 255, 255))
    layer = pen.done()
    im.paste(layer, (0, 0), layer)
    p = OUT / "banner.png"
    im.save(p)
    return p


def main() -> str:
    OUT.mkdir(exist_ok=True)
    return f"{logo()}\n{banner()}"


if __name__ == "__main__":
    print(main())
