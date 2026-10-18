"""The five locations, drawn once with the same pen as the characters and cached as PNG.
tapri (Raju's chai stall), kirana (Sharma General Store), school (classroom), gali (street), chhat (rooftop)."""
import math
import random

from PIL import Image

from . import config
from .draw import GROUND, H, INK, W, Pen, mix

LOCATIONS = ["tapri", "kirana", "school", "gali", "chhat"]
VERSION = 3  # bump to redraw cached sets
_MEM = {}


def _sky(pen, top, bottom, y1=GROUND):
    for i in range(0, int(y1), 8):
        pen.rect((0, i, W, i + 9), fill=mix(top, bottom, i / y1))


def _ground(pen, col, rnd):
    pen.rect((0, GROUND, W, H), fill=col)
    for _ in range(70):
        x, y = rnd.uniform(0, W), rnd.uniform(GROUND + 30, H - 20)
        r = rnd.uniform(2, 6)
        pen.circle((x, y), r, fill=mix(col, INK, 0.18))
    pen.line((0, GROUND), (W, GROUND), 6, fill=mix(col, INK, 0.5))


def _sign(pen, box, text, sub, bg, fg=(255, 255, 255)):
    pen.rrect(box, 14, fill=bg, outline=INK, width=7)
    cx = (box[0] + box[2]) / 2
    pen.text((cx, box[1] + (box[3] - box[1]) * (0.40 if sub else 0.5)), text, "Bangers.ttf", 88, fill=fg, stroke=5, stroke_fill=INK)
    if sub:
        pen.text((cx, box[3] - 34), sub, "PatrickHand.ttf", 40, fill=fg, stroke=3, stroke_fill=INK)


def _rect_pen(pen):
    # a tiny helper: filled rectangle via rrect with no radius
    return lambda b, fill, outline=None, width=0: pen.rrect(b, 0, fill=fill, outline=outline, width=width)


def _tapri(pen, rnd):
    _sky(pen, (255, 196, 140), (255, 236, 200))
    R = _rect_pen(pen)
    # the building behind: old plaster wall with a window and posters
    R((0, 300, W, GROUND), fill=(236, 214, 170))
    for y in range(340, GROUND, 70):
        pen.line((0, y), (W, y), 2, fill=(222, 196, 150))
    R((60, 760, 300, 1040), fill=(120, 170, 190), outline=INK, width=6)
    pen.line((180, 760), (180, 1040), 5)
    pen.line((60, 900), (300, 900), 5)
    for i, c in enumerate([(240, 90, 80), (90, 140, 230)]):
        R((780 + i * 130, 790, 880 + i * 130, 930), fill=c, outline=INK, width=4)
        pen.text((830 + i * 130, 860), ["SALE", "JOB!"][i], "Bangers.ttf", 34, fill=(255, 255, 255))
    # awning with stripes
    stripes = [(220, 50, 50), (255, 255, 255)]
    for i in range(12):
        x0 = i * 90
        pen.poly([(x0, 560), (x0 + 90, 560), (x0 + 90, 680), (x0, 680)], fill=stripes[i % 2])
    for i in range(12):
        pen.pie((i * 90, 640, i * 90 + 90, 720), 0, 180, fill=stripes[i % 2])
    pen.line((0, 560), (W, 560), 8)
    # hanging chips packets
    for i in range(9):
        x = 110 + i * 100
        pen.line((x, 690), (x, 730), 3)
        R((x - 30, 730, x + 30, 810), fill=[(250, 200, 30), (60, 170, 220), (240, 80, 120)][i % 3], outline=INK, width=4)
    _sign(pen, (110, 330, 970, 530), "RAJU TEA STALL", "Cutting Chai Rs 10  |  Bun Maska  |  Samosa", (178, 44, 44))
    # the counter
    R((60, 1180, 1020, GROUND), fill=(160, 104, 60), outline=INK, width=7)
    for x in range(60, 1020, 120):
        pen.line((x, 1180), (x, GROUND), 3, fill=(130, 82, 46))
    R((40, 1160, 1040, 1190), fill=(120, 74, 40), outline=INK, width=6)
    # stove and kettle on the left of the counter
    R((110, 1090, 260, 1160), fill=(90, 90, 96), outline=INK, width=5)
    pen.ellipse((120, 990, 250, 1100), fill=(205, 205, 210), outline=INK, width=6)
    pen.line((245, 1030), (300, 990), 10, fill=(180, 180, 186))
    for i in range(3):
        pen.arc((150 + i * 30, 900 - i * 20, 200 + i * 30, 990 - i * 20), 90, 270, 5, fill=(255, 255, 255))
    # glass jars of biscuits on the right
    for i, c in enumerate([(240, 200, 120), (220, 150, 90), (250, 230, 180)]):
        x = 760 + i * 90
        R((x, 1060, x + 74, 1160), fill=mix(c, (255, 255, 255), 0.3), outline=INK, width=5)
        R((x - 4, 1046, x + 78, 1068), fill=(220, 40, 40), outline=INK, width=4)
        for j in range(3):
            pen.circle((x + 20 + j * 18, 1120 - j * 14), 12, fill=c)
    _ground(pen, (196, 170, 130), rnd)


