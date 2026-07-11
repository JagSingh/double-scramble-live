# (c) 2026 jag.m.singh@gmail.com
"""Central configuration, all overridable via environment variables."""
import os


def _f(name, default):
    return float(os.environ.get(name, default))


def _i(name, default):
    return int(os.environ.get(name, default))


# --- Video ---
WIDTH = _i("WIDTH", 1280)
HEIGHT = _i("HEIGHT", 720)
FPS = _i("FPS", 30)
BANDS_PER_PANEL = _i("BANDS", 8)          # concentric squares per panel
VIDEO_BITRATE = os.environ.get("VIDEO_BITRATE", "3000k")

# --- Audio ---
SAMPLE_RATE = 44100
SAMPLES_PER_FRAME = SAMPLE_RATE // FPS     # must divide evenly (44100/30 = 1470)

# --- Behaviour ---
TRANSITION_SECONDS = _f("TRANSITION_SECONDS", 4.0)   # colour cross-fade length
IDLE_SECONDS = _f("IDLE_SECONDS", 7.0)               # silence gap before hum/pulse
MIN_EVENT_GAP = _f("MIN_EVENT_GAP", 0.6)             # rate-limit bursts of planes
DEDUPE_SECONDS = _f("DEDUPE_SECONDS", 300)           # same hex won't retrigger for 5 min

# --- ADS-B ---
ADSB_JSON = os.environ.get("ADSB_JSON", "/adsb/aircraft.json")
POLL_SECONDS = _f("POLL_SECONDS", 1.0)
DEMO = os.environ.get("DEMO", "0") == "1"            # synthesize fake traffic

# Emitter categories (dump1090 "category" attribute).
# Heavier / rarer -> treble melody note + palette transition.
# Lighter / frequent (or missing) -> bass clef accompaniment.
TREBLE_CATEGORIES = {"A3", "A4", "A5", "A6"}
BASS_CATEGORIES = {"A0", "A1", "A2", "A7",
                   "B0", "B1", "B2", "B3", "B4", "B6", "C0", "C1", "C2", "C3"}

# --- Output ---
YOUTUBE_STREAM_KEY = os.environ.get("YOUTUBE_STREAM_KEY", "")
OUTPUT_URL = os.environ.get("OUTPUT_URL", "")        # explicit override (any ffmpeg sink)
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/output") # local HLS preview when no key
SMOKE_TEST = os.environ.get("SMOKE_TEST", "0") == "1"  # render a few seconds, then exit 0

# --- Record maturation ---
# dump1090 assembles aircraft.json incrementally: a hex appears first,
# category and flight arrive over the following seconds. Firing on first
# sight misclassifies heavies as light (category still null). A record is
# acted on as soon as it is complete (category AND flight present), or
# after MATURE_SECONDS with whatever has arrived - whichever comes first.
MATURE_SECONDS = _f("MATURE_SECONDS", 30)

# --- Clock overlay ---
CLOCK_FORMAT = os.environ.get("CLOCK_FORMAT", "%I:%M:%S %p")
