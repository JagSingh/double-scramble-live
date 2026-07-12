https://jagmsingh.com/Double-Scramble/Double-Scramble.html

# Double Scramble, Live

A 24/7 generative art livestream after Frank Stella's *Double Scramble* (Blanton Museum of Art), scored by Erik Satie's Gymnopédie No. 1 and conducted by the aircraft flying over the local antenna.

Two side-by-side panels of concentric squares hold the screen. A local dump1090 ADS-B receiver watches the sky. When a **heavy aircraft** appears (emitter category A3–A6), the next note of the Gymnopédie melody sounds and both panels dissolve — a four-second linear-light cross-fade — into a freshly generated palette. When a **light aircraft** appears (A0–A2, rotorcraft, gliders, or no category), the next bass event of the piece is laid down: a low root, then the chord rolled gently after it. When the sky is empty for a few seconds, the colors begin to breathe in a slow ripple and a low G-pedal drone hums until the next contact.

The melody and harmony are Satie's, in order; the *rhythm* is the sky's. Over a quiet night the piece assembles itself one contact at a time.

## Palettes that never repeat

The base hue advances by the golden-ratio conjugate (an irrational rotation of the color wheel, so the sequence never cycles), then each palette is jittered by a seed built from the aircraft's ICAO hex and the nanosecond clock. Scheme (analogous / split-complement / soft triad), saturation band, lightness ramp, and ramp direction are drawn fresh every time, tuned to the soft mid-saturation ranges of curated palettes. Panel A steps through its values in order; panel B scrambles the same family — Stella's double scramble.

## Design

```
dump1090 → /var/run/dump1090-mutability/aircraft.json  (host, read-only mount)
                     │ poll 1 Hz, dedupe by ICAO hex (5 min)
                     ▼
              adsb.py ── PlaneEvent(kind: treble | bass) ──▶ main loop
                                                              │
        music.py  (Gymnopédie treble/bass sequencers) ────────┤
        palette.py (golden-ratio, never-repeating palettes) ──┤
                                                              ▼
        synth.py  1470 samples/frame ─┐            visuals.py LUT render
        (voices + drone + echo)       │ named pipes  (numpy, 720p30)
                                      ▼                       │
                              ffmpeg (x264 + AAC) ◀───────────┘
                                      │
                       rtmp://a.rtmp.youtube.com/live2/KEY
```

Audio and video are generated frame-locked (44100 / 30 = 1470 samples per frame) and paced to the wall clock, so the note you hear is the transition you see. A supervisor loop restarts the pipeline if YouTube or ffmpeg drops, and Docker's `restart: unless-stopped` covers everything else.

### Feeding two pipes without deadlocking

"named pipes" in the diagram - ugh!! A Linux FIFO buffers ~64 KB; one raw 720p frame is
2.7 MB, so every video write blocks until ffmpeg drains it — while
ffmpeg, for its part, decides which input it wants next based on
timestamp interleaving, and (since ffmpeg 7) deliberately *pauses* the
stream that is ahead until the lagging one catches up. Feed it naively
and both processes end up waiting on each other forever, healthy and
silent at 0% CPU. Three mechanisms keep the pipeline deadlock-free:

1. **Startup handshake.** ffmpeg opens and probes its inputs
   sequentially, so the launcher follows a strict order: open the video
   FIFO, push frame 0 (satisfies the probe), open the audio FIFO, push
   one audio block. Deterministic, done once (`stream.py`).

2. **One writer thread per pipe.** The render loop never writes to a
   pipe directly; it enqueues, and a dedicated thread per pipe does the
   blocking writes. Whichever stream ffmpeg wants next, that pipe's
   writer is standing there with data — blocking one pipe can no longer
   hold the other hostage (`main.py`).

3. **Asymmetric queues.** Audio frames are 5.8 KB, video frames 2.7 MB,
   so the audio queue is deep (256 frames ≈ 8.5 s, all of 1.5 MB) and
   the video queue modest (8). This makes the producer-side deadlock
   structurally impossible: the render loop can only ever block on
   video, and by then every audio frame up to that point is already
   queued — whichever stream ffmpeg demands is always available, under
   ffmpeg 6's greedy input reads and ffmpeg 7's interleave backpressure
   alike.

Failure is handled by conceding it will happen: the queue `put`s carry
5-second timeouts, so a truly dead ffmpeg becomes a detected stall; the
RTMP output carries `-rw_timeout`, so a wedged YouTube socket kills
ffmpeg instead of letting it hoard buffers; a supervisor loop restarts
the pipeline in-process within seconds; and Docker's
`restart: unless-stopped` covers everything the process can't recover
from itself. The base image is pinned by digest, because ffmpeg's I/O
scheduling has changed meaningfully between major versions and an
upgrade should be a decision, not a side effect of a rebuild.

## Run it

Prerequisites on the host: Docker, and dump1090-mutability writing `/var/run/dump1090-mutability/aircraft.json`.

1. Create a YouTube live stream (YouTube Studio → Go live → Streaming software) and copy the stream key.
2. `cp .env.example .env` and paste the key.
3. In `docker-compose.yml`, use `build: .` and set the image to GHCR path in future.
4. `docker compose up -d`

Test without antenna. `DEMO=1 docker compose up` fabricates plausible traffic. No stream key? The container writes a local HLS preview to `./output/preview.m3u8` — open it in VLC.

Useful knobs (env vars): `WIDTH`, `HEIGHT`, `FPS`, `VIDEO_BITRATE`, `TRANSITION_SECONDS`, `IDLE_SECONDS`, `DEDUPE_SECONDS`, `OUTPUT_URL` (any ffmpeg sink, e.g. a different RTMP endpoint).

## CI/CD

Every push to `main` triggers GitHub Actions to build the image, run a 10-second headless smoke test (demo traffic, null encoder sink), and publish to GHCR as `latest` + short SHA. On the streaming machine, `docker compose pull && docker compose up -d` rolls the new version. Add [Watchtower](https://containrrr.dev/watchtower/) in future to automate the pull.

## Notes on 24/7 YouTube streaming

- Use a persistent ("reusable") stream key so the broadcast survives restarts.
- 720p30 at 3000k is comfortably within YouTube's recommended range and renders in real time on a modest CPU; raise to 1080p if the machine has headroom.
- YouTube occasionally recycles long-running broadcasts; the supervisor reconnects automatically, but enabling "auto-start/auto-stop" off (manual control) keeps the event alive across brief drops.
