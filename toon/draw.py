"""The stickman drawing kit: a supersampled pen, an IK skeleton that works at any size, faces, the three
characters (Pappu, Golu, Chhotu), hand props and small effects. Pen, ik and the pose table come from
shorts_factory_v8/shorts/stick.py, made size independent so a short and a tall figure share one rig."""
import math

from PIL import Image, ImageDraw, ImageFont

from . import config

W, H = 1080, 1920
SS = 2                       # drawn at twice the size and shrunk, so lines are smooth
STAGE_Y0, STAGE_Y1 = 700, 1600
GROUND = 1500                # where the feet stand
INK = (30, 26, 34)
WHITE = (255, 255, 255)
SKIN = (255, 236, 214)

_FONTS = {}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key not in _FONTS:
        p = config.FONTS / name
        if not p.exists():
            p = config.FONTS / "DejaVuSans-Bold.ttf"
        _FONTS[key] = ImageFont.truetype(str(p), size)
    return _FONTS[key]


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def clamp01(x):
    return max(0.0, min(1.0, x))


def ease_out_back(t: float) -> float:
    t = clamp01(t)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


class Pen:
    """Draws in frame coordinates onto a supersampled transparent layer that covers (ox, oy, ox+w, oy+h)."""

    def __init__(self, ox=0.0, oy=STAGE_Y0, w=W, h=STAGE_Y1 - STAGE_Y0):
        self.ox, self.oy, self.w, self.h = ox, oy, w, h
        self.im = Image.new("RGBA", (int(w * SS), int(h * SS)), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def p(self, x, y):
        return ((x - self.ox) * SS, (y - self.oy) * SS)

    def line(self, a, b, width=12, fill=INK):
        pa, pb = self.p(*a), self.p(*b)
        self.d.line([pa, pb], fill=fill, width=max(1, int(width * SS)))
        r = width * SS / 2
        for q in (pa, pb):
            self.d.ellipse((q[0] - r, q[1] - r, q[0] + r, q[1] + r), fill=fill)

    def path(self, pts, width=12, fill=INK):
        for a, b in zip(pts, pts[1:]):
            self.line(a, b, width, fill)

    def circle(self, c, r, fill=None, outline=None, width=0):
        x, y = self.p(*c)
        R = r * SS
        self.d.ellipse((x - R, y - R, x + R, y + R), fill=fill, outline=outline, width=int(width * SS))

    def ellipse(self, box, fill=None, outline=None, width=0):
        (x0, y0), (x1, y1) = self.p(box[0], box[1]), self.p(box[2], box[3])
        self.d.ellipse((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), fill=fill, outline=outline, width=int(width * SS))

    def rrect(self, box, radius=12, fill=None, outline=None, width=0):
        (x0, y0), (x1, y1) = self.p(box[0], box[1]), self.p(box[2], box[3])
        self.d.rounded_rectangle((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), radius=radius * SS,
                                 fill=fill, outline=outline, width=int(width * SS))

    def rect(self, box, fill=None, outline=None, width=0):
        self.rrect(box, 0, fill=fill, outline=outline, width=width)

    def poly(self, pts, fill=None, outline=None, width=0):
        q = [self.p(*pt) for pt in pts]
        if fill is not None:
            self.d.polygon(q, fill=fill)
        if outline is not None:
            self.d.line(q + [q[0]], fill=outline, width=int(width * SS), joint="curve")

    def arc(self, box, start, end, width=7, fill=INK):
        (x0, y0), (x1, y1) = self.p(box[0], box[1]), self.p(box[2], box[3])
        self.d.arc((x0, y0, x1, y1), start, end, fill=fill, width=max(1, int(width * SS)))

    def pie(self, box, start, end, fill=INK):
        (x0, y0), (x1, y1) = self.p(box[0], box[1]), self.p(box[2], box[3])
        self.d.pieslice((x0, y0, x1, y1), start, end, fill=fill)

    def text(self, xy, s, fnt, size, fill=INK, anchor="mm", stroke=0, stroke_fill=WHITE):
        size = int(size * SS)
        if size < 4:
            return
        kw = {"stroke_width": int(stroke * SS), "stroke_fill": stroke_fill} if stroke else {}
        self.d.text(self.p(*xy), s, font=font(fnt, size), fill=fill, anchor=anchor, **kw)

    def done(self) -> Image.Image:
        return self.im.resize((int(self.w), int(self.h)), Image.BOX)


# ======================================================================= the rig
BASE = {"thigh": 112, "shin": 112, "torso": 175, "head": 64, "uarm": 100, "farm": 96}
LW = 13

# hand targets relative to the neck (back arm, front arm) for a figure facing right. y grows downward.
POSE_HANDS = {
    "idle": ((-50, 180), (50, 180)),
    "talk": ((-50, 180), (120, 40)),
    "point": ((-50, 180), (210, 0)),
    "shrug": ((-150, 40), (150, 40)),
    "facepalm": ((-50, 180), (20, -70)),
    "think": ((-36, 104), (30, -16)),
    "cheer": ((-120, -150), (120, -150)),
    "panic": ((-110, -170), (110, -170)),
    "hips": ((-86, 128), (86, 128)),
    "wave": ((-50, 180), (106, -118)),
    "show": ((-50, 180), (150, 30)),
    "walk": ((-64, 156), (64, 156)),
    "sip": ((-50, 180), (34, -30)),
    "cross": ((40, 90), (-40, 90)),
}
POSES = list(POSE_HANDS)
POSE_LEAN = {"panic": -5, "point": 5, "talk": 2, "think": -2}
ELBOW_OUT = {"shrug", "hips", "panic", "cheer", "facepalm", "cross"}


def ik(a, b, l1, l2, side):
    """Two bone chain from a to b, returns the middle joint. side picks which way the elbow or knee bends."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = min(max(1e-6, math.hypot(dx, dy)), l1 + l2 - 1.0)
    d = max(d, abs(l1 - l2) + 1.0)
    base = math.atan2(dy, dx)
    ang = math.acos(max(-1.0, min(1.0, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d))))
    th = base + side * ang
    return (a[0] + l1 * math.cos(th), a[1] + l1 * math.sin(th))


def ik_out(a, b, l1, l2, cx):
    c1, c2 = ik(a, b, l1, l2, 1), ik(a, b, l1, l2, -1)
    return c1 if abs(c1[0] - cx) >= abs(c2[0] - cx) else c2


def skeleton(cx, gy, pose, t, flip=1, s=1.0, hop=0.0, talking=0.0):
    """Every joint of one figure at time t. flip=1 faces right, -1 faces left. s = size."""
    L = {k: v * s for k, v in BASE.items()}
    p = pose if pose in POSE_HANDS else "idle"
    lean = math.radians(POSE_LEAN.get(p, 0) * flip)
    breath = math.sin(t * 2.6 + cx) * 3.0 * s
    if p == "walk":
        ph = t * 7.5
        step, lift = 56 * s, 32 * s
        feet = [(-step * math.sin(ph), -max(0.0, math.cos(ph)) * lift), (step * math.sin(ph), -max(0.0, -math.cos(ph)) * lift)]
    else:
        feet = [(-36 * s, 0), (36 * s, 0)]
    if p == "cheer":
        hop += abs(math.sin(t * 6.0)) * 22 * s
    hip = (cx, gy - (L["thigh"] + L["shin"]) * 0.95 - hop + breath * 0.4)
    neck = (hip[0] + math.sin(lean) * L["torso"], hip[1] - math.cos(lean) * L["torso"] + breath)
    head = (neck[0] + math.sin(lean) * (L["head"] + 6 * s), neck[1] - math.cos(lean) * (L["head"] + 6 * s))
    legs = []
    for k, (fx, fy) in enumerate(feet):
        foot = (cx + fx * flip, gy - hop + fy)
        hp = (hip[0] + (k * 2 - 1) * 7 * s, hip[1])
        legs.append((hp, ik(hp, foot, L["thigh"], L["shin"], 1 if flip == 1 else -1), foot))
    arms = []
    for k, (hx, hy) in enumerate(POSE_HANDS[p]):
        hx, hy = hx * s, hy * s
        if p == "talk" and k == 1:          # the talking hand moves with the voice
            hx += math.sin(t * 7.0) * 26 * s * (0.4 + talking)
            hy += math.cos(t * 5.0) * 30 * s * (0.4 + talking)
        if p == "wave" and k == 1:
            hx += math.sin(t * 11.0) * 30 * s
        if p == "panic":
            hx += math.sin(t * 13.0 + k * 2) * 40 * s
            hy += math.cos(t * 15.0 + k) * 20 * s
        if p == "shrug":
            hy -= abs(math.sin(t * 3.4)) * 14 * s
        if p == "walk":
            hy += math.sin(t * 7.5 + k * math.pi) * 22 * s
        if p in ("idle", "think", "sip"):
            hx += math.sin(t * 2.2 + k) * 3 * s
        shoulder = (neck[0] + (-1 if k == 0 else 1) * 4 * s * flip, neck[1] + 8 * s)
        target = (neck[0] + hx * flip, neck[1] + hy)
        if p in ELBOW_OUT:
            elbow = ik_out(shoulder, target, L["uarm"], L["farm"], neck[0])
        else:
            elbow = ik(shoulder, target, L["uarm"], L["farm"], (1 if k == 0 else -1) * flip)
        arms.append((shoulder, elbow, target))
    return {"hip": hip, "neck": neck, "head": head, "legs": legs, "arms": arms, "flip": flip, "pose": p, "s": s, "r": L["head"]}


# ======================================================================= faces
FACES = ["neutral", "happy", "laugh", "shocked", "worried", "angry", "smug", "sad", "confused", "hungry", "sleepy"]


def draw_face(pen: Pen, c, r, face, t, mouth=0.0, flip=1, speaking=False):
    """Face scaled to head radius r. mouth = 0..1 loudness of the voice at this frame."""
    k = r / 64.0
    x, y = c
    fx = flip * 6 * k                     # the face looks a little toward where the figure faces
    ex = 22 * k
    blink = (t % 3.4) < 0.11
    lw = max(3, 6 * k)
    m = clamp01(mouth)

    def eyes(size=7):
        if blink:
            for sgn in (-1, 1):
                pen.line((x + sgn * ex + fx - 8 * k, y - 6 * k), (x + sgn * ex + fx + 8 * k, y - 6 * k), lw)
        else:
            for sgn in (-1, 1):
                pen.circle((x + sgn * ex + fx, y - 6 * k), size * k, fill=INK)

    def brow(a, b):
        pen.line((x + a[0] * k + fx, y + a[1] * k), (x + b[0] * k + fx, y + b[1] * k), lw)

    def talk_mouth(w=12, base=4, amp=18):
        pen.ellipse((x + fx - w * k, y + 22 * k, x + fx + w * k, y + (26 + base + amp * m) * k), fill=INK)

    if face == "happy":
        for sgn in (-1, 1):
            pen.arc((x + sgn * ex + fx - 11 * k, y - 16 * k, x + sgn * ex + fx + 11 * k, y + 4 * k), 200, 340, lw)
        if speaking:
            talk_mouth(14, 6)
        else:
            pen.arc((x + fx - 20 * k, y + 4 * k, x + fx + 20 * k, y + 38 * k), 20, 160, lw)
    elif face == "laugh":
        for sgn in (-1, 1):
            e0 = x + sgn * ex + fx
            pen.line((e0 - 10 * k * sgn, y - 14 * k), (e0 + 7 * k * sgn, y - 6 * k), lw)
            pen.line((e0 - 10 * k * sgn, y + 2 * k), (e0 + 7 * k * sgn, y - 6 * k), lw)
        pen.pie((x + fx - 22 * k, y + 6 * k, x + fx + 22 * k, y + (46 + 6 * math.sin(t * 22)) * k), 0, 180, fill=INK)
    elif face == "shocked":
        for sgn in (-1, 1):
            pen.circle((x + sgn * ex + fx, y - 8 * k), 12 * k, fill=WHITE, outline=INK, width=lw * 0.8)
            pen.circle((x + sgn * ex + fx + 2 * k * flip, y - 8 * k), 4.5 * k, fill=INK)
        brow((-36, -34), (-12, -40))
        brow((12, -40), (36, -34))
        pen.ellipse((x + fx - 10 * k, y + 20 * k, x + fx + 10 * k, y + (46 + 8 * m) * k), fill=INK)
    elif face == "worried":
        eyes()
        brow((-36, -26), (-12, -34))
        brow((12, -34), (36, -26))
        if speaking:
            talk_mouth(11, 4)
        else:
            pen.path([(x + fx - 16 * k, y + 32 * k), (x + fx - 6 * k, y + 26 * k), (x + fx + 6 * k, y + 32 * k), (x + fx + 16 * k, y + 26 * k)], lw * 0.9)
    elif face == "angry":
        eyes()
        brow((-38, -30), (-10, -20))
        brow((10, -20), (38, -30))
        if speaking:
            talk_mouth(14, 4, 20)
        else:
            pen.line((x + fx - 16 * k, y + 32 * k), (x + fx + 16 * k, y + 32 * k), lw)
    elif face == "smug":
        for sgn in (-1, 1):
            pen.circle((x + sgn * ex + fx, y - 4 * k), 6.5 * k, fill=INK)
            pen.line((x + sgn * ex + fx - 11 * k, y - 13 * k), (x + sgn * ex + fx + 11 * k, y - 13 * k), lw)
        if speaking:
            talk_mouth(12, 4)
        else:
            pen.arc((x + fx - 18 * k, y + 10 * k, x + fx + 22 * k, y + 36 * k), 20, 130, lw)
    elif face == "sad":
        eyes()
        brow((-36, -32), (-12, -26))
        brow((12, -26), (36, -32))
        if speaking:
            talk_mouth(10, 3, 14)
        else:
            pen.arc((x + fx - 18 * k, y + 28 * k, x + fx + 18 * k, y + 52 * k), 200, 340, lw)
        pen.ellipse((x - ex - 6 * k, y + 4 * k, x - ex + 4 * k, y + (22 + (t * 30) % 14) * k), fill=(110, 170, 240))
    elif face == "confused":
        eyes()
        brow((-36, -30), (-12, -30))
        brow((12, -44), (36, -34))
        if speaking:
            talk_mouth(10, 3)
        else:
            pen.path([(x + fx - 14 * k, y + 30 * k), (x + fx, y + 26 * k), (x + fx + 14 * k, y + 32 * k)], lw * 0.9)
    elif face == "hungry":
        for sgn in (-1, 1):
            pen.circle((x + sgn * ex + fx, y - 8 * k), 10 * k, fill=WHITE, outline=INK, width=lw * 0.7)
            pen.circle((x + sgn * ex + fx, y - 10 * k), 5 * k, fill=INK)
        if speaking:
            talk_mouth(13, 6)
        else:
            pen.arc((x + fx - 20 * k, y + 4 * k, x + fx + 20 * k, y + 38 * k), 20, 160, lw)
        drip = (t * 0.8) % 1.0
        pen.ellipse((x + fx + 12 * k, y + 32 * k, x + fx + 20 * k, y + (40 + 22 * drip) * k), fill=(140, 200, 255))
    elif face == "sleepy":
        for sgn in (-1, 1):
            pen.arc((x + sgn * ex + fx - 11 * k, y - 14 * k, x + sgn * ex + fx + 11 * k, y + 4 * k), 20, 160, lw)
        pen.circle((x + fx, y + 30 * k), (5 + 3 * math.sin(t * 2)) * k, outline=INK, width=lw * 0.8)
    else:  # neutral
        eyes()
        if speaking:
            talk_mouth()
        else:
            pen.line((x + fx - 13 * k, y + 30 * k), (x + fx + 13 * k, y + 30 * k), lw)


# ======================================================================= the three characters
def _col(who):
    return tuple(config.CAST.get(who, {}).get("color", (200, 80, 60)))


def draw_character(pen: Pen, who: str, sk: dict, face: str, t: float, mouth=0.0, speaking=False, prop="none"):
    s, flip, r = sk["s"], sk["flip"], sk["r"]
    col = _col(who)
    lw = LW * max(0.8, s)
    n, hp, hc = sk["neck"], sk["hip"], sk["head"]
    # legs
    for hpt, knee, foot in sk["legs"]:
        pen.path([hpt, knee, foot], lw)
        pen.line(foot, (foot[0] + 22 * s * flip, foot[1]), lw)
    # torso
    if who == "golu":  # a round belly
        bw = 62 * s
        cy = hp[1] - (hp[1] - n[1]) * 0.42
        pen.ellipse((hp[0] - bw, n[1] + 18 * s, hp[0] + bw * 1.05, hp[1] + 14 * s), fill=(250, 250, 244), outline=INK, width=lw)
        pen.arc((hp[0] - 10 * s, cy, hp[0] + 6 * s, cy + 14 * s), 0, 360, max(2, 4 * s))  # navel
    else:
        pen.line(hp, n, lw)
    # what each one wears at the neck and shoulder
    if who == "pappu":  # saffron gamcha around the neck, ends flying
        pen.line((n[0] - 26 * s, n[1] + 6 * s), (n[0] + 26 * s, n[1] + 6 * s), 16 * s, fill=col)
        sw = math.sin(t * 4.0) * 6 * s
        pen.poly([(n[0] - 12 * s * flip, n[1] + 10 * s), (n[0] - 46 * s * flip, n[1] + 52 * s + sw),
                  (n[0] - 28 * s * flip, n[1] + 66 * s + sw), (n[0] - 2 * s * flip, n[1] + 16 * s)], fill=col)
        for yy in (30, 44):
            pen.line((n[0] - 22 * s * flip, n[1] + yy * s + sw * 0.5), (n[0] - 36 * s * flip, n[1] + (yy + 10) * s + sw * 0.5), 3 * s, fill=mix(col, INK, 0.35))
    if who == "chhotu":  # blue towel over one shoulder
        pen.poly([(n[0] - 22 * s, n[1] + 2 * s), (n[0] + 4 * s, n[1] - 2 * s), (n[0] + 2 * s, n[1] + 70 * s), (n[0] - 24 * s, n[1] + 76 * s)],
                 fill=col, outline=INK, width=4 * s)
    # arms, the prop goes in the front hand
    for k, (sh, el, ha) in enumerate(sk["arms"]):
        pen.path([sh, el, ha], lw)
        pen.circle(ha, 8 * s, fill=INK)
    if prop and prop != "none":
        draw_prop(pen, prop, sk["arms"][1][2], s, flip, t)
    # head
    pen.circle(hc, r, fill=SKIN if who == "golu" else WHITE, outline=INK, width=lw)
    if who == "golu":  # green topi and rosy cheeks
        pen.pie((hc[0] - r * 0.92, hc[1] - r * 1.25, hc[0] + r * 0.92, hc[1] - r * 0.25), 180, 360, fill=col)
        pen.line((hc[0] - r * 0.92, hc[1] - r * 0.74), (hc[0] + r * 0.92, hc[1] - r * 0.74), 5 * s, fill=mix(col, INK, 0.4))
        pen.circle(hc, r, outline=INK, width=lw)
        for sgn in (-1, 1):
            pen.circle((hc[0] + sgn * r * 0.55 + flip * 4 * s, hc[1] + r * 0.18), r * 0.15, fill=(255, 160, 170))
    draw_face(pen, hc, r, face, t, mouth, flip, speaking)
    if who == "pappu":  # spiky hair and a thin moustache
        for dx in (-30, -15, 0, 15, 30):
            base = (hc[0] + dx * s, hc[1] - r * math.cos(math.radians(dx * 1.4)) + 4 * s)
            pen.line(base, (base[0] + dx * 0.45 * s + flip * 6 * s, base[1] - 26 * s), 7 * s)
        my = hc[1] + r * 0.30
        pen.arc((hc[0] + flip * 6 * s - 22 * s, my - 6 * s, hc[0] + flip * 6 * s, my + 10 * s), 190, 330, 5 * s)
        pen.arc((hc[0] + flip * 6 * s, my - 6 * s, hc[0] + flip * 6 * s + 22 * s, my + 10 * s), 210, 350, 5 * s)
    if who == "chhotu":  # headband
        pen.arc((hc[0] - r, hc[1] - r * 0.95, hc[0] + r, hc[1] + r * 0.55), 195, 345, 12 * s, fill=col)
        pen.poly([(hc[0] - flip * r * 0.9, hc[1] - r * 0.45), (hc[0] - flip * (r * 0.9 + 30 * s), hc[1] - r * 0.25 + math.sin(t * 5) * 4 * s),
                  (hc[0] - flip * (r * 0.9 + 26 * s), hc[1] - r * 0.05)], fill=col)


# ======================================================================= props in the hand
PROPS = ["none", "chai", "phone", "samosa", "book", "kettle", "bat", "note", "umbrella", "kite", "jalebi"]


def draw_prop(pen: Pen, kind: str, hand, s: float, flip: int, t: float):
    x, y = hand
    if kind == "chai":  # cutting chai glass
        pen.poly([(x - 16 * s, y - 40 * s), (x + 16 * s, y - 40 * s), (x + 12 * s, y + 6 * s), (x - 12 * s, y + 6 * s)], fill=(255, 255, 255), outline=INK, width=4 * s)
        pen.poly([(x - 14 * s, y - 26 * s), (x + 14 * s, y - 26 * s), (x + 12 * s, y + 4 * s), (x - 12 * s, y + 4 * s)], fill=(196, 128, 64))
        for i in range(2):
            ph = (t * 1.3 + i * 0.5) % 1.0
            pen.arc((x - 10 * s + i * 10 * s, y - (60 + 40 * ph) * s, x + 6 * s + i * 10 * s, y - (40 + 40 * ph) * s), 90, 270, 3 * s, fill=(170, 170, 170))
    elif kind == "phone":
        pen.rrect((x - 18 * s, y - 52 * s, x + 18 * s, y + 6 * s), 6 * s, fill=INK)
        pen.rrect((x - 13 * s, y - 46 * s, x + 13 * s, y - 2 * s), 3 * s, fill=(120, 210, 255))
    elif kind == "samosa":
        pen.poly([(x - 30 * s, y + 10 * s), (x + 30 * s, y + 10 * s), (x, y - 40 * s)], fill=(232, 170, 70), outline=INK, width=4 * s)
        pen.line((x - 10 * s, y - 4 * s), (x + 4 * s, y - 18 * s), 3 * s, fill=(180, 110, 40))
    elif kind == "jalebi":
        for i, rr in enumerate((26, 18, 10)):
            pen.circle((x, y - 22 * s), rr * s, outline=(240, 150, 20), width=7 * s)
    elif kind == "book":
        pen.rrect((x - 34 * s, y - 50 * s, x + 34 * s, y + 4 * s), 4 * s, fill=(210, 60, 60), outline=INK, width=4 * s)
        pen.line((x, y - 50 * s), (x, y + 4 * s), 3 * s)
    elif kind == "kettle":
        pen.ellipse((x - 34 * s, y - 20 * s, x + 34 * s, y + 40 * s), fill=(200, 200, 205), outline=INK, width=4 * s)
        pen.line((x + 30 * s * flip, y), (x + 56 * s * flip, y - 20 * s), 7 * s, fill=(170, 170, 175))
        pen.arc((x - 22 * s, y - 44 * s, x + 22 * s, y - 4 * s), 180, 360, 5 * s)
    elif kind == "bat":
        pen.line((x, y), (x + 20 * s * flip, y - 30 * s), 8 * s, fill=(120, 80, 40))
        pen.poly([(x + 16 * s * flip, y - 26 * s), (x + 32 * s * flip, y - 38 * s), (x + 96 * s * flip, y - 150 * s), (x + 78 * s * flip, y - 160 * s)],
                 fill=(236, 200, 140), outline=INK, width=4 * s)
    elif kind == "note":
        pen.rrect((x - 40 * s, y - 40 * s, x + 40 * s, y + 2 * s), 3 * s, fill=(170, 220, 160), outline=INK, width=4 * s)
        pen.text((x, y - 19 * s), "Rs", "DejaVuSans-Bold.ttf", 20 * s)
    elif kind == "umbrella":
        pen.line((x, y), (x, y - 150 * s), 5 * s)
        pen.pie((x - 90 * s, y - 210 * s, x + 90 * s, y - 90 * s), 180, 360, fill=(60, 60, 200))
    elif kind == "kite":
        pen.poly([(x + 60 * s * flip, y - 190 * s), (x + 100 * s * flip, y - 150 * s), (x + 60 * s * flip, y - 100 * s), (x + 20 * s * flip, y - 150 * s)],
                 fill=(240, 60, 120), outline=INK, width=4 * s)
        pen.line((x, y), (x + 60 * s * flip, y - 100 * s), 2 * s)


# ======================================================================= small effects above a head
FX = ["none", "exclaim", "question", "sweat", "stars", "hearts", "anger", "idea", "zzz", "laugh"]


def draw_fx(pen: Pen, kind: str, head, r, t: float, age: float):
    if kind in (None, "", "none"):
        return
    x, y = head[0], head[1] - r - 40
    pop = ease_out_back(age / 0.35)
    if kind == "exclaim":
        pen.text((x + 40, y - 10), "!", "Bangers.ttf", 90 * pop, fill=(230, 40, 40), stroke=4)
    elif kind == "question":
        pen.text((x + 40, y - 10), "?", "Bangers.ttf", 90 * pop, fill=(40, 90, 230), stroke=4)
    elif kind == "sweat":
        dy = (t * 60) % 30
        pen.ellipse((head[0] + r * 0.7, head[1] - r * 0.6 + dy, head[0] + r * 0.7 + 16, head[1] - r * 0.6 + 30 + dy), fill=(120, 190, 255), outline=INK, width=3)
    elif kind == "stars":
        for i in range(3):
            a = t * 4 + i * 2.1
            pen.text((head[0] + math.cos(a) * r * 1.2, head[1] - r - 6 + math.sin(a) * 14), "*", "Bangers.ttf", 52, fill=(255, 200, 0), stroke=3)
    elif kind == "hearts":
        for i in range(2):
            ph = (t * 0.7 + i * 0.5) % 1.0
            pen.text((x - 20 + i * 50, y + 20 - ph * 80), "<3", "Bangers.ttf", 44, fill=(240, 60, 110), stroke=3)
    elif kind == "anger":
        pen.text((x + 46, y + 10), "#", "Bangers.ttf", 70 * pop, fill=(230, 40, 40), stroke=3)
        if int(t * 8) % 2 == 0:
            pen.circle((head[0], head[1]), r + 6, outline=(255, 90, 90), width=5)
    elif kind == "idea":
        pen.circle((x + 30, y - 20), 26 * pop, fill=(255, 230, 80), outline=INK, width=4)
        for a in range(0, 360, 45):
            ra = math.radians(a)
            pen.line((x + 30 + math.cos(ra) * 36, y - 20 + math.sin(ra) * 36), (x + 30 + math.cos(ra) * 48, y - 20 + math.sin(ra) * 48), 4, fill=(255, 190, 0))
    elif kind == "zzz":
        for i in range(3):
            ph = (t * 0.6 + i * 0.33) % 1.0
            pen.text((x + 30 + ph * 50, y - ph * 70), "z", "Bangers.ttf", 30 + 20 * ph, fill=(80, 80, 160), stroke=3)
    elif kind == "laugh":
        pen.text((x + 10, y - 6 + math.sin(t * 18) * 6), "HAHA", "Bangers.ttf", 58 * pop, fill=(255, 120, 0), stroke=4)
