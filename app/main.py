# (c) 2026 jag.m.singh@gmail.com
"""Double Scramble, Live.

Two concentric-square panels after Frank Stella's *Double Scramble*
(Blanton Museum of Art), played by the sky: aircraft captured by a local
dump1090 ADS-B receiver trigger the notes of Satie's Gymnopedie No. 1.
Heavy aircraft advance the melody and dissolve the panels into a fresh,
never-repeating palette; light aircraft lay down the bass. When the sky
empties, the colours breathe and a low hum holds the room.

Runs forever, streaming to YouTube. Designed to be boring to operate and
mesmerising to watch.
"""
import queue
import threading
import time

from . import adsb, config, music, stream, synth, visuals
from .overlay import ClockOverlay, FlightOverlay
from .palette import PaletteEngine


def watcher_thread(q, stop):
    watcher = adsb.make_watcher()
    while not stop.is_set():
        for ev in watcher.poll():
            q.put(ev)
        stop.wait(config.POLL_SECONDS)


def run_pipeline():
    renderer = visuals.Renderer()
    palettes = PaletteEngine(config.BANDS_PER_PANEL)
    engine = synth.Synth()
    melody = music.MelodySequencer()
    bass = music.BassSequencer()
    overlay_treble = FlightOverlay()                       # left edge
    overlay_bass = FlightOverlay(align="right", base_level=0.55)  # right edge
    clock = ClockOverlay()                                 # bottom right

    bg, pa, pb = palettes.next_palette("genesis")
    renderer.set_palette(bg, pa, pb, now=0.0, instant=True)

    # Render frame 0 and its audio up front - the ffmpeg startup handshake
    # needs one real packet of each (see stream.py).
    first_audio = engine.render_frame()
    first_frame = renderer.render(0.0, idle_level=1.0).tobytes()
    proc, vpipe, apipe = stream.start_ffmpeg(first_frame, first_audio)

    # Dedicated writer thread per pipe. A single thread alternating
    # audio-write / video-write can deadlock: ffmpeg interleaves by
    # timestamp and may refuse to drain more video until it gets audio,
    # while we sit blocked pushing a 2.7 MB frame into a 64 KB pipe -
    # both processes healthy, both waiting forever. With one thread per
    # pipe, ffmpeg always finds whichever stream it wants next. Bounded
    # queues preserve backpressure: if ffmpeg truly stalls, put() blocks
    # and the timeout below turns it into a supervised restart.
    # Queue sizing is deliberately asymmetric, and it is what makes the
    # cross-pipe deadlock structurally impossible on ANY ffmpeg version.
    # ffmpeg 7's threaded scheduler enforces interleave backpressure: it
    # pauses reading the stream that is AHEAD (audio) until the lagging
    # stream (video) catches up. If the audio queue could fill first, the
    # producer would block on audio while holding back the very video
    # frame the scheduler is waiting for - observed as a deadlock under
    # ffmpeg 7.1 (container) that ffmpeg 6.1's greedier input reading
    # (host) happened to tolerate. So audio - at 5.8 KB/frame - gets a
    # deep queue (~8.5 s, 1.5 MB) the producer essentially never blocks
    # on; video - 2.7 MB/frame - stays modest. Blocked-on-video is safe:
    # all audio up to that frame is already queued, so whichever stream
    # ffmpeg wants next is always available.
    video_q = queue.Queue(maxsize=8)
    audio_q = queue.Queue(maxsize=256)
    writer_dead = threading.Event()
    closing = threading.Event()

    def _writer(pipe, q, name):
        try:
            while True:
                data = q.get()
                if data is None:
                    return
                pipe.write(data)
        except Exception as exc:
            if not closing.is_set():   # expected during shutdown; stay quiet
                print(f"[stream] {name} writer died: {exc}", flush=True)
            writer_dead.set()

    for pipe, q, name in ((apipe, audio_q, "audio"), (vpipe, video_q, "video")):
        threading.Thread(target=_writer, args=(pipe, q, name),
                         daemon=True).start()

    events = queue.Queue()
    stop = threading.Event()
    threading.Thread(target=watcher_thread, args=(events, stop),
                     daemon=True).start()

    frame_period = 1.0 / config.FPS
    t0 = time.perf_counter()
    next_deadline = 0.0  # measured as elapsed seconds since t0
    frame_no = 1  # frame 0 already written during the handshake
    last_event_time = -config.IDLE_SECONDS  # elapsed base; start in idle calm
    last_trigger = -config.MIN_EVENT_GAP
    idle_level = 0.0
    max_frames = config.FPS * 10 if config.SMOKE_TEST else None

    print("[main] streaming - the sky is the score", flush=True)
    try:
        while True:
            now = time.perf_counter() - t0

            # --- handle at most one plane per MIN_EVENT_GAP ---------------
            if now - last_trigger >= config.MIN_EVENT_GAP:
                try:
                    ev = events.get_nowait()
                except queue.Empty:
                    ev = None
                if ev is not None:
                    last_trigger = now
                    last_event_time = now
                    engine.set_idle(False)
                    if ev.kind == "treble":
                        freq, length = melody.next()
                        engine.melody_note(freq, length)
                        bg, pa, pb = palettes.next_palette(ev.hexid)
                        renderer.set_palette(bg, pa, pb, now)
                        overlay_treble.push(ev.flight or ev.hexid.upper(), now)
                        print(f"[event] {ev} -> melody + palette", flush=True)
                    else:
                        root, chord = bass.next()
                        engine.bass_event(root, chord)
                        bg, pa, pb = palettes.next_palette(ev.hexid, leap=False)
                        renderer.set_palette(bg, pa, pb, now)
                        overlay_bass.push(ev.flight or ev.hexid.upper(), now)
                        print(f"[event] {ev} -> bass + drift", flush=True)

            # --- idle detection -------------------------------------------
            idle = (now - last_event_time) > config.IDLE_SECONDS
            engine.set_idle(idle)
            idle_level = min(1.0, idle_level + frame_period / 3.0) if idle \
                else max(0.0, idle_level - frame_period / 1.5)

            # --- produce one frame of audio + video -----------------------
            if writer_dead.is_set():
                raise BrokenPipeError("pipe writer died")
            frame = renderer.render(now, idle_level)
            overlay_treble.apply(frame, now)
            overlay_bass.apply(frame, now)
            clock.apply(frame)
            try:
                audio_q.put(engine.render_frame(), timeout=5)
                video_q.put(frame.tobytes(), timeout=5)
            except queue.Full:
                raise BrokenPipeError("ffmpeg stopped draining its pipes")

            frame_no += 1
            if max_frames and frame_no >= max_frames:
                print("[main] smoke test complete", flush=True)
                break

            # --- pace to wall clock ---------------------------------------
            next_deadline += frame_period
            delay = next_deadline - (time.perf_counter() - t0)
            if delay > 0:
                time.sleep(delay)
            elif delay < -2.0:  # fell badly behind; resync rather than sprint
                next_deadline = time.perf_counter() - t0
    finally:
        stop.set()
        closing.set()
        for q in (audio_q, video_q):
            try:
                q.put_nowait(None)   # stop writer threads
            except queue.Full:
                pass
        for p in (vpipe, apipe):
            try:
                p.close()
            except OSError:
                pass
        proc.wait(timeout=10) if config.SMOKE_TEST else proc.terminate()


def main():
    if config.SMOKE_TEST:
        run_pipeline()
        return
    # 24/7 supervisor: if YouTube or ffmpeg hiccups, restart the pipeline.
    while True:
        try:
            run_pipeline()
        except (BrokenPipeError, RuntimeError) as exc:
            print(f"[main] pipeline dropped ({exc}); restarting in 3 s",
                  flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()