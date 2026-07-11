# (c) 2026 jag.m.singh@gmail.com
"""Flight-number overlay.

Each aircraft that triggers a melody note + palette transition leaves its
flight number (or ICAO hex, when the callsign wasn't broadcast) in a
vertical column at the left edge of the frame: newest at the top, older
entries sliding down one slot, the oldest fading out and dropping off.

Text is rasterized once per event into a small alpha sprite (PIL), then
composited onto the numpy frame each tick - so the per-frame cost is a
handful of tiny array blends, not text rendering.
"""
import numpy as np

from PIL import Image, ImageDraw, ImageFont

MARGIN_X = 28
TOP_Y = 26
SLOT_H = 36
MAX_VISIBLE = 6
FONT_SIZE = 22
TEXT_RGB = np.array([235.0, 235.0, 228.0])  # warm off-white
FADE_SECONDS = 1.2       # drop-off fade for the entry leaving the screen
EASE_RATE = 6.0          # position easing (higher = snappier slide)


def _load_font():
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, FONT_SIZE)
        except OSError:
            continue
    return ImageFont.load_default()


_FONT = _load_font()


def _rasterize(label: str) -> np.ndarray:
    """Return a float alpha mask (h, w) in [0, 1] for the label text."""
    dummy = Image.new("L", (1, 1))
    x0, y0, x1, y1 = ImageDraw.Draw(dummy).textbbox((0, 0), label, font=_FONT)
    img = Image.new("L", (x1 - x0 + 4, y1 - y0 + 4), 0)
    ImageDraw.Draw(img).text((2 - x0, 2 - y0), label, fill=255, font=_FONT)
    return np.asarray(img, dtype=np.float64) / 255.0


class _Entry:
    __slots__ = ("sprite", "y", "alpha", "dying_since")

    def __init__(self, label, y):
        self.sprite = _rasterize(label)
        self.y = float(y)
        self.alpha = 0.0        # fades in on arrival
        self.dying_since = None  # set when pushed off the list


class FlightOverlay:
    """One column of labels. Anchor with x + align:
    align="left"  -> text starts x px from the left edge (newest on top)
    align="right" -> text ends x px from the right edge
    base_level scales the whole column's opacity (the bass column runs
    quieter than the treble one so the melody planes stay the headline).
    """

    def __init__(self, x=MARGIN_X, align="left", base_level=0.95):
        self.x = x
        self.align = align
        self.base_level = base_level
        self.entries = []
        self._last_t = None

    def push(self, label: str, now: float):
        # new entries arrive at the top slot, slightly above, and settle in
        self.entries.insert(0, _Entry(label.strip() or "------", TOP_Y - 18))
        for i, e in enumerate(self.entries):
            if i >= MAX_VISIBLE and e.dying_since is None:
                e.dying_since = now

    def apply(self, frame: np.ndarray, now: float):
        """Composite entries onto the frame in place."""
        if not self.entries:
            self._last_t = now
            return
        dt = 0.0 if self._last_t is None else max(0.0, now - self._last_t)
        self._last_t = now

        h, w, _ = frame.shape
        ease = min(1.0, EASE_RATE * dt)
        survivors = []
        for i, e in enumerate(self.entries):
            # slide toward this slot; a dying entry keeps drifting down
            target_y = TOP_Y + min(i, MAX_VISIBLE) * SLOT_H
            e.y += (target_y - e.y) * ease

            if e.dying_since is not None:
                fade = 1.0 - (now - e.dying_since) / FADE_SECONDS
                if fade <= 0.0:
                    continue  # dropped off the screen
                level = fade
            else:
                e.alpha = min(1.0, e.alpha + dt / 0.4)  # 0.4 s fade-in
                level = e.alpha
            survivors.append(e)

            # older entries sit progressively quieter
            level *= self.base_level * (0.85 ** min(i, MAX_VISIBLE))

            sh, sw = e.sprite.shape
            y = int(e.y)
            x0 = self.x if self.align == "left" else w - self.x - sw
            if y < 0 or y + sh > h or x0 < 0 or x0 + sw > w:
                continue
            a = (e.sprite * level)[..., None]           # (sh, sw, 1)
            region = frame[y:y + sh, x0:x0 + sw]
            region[:] = (region * (1.0 - a) + TEXT_RGB * a).astype(np.uint8)
        self.entries = survivors


class ClockOverlay:
    """Local time, bottom-right. A ticking clock is quiet proof of
    liveness - the one element of the frame that changes every second
    regardless of the sky. Rasterized only when the string changes
    (once per second), composited every frame like the flight columns."""

    def __init__(self, fmt=None, margin=28, level=0.55):
        import time as _time
        from . import config as _config
        self._time = _time
        self.fmt = fmt or _config.CLOCK_FORMAT
        self.margin = margin
        self.level = level
        self._label = None
        self._sprite = None

    def apply(self, frame):
        label = self._time.strftime(self.fmt)
        if label != self._label:
            self._label = label
            self._sprite = _rasterize(label)
        sh, sw = self._sprite.shape
        h, w, _ = frame.shape
        x0, y0 = w - self.margin - sw, h - self.margin - sh
        if x0 < 0 or y0 < 0:
            return
        a = (self._sprite * self.level)[..., None]
        region = frame[y0:y0 + sh, x0:x0 + sw]
        region[:] = (region * (1.0 - a) + TEXT_RGB * a).astype(np.uint8)
