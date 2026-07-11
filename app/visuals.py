# (c) 2026 jag.m.singh@gmail.com
"""Frame renderer.

The geometry is computed once as a "band map": an integer per pixel saying
which concentric band (of which panel) it belongs to, or -1 for background.
Every frame is then a single LUT lookup - fast enough to hold 30 fps in
pure numpy at 720p with plenty of headroom.

Colour changes are never sudden: current -> target is eased with a
smoothstep over TRANSITION_SECONDS, interpolated in linear-light RGB so
the blend stays luminous instead of dipping through grey.
"""
import numpy as np

from . import config


def _build_band_map(w, h, bands):
    """Two side-by-side panels of concentric squares (Chebyshev rings)."""
    margin = int(h * 0.08)
    panel = min(h - 2 * margin, w // 2 - int(margin * 1.5))
    gap = w - 2 * panel
    cx_a = gap // 3 + panel // 2
    cx_b = w - gap // 3 - panel // 2
    cy = h // 2
    half = panel / 2.0
    band_w = half / bands

    yy, xx = np.mgrid[0:h, 0:w]
    band_map = np.full((h, w), -1, dtype=np.int16)

    for p, cx in enumerate((cx_a, cx_b)):
        cheb = np.maximum(np.abs(xx - cx), np.abs(yy - cy))
        inside = cheb < half
        idx = np.minimum((cheb / band_w).astype(np.int16), bands - 1)
        band_map[inside] = idx[inside] + p * bands
    return band_map


def _smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class Renderer:
    def __init__(self):
        self.bands = config.BANDS_PER_PANEL
        self.n_colors = 2 * self.bands + 1  # +1 for background at index 0
        self.band_map = _build_band_map(config.WIDTH, config.HEIGHT, self.bands)
        self.lut_index = (self.band_map + 1).astype(np.intp)

        # Colour state, in linear light. Start from a first palette.
        self.current = np.zeros((self.n_colors, 3), dtype=np.float64)
        self.target = np.zeros_like(self.current)
        self.t_start = -1e9
        self.duration = config.TRANSITION_SECONDS
        # Per-band phase offsets for the idle pulse. Bands within each panel
        # get phases proportional to their depth, so the brightness wave
        # visibly travels inward, ring by ring, toward the centre of each
        # square. Background (index 0) participates faintly (see scale).
        depth = np.arange(self.bands) * (2 * np.pi / self.bands)
        self.pulse_phase = np.concatenate(([0.0], -depth, -depth))
        self._pulse_scale = np.ones(self.n_colors)
        self._pulse_scale[0] = 0.35  # keep the background calm

    @staticmethod
    def _to_linear(srgb):
        return np.power(np.clip(srgb, 0, 1), 2.2)

    @staticmethod
    def _to_srgb(lin):
        return np.power(np.clip(lin, 0, 1), 1 / 2.2)

    def set_palette(self, bg, panel_a, panel_b, now, instant=False):
        stacked = np.array([bg] + panel_a + panel_b, dtype=np.float64)
        lin = self._to_linear(stacked)
        if instant:
            self.current = lin.copy()
        else:
            self.current = self._blended(now)  # freeze mid-transition state
        self.target = lin
        self.t_start = now

    def _blended(self, now):
        t = _smoothstep((now - self.t_start) / self.duration)
        return self.current * (1.0 - t) + self.target * t

    def render(self, now, idle_level=0.0):
        """idle_level in [0,1] fades the meditative pulse in and out."""
        colors = self._blended(now)
        if idle_level > 0.001:
            # Two superimposed waves, both travelling inward band-by-band:
            # a deep slow breath (+-18%, ~11 s cycle) carrying the motion,
            # and a gentler shimmer (+-5%, ~5 s cycle) riding on top of it -
            # enough glint to keep the surface alive without flicker.
            ph = self.pulse_phase
            breath = 0.18 * np.sin(2 * np.pi * 0.09 * now + ph)
            shimmer = 0.05 * np.sin(2 * np.pi * 0.20 * now + 2.6 * ph)
            pulse = 1.0 + idle_level * self._pulse_scale * (breath + shimmer)
            colors = colors * pulse[:, None]
        lut = (self._to_srgb(colors) * 255.0 + 0.5).astype(np.uint8)
        return lut[self.lut_index]  # (H, W, 3) uint8