def _kirana(pen, rnd):
    _sky(pen, (170, 220, 255), (225, 240, 255))
    R = _rect_pen(pen)
    R((0, 300, W, GROUND), fill=(250, 226, 120))
    _sign(pen, (90, 330, 990, 530), "SHARMA GENERAL STORE", "Kirana  |  Doodh  |  Recharge", (30, 110, 60))
    R((90, 580, 990, 1220), fill=(60, 42, 30), outline=INK, width=7)   # the open shop
    R((90, 560, 990, 610), fill=(150, 150, 160), outline=INK, width=6)  # rolled up shutter
    for y in range(570, 610, 10):
        pen.line((90, y), (990, y), 2, fill=(120, 120, 130))
    colors = [(230, 60, 60), (250, 190, 40), (60, 140, 230), (90, 190, 90), (240, 120, 40), (180, 80, 200)]
    for row in range(4):
        y = 640 + row * 145
        R((110, y + 110, 970, y + 122), fill=(140, 96, 60))
        x = 130
        while x < 940:
            w = rnd.choice([50, 60, 70])
            h = rnd.choice([70, 90, 100])
            R((x, y + 110 - h, x + w, y + 110), fill=rnd.choice(colors), outline=INK, width=3)
            x += w + 10
    # hanging shampoo sachets
    for i in range(14):
        x = 130 + i * 60
        pen.line((x, 610), (x, 640), 2)
        R((x - 18, 640, x + 18, 690), fill=colors[i % len(colors)], outline=INK, width=2)
    R((60, 1180, 1020, GROUND), fill=(110, 140, 170), outline=INK, width=7)   # counter
    pen.text((540, 1340), "UPI ACCEPTED", "Bangers.ttf", 64, fill=(255, 255, 255), stroke=4, stroke_fill=INK)
    # rice sacks
    for i in range(2):
        pen.ellipse((-20 + i * 130, 1330, 140 + i * 130, 1520), fill=(236, 226, 200), outline=INK, width=6)
    _ground(pen, (200, 190, 170), rnd)


def _school(pen, rnd):
    R = _rect_pen(pen)
    R((0, 0, W, GROUND), fill=(214, 236, 214))
    R((0, 0, W, 200), fill=(240, 240, 232))
    # ceiling fan
    pen.line((540, 200), (540, 260), 8)
    pen.ellipse((500, 250, 580, 290), fill=(120, 120, 130), outline=INK, width=5)
    for a in (0, 120, 240):
        ra = math.radians(a + 15)
        pen.poly([(540, 270), (540 + math.cos(ra) * 260, 270 + math.sin(ra) * 30), (540 + math.cos(ra + 0.2) * 260, 270 + math.sin(ra + 0.2) * 30)], fill=(150, 150, 160), outline=INK, width=4)
    # blackboard
    R((80, 360, 1000, 940), fill=(116, 84, 56), outline=INK, width=7)
    R((110, 390, 970, 910), fill=(36, 74, 56))
    chalk = (236, 240, 236)
    pen.text((540, 460), "Aaj ka Vichar:", "PatrickHand.ttf", 66, fill=chalk)
    pen.text((540, 560), "Padhai karo,", "PatrickHand.ttf", 72, fill=chalk)
    pen.text((540, 650), "jugaad nahi!", "PatrickHand.ttf", 72, fill=chalk)
    pen.text((830, 860), "2 + 2 = 4", "PatrickHand.ttf", 44, fill=mix(chalk, (36, 74, 56), 0.3))
    pen.text((250, 860), "Class 7-B", "PatrickHand.ttf", 44, fill=mix(chalk, (36, 74, 56), 0.3))
    R((420, 912, 660, 930), fill=(140, 100, 70))
    # window
    R((0, 1000, 150, 1300), fill=(160, 210, 240), outline=INK, width=6)
    pen.line((75, 1000), (75, 1300), 5)
    # back row desks
    for x in (200, 560, 900):
        R((x - 130, 1250, x + 130, 1290), fill=(176, 120, 70), outline=INK, width=5)
        R((x - 120, 1290, x - 100, 1420), fill=(140, 96, 56))
        R((x + 100, 1290, x + 120, 1420), fill=(140, 96, 56))
    R((0, GROUND, W, H), fill=(196, 180, 160))
    for x in range(0, W, 120):
        pen.line((x, GROUND), (x - 60, H), 3, fill=(170, 154, 134))
    pen.line((0, GROUND), (W, GROUND), 6, fill=(120, 100, 80))


