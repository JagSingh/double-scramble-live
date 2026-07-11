# (c) 2026 jag.m.singh@gmail.com
"""Block-based real-time synthesizer.

Voices are gentle additive tones (fundamental + a few fading partials) with
a felt-piano envelope: soft attack, long exponential release. An idle drone
(low G, its fifth, and a faint octave, breathing on a slow LFO) fades in
when the sky goes quiet. A dual-tap stereo echo gives everything the empty
gallery acoustic the piece deserves.

Audio is produced one video-frame at a time (1470 samples at 30 fps /
44.1 kHz), keeping picture and sound sample-locked.
"""
import numpy as np

from . import config

SR = config.SAMPLE_RATE
TWO_PI = 2.0 * np.pi

# Idle drone: G2 root, D3 fifth, G3 octave - matches the piece's G pedal.
# A faint G4 (392 Hz) is added and overall levels are raised ~3 dB because
# small laptop/desktop speakers roll off steeply below ~200 Hz: without a
# partial they can physically reproduce, the drone is nearly inaudible on
# them even though it measures fine. The 392 Hz octave gives small drivers
# something to latch onto while keeping the character of a low pedal tone.
DRONE_FREQS = (98.0, 146.83, 196.0, 392.0)
DRONE_AMPS = (0.070, 0.032, 0.022, 0.010)


class _Voice:
    __slots__ = ("freq", "start", "dur", "amp", "partials", "attack", "dead")

    def __init__(self, freq, start_sample, dur_seconds, amp,
                 partials=((1, 1.00), (2, 0.30), (3, 0.12), (4, 0.05)),
                 attack=0.012):
        self.freq = freq
        self.start = start_sample
        self.dur = dur_seconds
        self.amp = amp
        self.partials = partials
        self.attack = attack
        self.dead = False

    def render(self, block_start, n):
        rel = (np.arange(block_start, block_start + n) - self.start) / SR
        if rel[-1] < 0:
            return None
        rel = np.maximum(rel, 0.0)
        tau = max(self.dur / 3.0, 0.4)
        env = np.minimum(rel / self.attack, 1.0) * np.exp(-rel / tau)
        if rel[0] > self.dur and env.max() < 1e-4:
            self.dead = True
            return None
        out = np.zeros(n)
        for k, a in self.partials:
            # higher partials decay faster, like a struck string
            out += a * np.exp(-rel * 0.8 * k) * np.sin(TWO_PI * self.freq * k * rel)
        return out * env * self.amp


class Synth:
    def __init__(self):
        self.voices = []
        self.pos = 0  # absolute sample counter
        self.drone_level = 0.0
        self.drone_target = 0.0
        # dual-tap echo for stereo space
        self._echo_l = np.zeros(int(0.291 * SR))
        self._echo_r = np.zeros(int(0.377 * SR))
        self._ep_l = 0
        self._ep_r = 0

    # --- musical events -------------------------------------------------
    def melody_note(self, freq, length=1):
        dur = 2.5 + 1.2 * length
        self.voices.append(_Voice(freq, self.pos, dur, amp=0.20))
        # a whisper of the octave above, Satie's overtone shimmer
        self.voices.append(_Voice(freq * 2, self.pos + int(0.02 * SR),
                                  dur * 0.6, amp=0.03))

    def bass_event(self, root_freq, chord_freqs):
        self.voices.append(_Voice(root_freq, self.pos, 5.0, amp=0.16,
                                  partials=((1, 1.0), (2, 0.20), (3, 0.06)),
                                  attack=0.02))
        # rolled chord ~ a third of a beat later, gently arpeggiated
        for i, f in enumerate(chord_freqs):
            start = self.pos + int((0.30 + 0.055 * i) * SR)
            self.voices.append(_Voice(f, start, 3.5, amp=0.075))

    def set_idle(self, idle: bool):
        self.drone_target = 1.0 if idle else 0.0

    # --- rendering --------------------------------------------------------
    def _drone(self, n):
        t = np.arange(self.pos, self.pos + n) / SR
        breath = 0.75 + 0.25 * np.sin(TWO_PI * 0.045 * t)  # slow inhale/exhale
        out = np.zeros(n)
        for f, a in zip(DRONE_FREQS, DRONE_AMPS):
            out += a * np.sin(TWO_PI * f * t) \
                 + a * 0.5 * np.sin(TWO_PI * f * 1.003 * t)  # detune shimmer
        # smooth ~2.5 s fade so the hum never clicks in or out
        step = n / (2.5 * SR)
        new_level = float(np.clip(
            self.drone_level + np.clip(self.drone_target - self.drone_level,
                                       -step, step), 0.0, 1.0))
        ramp = np.linspace(self.drone_level, new_level, n)
        self.drone_level = new_level
        return out * breath * ramp

    def _echo(self, dry, buf, ptr):
        n = len(dry)
        idx = (ptr + np.arange(n)) % len(buf)
        wet = buf[idx]
        buf[idx] = dry + 0.42 * wet
        return dry + 0.30 * wet, (ptr + n) % len(buf)

    def render_frame(self):
        """Return one video frame's worth of interleaved stereo int16."""
        n = config.SAMPLES_PER_FRAME
        mix = self._drone(n)
        for v in self.voices:
            block = v.render(self.pos, n)
            if block is not None:
                mix += block
        self.voices = [v for v in self.voices if not v.dead]

        left, self._ep_l = self._echo(mix, self._echo_l, self._ep_l)
        right, self._ep_r = self._echo(mix, self._echo_r, self._ep_r)
        self.pos += n

        stereo = np.empty(2 * n)
        stereo[0::2] = np.tanh(left * 1.4)   # soft limiter
        stereo[1::2] = np.tanh(right * 1.4)
        return (stereo * 32000.0).astype(np.int16).tobytes()
