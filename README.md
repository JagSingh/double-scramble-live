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
