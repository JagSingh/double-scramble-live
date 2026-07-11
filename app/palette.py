# (c) 2026 jag.m.singh@gmail.com
"""Dynamic palette engine.

Frank Stella's *Double Scramble* is two side-by-side squares of concentric
bands: one panel steps through its values in order, the other "scrambles"
the same sequence. We honour that: panel A gets an ordered lightness ramp,
panel B gets a scrambled permutation of a related hue family.

Palettes are generated, never looped:
- the base hue advances by the golden-ratio conjugate each transition
  (an irrational rotation - the hue sequence never revisits itself),
- each aircraft's ICAO hex + nanosecond clock seeds per-palette jitter,
- scheme (analogous / split-complement / soft triad), saturation band and
  ramp direction are drawn fresh every time.

Saturation and lightness ranges are tuned to the soft, balanced feel of
curated palettes (canva.com/colors/color-palettes): mid saturation,
generous lightness spread, nothing neon, nothing muddy.
"""
import colorsys
import random
import time

GOLDEN_CONJUGATE = 0.6180339887498949


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class PaletteEngine:
    def __init__(self, bands_per_panel: int):
        self.n = bands_per_panel
        self.hue = random.random()
        self._scramble_rng = random.Random()

    def next_palette(self, seed_material: str = "", leap: bool = True):
        """Return (bg, panel_a, panel_b) - lists of float RGB triples.

        leap=True  (treble planes): base hue jumps by the golden-ratio
                   conjugate - a new colour family entirely.
        leap=False (bass planes): base hue drifts a small step - the piece
                   moves, but stays inside the current family, keeping the
                   melody planes as the moments of real transformation.
        """
        rng = random.Random(f"{seed_material}:{time.time_ns()}")
        if leap:
            # Irrational hue walk + tiny seeded drift -> never repeats.
            self.hue = (self.hue + GOLDEN_CONJUGATE + rng.uniform(-0.02, 0.02)) % 1.0
        else:
            self.hue = (self.hue + rng.uniform(0.03, 0.07)) % 1.0
        base = self.hue

        # Bass drifts stay analogous - a split-complement or triad draw
        # would lurch the second panel across the wheel, which is a leap
        # in all but name. Treble keeps the full scheme vocabulary.
        scheme = rng.choice(["analogous", "split", "triad"]) if leap \
            else "analogous"
        if scheme == "analogous":
            hue_a, hue_b = base, (base + rng.uniform(0.05, 0.10)) % 1.0
        elif scheme == "split":
            hue_a, hue_b = base, (base + 0.5 + rng.uniform(-0.06, 0.06)) % 1.0
        else:
            hue_a, hue_b = base, (base + rng.choice([1, -1]) / 3.0) % 1.0

        sat_lo = rng.uniform(0.22, 0.38)
        sat_hi = _clamp(sat_lo + rng.uniform(0.12, 0.28))
        l_lo, l_hi = rng.uniform(0.26, 0.34), rng.uniform(0.78, 0.88)
        ascending = rng.random() < 0.5

        def ramp(hue, k):
            """k in [0,1] -> pleasing colour along the lightness ramp."""
            l = l_lo + (l_hi - l_lo) * (k if ascending else 1 - k)
            s = sat_lo + (sat_hi - sat_lo) * (1 - abs(2 * k - 1))  # richest mid-ramp
            h = (hue + 0.04 * (k - 0.5)) % 1.0                     # gentle hue drift
            r, g, b = colorsys.hls_to_rgb(h, l, s)
            return (r, g, b)

        ks = [i / (self.n - 1) for i in range(self.n)]
        panel_a = [ramp(hue_a, k) for k in ks]

        # Panel B: same family, scrambled order (the "double scramble").
        order = list(range(self.n))
        self._scramble_rng.seed(rng.random())
        self._scramble_rng.shuffle(order)
        panel_b = [ramp(hue_b, ks[i]) for i in order]

        # Background: deep, desaturated cousin of the base hue.
        bg = colorsys.hls_to_rgb(base, 0.09, 0.18)
        return list(bg), panel_a, panel_b
