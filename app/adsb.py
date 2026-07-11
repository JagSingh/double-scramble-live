# (c) 2026 jag.m.singh@gmail.com
"""ADS-B ingest.

Polls dump1090-mutability's aircraft.json (mounted read-only into the
container). A "new plane" event fires the first time an ICAO hex appears,
and again only if it has been out of sight for DEDUPE_SECONDS - a jet
loitering overhead triggers once, not every second.

Classification by emitter category:
  A3/A4/A5/A6 (large, B757, heavy, high-performance)  -> TREBLE
  A0/A1/A2/A7, gliders, balloons, surface, or missing -> BASS

Demo mode fabricates plausible traffic so the piece can be developed,
smoke-tested in CI, and demoed without an SDR attached.
"""
import json
import os
import random
import time

from . import config


class PlaneEvent:
    __slots__ = ("hexid", "category", "kind", "flight")

    def __init__(self, hexid, category, flight=""):
        self.hexid = hexid
        self.category = category or "??"
        self.flight = flight.strip()
        self.kind = "treble" if category in config.TREBLE_CATEGORIES else "bass"

    def __repr__(self):
        return f"<{self.kind} {self.hexid} cat={self.category} {self.flight}>"


class AdsbWatcher:
    def __init__(self, path=config.ADSB_JSON):
        self.path = path
        self.seen = {}     # hex -> last sighting timestamp (already triggered)
        self.pending = {}  # hex -> first sighting timestamp (still maturing)
        self._warned_missing = False

    def poll(self):
        now = time.time()
        try:
            with open(self.path) as fh:
                data = json.load(fh)
            self._warned_missing = False
        except (OSError, json.JSONDecodeError):
            if not self._warned_missing:
                print(f"[adsb] cannot read {self.path} (waiting for dump1090)",
                      flush=True)
                self._warned_missing = True
            return []

        events = []
        for ac in data.get("aircraft", []):
            hexid = ac.get("hex")
            if not hexid:
                continue

            last = self.seen.get(hexid)
            if last is not None:
                if (now - last) <= config.DEDUPE_SECONDS:
                    self.seen[hexid] = now   # still the same visit; refresh
                    continue
                del self.seen[hexid]         # long gone and back; start fresh

            first = self.pending.get(hexid)
            if first is None:
                # First sighting. dump1090 fills the record incrementally -
                # category and flight often arrive seconds after the hex -
                # so hold the aircraft in `pending` rather than firing now
                # and misreading a heavy as light.
                self.pending[hexid] = now
                continue

            complete = bool(ac.get("category")) and bool(ac.get("flight"))
            if complete or (now - first) >= config.MATURE_SECONDS:
                events.append(PlaneEvent(hexid, ac.get("category"),
                                         ac.get("flight", "")))
                self.seen[hexid] = now
                del self.pending[hexid]

        # aircraft that vanished before their record matured
        stale = [h for h, t in self.pending.items()
                 if (now - t) > config.MATURE_SECONDS * 4]
        for h in stale:
            del self.pending[h]

        # keep the dedupe table from growing forever
        if len(self.seen) > 5000:
            cutoff = now - config.DEDUPE_SECONDS
            self.seen = {k: v for k, v in self.seen.items() if v > cutoff}
        return events


class DemoWatcher:
    """Fake sky: mostly light traffic, occasional heavies."""
    CATS = ["A1"] * 5 + ["A2"] * 3 + ["A7", "A3", "A3", "A4", "A5", None]

    def __init__(self):
        self._next = time.time() + 1.0

    def poll(self):
        now = time.time()
        if now < self._next:
            return []
        self._next = now + random.uniform(2.0, 12.0)
        hexid = f"{random.getrandbits(24):06x}"
        return [PlaneEvent(hexid, random.choice(self.CATS),
                           f"DEMO{random.randint(100, 999)}")]


def make_watcher():
    if config.DEMO or (config.SMOKE_TEST and not os.path.exists(config.ADSB_JSON)):
        print("[adsb] demo mode: synthesizing traffic", flush=True)
        return DemoWatcher()
    return AdsbWatcher()
