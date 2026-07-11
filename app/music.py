# (c) 2026 jag.m.singh@gmail.com
"""Erik Satie, Gymnopedie No. 1 - separated into treble (melody) and bass
(accompaniment) material.

The piece is not played on a timeline. Instead, two sequencers walk through
the material and the *sky* provides the rhythm: each heavy aircraft advances
the treble melody by one note, each light aircraft places the next bass
event (root + rolled chord). Over a quiet afternoon the piece assembles
itself; over a busy one it flows.
"""

# MIDI note numbers ------------------------------------------------------

def midi_to_freq(m: int) -> float:
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


# --- Treble clef: the famous melody (D major), bars 5 onward -----------
# F#5 A5 G5 F#5 | C#5 B4 C#5 D5 | A4 ... (phrases 1, 2, and the answering
# descending line). Encoded as (midi, relative_length) - length shapes the
# synth envelope, not wall-clock timing.
MELODY = [
    (78, 1), (81, 1), (79, 1), (78, 1), (73, 1), (71, 1), (73, 1), (74, 1), (69, 3),
    (78, 1), (81, 1), (79, 1), (78, 1), (73, 1), (71, 1), (73, 1), (74, 1), (69, 3),
    (73, 1), (78, 1), (76, 1), (74, 1), (73, 1), (71, 1), (69, 1), (71, 1),
    (73, 1), (74, 1), (76, 2), (74, 1), (73, 1), (74, 1), (69, 2),
    (71, 1), (73, 1), (74, 1), (76, 1), (78, 1), (79, 1), (78, 2),
    (71, 1), (74, 1), (73, 3),
]

# --- Bass clef: root + chord, the piece's swaying left hand ------------
# Gmaj7 / D6 alternation, then the later harmonic colours.
_G = (43, [59, 62, 66])    # G2  + B3 D4 F#4
_D = (38, [57, 61, 66])    # D2  + A3 C#4 F#4
_Em = (40, [59, 64, 67])   # E2  + B3 E4 G4
_A7 = (45, [61, 64, 67])   # A2  + C#4 E4 G4
_Bm = (47, [62, 66, 71])   # B2  + D4 F#4 B4
_Fsm = (42, [57, 61, 66])  # F#2 + A3 C#4 F#4 (F# minor)

BASS_PROGRESSION = [
    _G, _D, _G, _D, _G, _D, _G, _D,
    _Em, _A7, _D, _Bm,
    _Em, _Fsm, _G, _D,
]


class MelodySequencer:
    def __init__(self):
        self._i = 0

    def next(self):
        note, length = MELODY[self._i % len(MELODY)]
        self._i += 1
        return midi_to_freq(note), length


class BassSequencer:
    def __init__(self):
        self._i = 0

    def next(self):
        root, chord = BASS_PROGRESSION[self._i % len(BASS_PROGRESSION)]
        self._i += 1
        return midi_to_freq(root), [midi_to_freq(n) for n in chord]