def _gali(pen, rnd):
    _sky(pen, (150, 210, 250), (215, 238, 255))
    R = _rect_pen(pen)
    houses = [(-20, 260, 300, (255, 170, 160)), (290, 420, 520, (170, 210, 250)), (510, 340, 790, (250, 220, 130)), (780, 220, 1100, (190, 230, 180))]
    for x0, top, x1, c in houses:
        R((x0, top, x1, GROUND), fill=c, outline=INK, width=6)
        for wy in range(top + 80, GROUND - 260, 230):
            R((x0 + 50, wy, x0 + 140, wy + 130), fill=(90, 120, 150), outline=INK, width=5)
            if x1 - x0 > 250:
                R((x1 - 140, wy, x1 - 50, wy + 130), fill=(90, 120, 150), outline=INK, width=5)
            pen.line((x0 + 30, wy + 150), (x1 - 30, wy + 150), 8, fill=mix(c, INK, 0.4))  # balcony rail
        R((x0 + (x1 - x0) / 2 - 60, GROUND - 230, x0 + (x1 - x0) / 2 + 60, GROUND), fill=mix(c, INK, 0.45), outline=INK, width=5)
    # tangled electric wires
    for i in range(6):
        y0 = 300 + i * 26
        pts = [(x, y0 + 60 * math.sin(x / 300 + i) + rnd.uniform(-6, 6)) for x in range(-20, W + 40, 60)]
        pen.path(pts, 3, fill=(40, 40, 40))
    pen.line((180, 220), (180, GROUND), 10, fill=(110, 110, 110))  # pole
    # a parked scooter on the right
    pen.circle((860, 1440), 46, fill=INK)
    pen.circle((1010, 1440), 46, fill=INK)
    pen.poly([(820, 1420), (1050, 1420), (1020, 1320), (900, 1320)], fill=(220, 50, 60), outline=INK, width=5)
    pen.line((860, 1330), (840, 1230), 8)
    pen.line((810, 1230), (870, 1230), 8)
    _ground(pen, (150, 150, 155), rnd)
    pen.rrect((0, 1600, W, 1630), 0, fill=(110, 110, 115))  # the drain line


def _chhat(pen, rnd):
    _sky(pen, (90, 170, 245), (190, 228, 255))
    R = _rect_pen(pen)
    for cx, cy in ((200, 260), (760, 380), (980, 200)):
        for dx, r in ((-50, 50), (0, 70), (55, 52)):
            pen.circle((cx + dx, cy), r, fill=(255, 255, 255))
    # kites in the sky
    for kx, ky, c in ((300, 520, (240, 60, 120)), (840, 640, (250, 200, 40))):
        pen.poly([(kx, ky - 60), (kx + 50, ky), (kx, ky + 70), (kx - 50, ky)], fill=c, outline=INK, width=4)
        pen.path([(kx, ky + 70), (kx + 30, ky + 160), (kx - 20, ky + 260)], 2)
    # distant rooftops
    for x0, top, c in ((-20, 1060, (220, 200, 190)), (260, 1110, (200, 214, 230)), (560, 1030, (236, 220, 180)), (820, 1090, (210, 230, 210))):
        R((x0, top, x0 + 300, GROUND), fill=c, outline=INK, width=4)
    # black water tank on a stand
    R((760, 960, 800, 1300), fill=(90, 90, 90))
    R((960, 960, 1000, 1300), fill=(90, 90, 90))
    pen.ellipse((730, 760, 1030, 1000), fill=(34, 34, 40), outline=INK, width=6)
    R((730, 860, 1030, 960), fill=(34, 34, 40))
    pen.ellipse((730, 900, 1030, 1020), fill=(34, 34, 40), outline=INK, width=6)
    for y in (850, 900, 950):
        pen.line((735, y), (1025, y), 3, fill=(70, 70, 80))
    # clothesline
    pen.line((40, 900), (680, 860), 3)
    for i, c in enumerate([(240, 80, 80), (60, 140, 230), (250, 210, 60), (120, 200, 120)]):
        x = 110 + i * 150
        y = 896 - i * 9
        R((x, y, x + 100, y + 150), fill=c, outline=INK, width=4)
    # parapet wall behind the characters
    R((0, 1300, W, GROUND), fill=(214, 200, 190), outline=INK, width=6)
    for x in range(0, W, 160):
        pen.line((x, 1300), (x, GROUND), 3, fill=(190, 176, 166))
    _ground(pen, (186, 170, 160), rnd)


_DRAW = {"tapri": _tapri, "kirana": _kirana, "school": _school, "gali": _gali, "chhat": _chhat}


def background(name: str) -> Image.Image:
    """The location as an RGB image, W x H. Cached in memory and on disk."""
    name = name if name in _DRAW else "tapri"
    if name in _MEM:
        return _MEM[name]
    path = config.CACHE / "sets" / f"{name}_v{VERSION}.png"
    if path.exists():
        im = Image.open(path).convert("RGB")
    else:
        pen = Pen(0, 0, W, H)
        _DRAW[name](pen, random.Random(name))
        im = pen.done().convert("RGB")
        path.parent.mkdir(parents=True, exist_ok=True)
        im.save(path)
    _MEM[name] = im
    return im
