# (c) 2026 jag.m.singh@gmail.com
"""FFmpeg pipeline.

Raw RGB frames and raw stereo PCM are fed through two named pipes into a
single ffmpeg process that encodes H.264 + AAC and pushes RTMP to YouTube.
Without a stream key it falls back to a local HLS preview (open
output/preview.m3u8 in VLC), and in smoke-test mode it encodes to null.
"""
import os
import subprocess

from . import config

VIDEO_FIFO = "/tmp/video.fifo"
AUDIO_FIFO = "/tmp/audio.fifo"


def _sink():
    if config.SMOKE_TEST:
        return ["-f", "null", "-"]
    if config.OUTPUT_URL:
        return ["-f", "flv", config.OUTPUT_URL]
    if config.YOUTUBE_STREAM_KEY:
        # rw_timeout (microseconds): if the RTMP socket stops accepting
        # writes for 10 s, ffmpeg exits instead of hoarding buffers as a
        # zombie - the writers die, and the supervisor reconnects fresh.
        return ["-f", "flv", "-rw_timeout", "10000000",
                f"rtmp://a.rtmp.youtube.com/live2/{config.YOUTUBE_STREAM_KEY}"]
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    print(f"[stream] no YOUTUBE_STREAM_KEY - writing local HLS preview to "
          f"{config.OUTPUT_DIR}/preview.m3u8", flush=True)
    return ["-f", "hls", "-hls_time", "4", "-hls_list_size", "6",
            "-hls_flags", "delete_segments",
            os.path.join(config.OUTPUT_DIR, "preview.m3u8")]


def start_ffmpeg(first_frame: bytes, first_audio: bytes):
    for fifo in (VIDEO_FIFO, AUDIO_FIFO):
        if os.path.exists(fifo):
            os.remove(fifo)
        os.mkfifo(fifo)

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning",
        "-thread_queue_size", "1024",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{config.WIDTH}x{config.HEIGHT}", "-r", str(config.FPS),
        "-i", VIDEO_FIFO,
        # raw pcm is fully specified by the args, so don't sit probing an
        # empty FIFO (which would deadlock the startup handshake)
        "-probesize", "32", "-analyzeduration", "0",
        "-thread_queue_size", "1024",
        "-f", "s16le", "-ar", str(config.SAMPLE_RATE), "-ac", "2",
        "-i", AUDIO_FIFO,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-g", str(config.FPS * 2), "-keyint_min", str(config.FPS * 2),
        "-b:v", config.VIDEO_BITRATE, "-maxrate", config.VIDEO_BITRATE,
        "-bufsize", "6000k",
        "-c:a", "aac", "-b:a", "160k", "-ar", str(config.SAMPLE_RATE),
    ] + _sink()

    proc = subprocess.Popen(cmd)

    # Startup handshake. FIFO opens block until the reader (ffmpeg)
    # attaches, and ffmpeg won't open input #1 until it has probed one
    # full packet from input #0 - so the order matters:
    #   open video -> write first frame -> open audio -> prime audio.
    vpipe = open(VIDEO_FIFO, "wb", buffering=0)
    vpipe.write(first_frame)
    apipe = open(AUDIO_FIFO, "wb", buffering=0)
    apipe.write(first_audio)

    if proc.poll() is not None:
        raise RuntimeError(f"ffmpeg exited at startup (rc={proc.returncode})")
    return proc, vpipe, apipe