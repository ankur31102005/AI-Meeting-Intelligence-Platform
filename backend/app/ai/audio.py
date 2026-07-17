"""
Audio preparation via FFmpeg (subprocess, not a Python binding).

Why subprocess over a binding (ffmpeg-python, PyAV):
  * ffmpeg is already in the worker image; no extra native build.
  * Explicit args = predictable, debuggable command lines in logs.

`prepare_audio()` is the pipeline's entry point: it takes ANY supported input
(mp3/wav/mp4) and produces a 16 kHz mono WAV — the exact format Whisper wants.
Running video and audio through the SAME normalization keeps one code path
and guarantees the transcriber never sees a surprise codec.
"""

import subprocess
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import UnprocessableError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Whisper is trained on 16 kHz mono audio; matching it avoids an internal
# resample and halves memory vs stereo.
_TARGET_SAMPLE_RATE = 16000
_TARGET_CHANNELS = 1
# Hard ceiling so a corrupt/huge file can't hang a worker forever.
_FFMPEG_TIMEOUT_SECONDS = 60 * 30


def get_media_duration(path: str) -> float:
    """Seconds of media, via ffprobe. Returns 0.0 if it can't be determined."""
    settings = get_settings()
    try:
        # noqa: S603 — binary path is from trusted config, args are internal
        # file paths, never raw user input. shell=False (list form).
        result = subprocess.run(  # noqa: S603
            [
                settings.FFPROBE_BINARY,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
        logger.warning("ffprobe_duration_failed", path=path, error=str(exc))
        return 0.0


def prepare_audio(input_path: str, output_path: str) -> float:
    """Transcode `input_path` to a 16 kHz mono WAV at `output_path`.

    Works for both audio and video sources (ffmpeg extracts the audio track).
    Returns the audio duration in seconds. Raises UnprocessableError with the
    ffmpeg stderr on failure so the pipeline can mark the meeting FAILED with a
    real reason instead of a generic 500.
    """
    settings = get_settings()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        settings.FFMPEG_BINARY,
        "-y",                       # overwrite output if it exists
        "-i", input_path,
        "-vn",                      # drop any video stream
        "-ac", str(_TARGET_CHANNELS),
        "-ar", str(_TARGET_SAMPLE_RATE),
        "-c:a", "pcm_s16le",        # uncompressed 16-bit PCM WAV
        output_path,
    ]
    logger.info("ffmpeg_extract_start", input=input_path, output=output_path)
    try:
        subprocess.run(  # noqa: S603 — trusted binary, list args, shell=False
            cmd,
            capture_output=True,
            text=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        # ffmpeg puts the useful diagnostic on stderr.
        tail = (exc.stderr or "").strip().splitlines()[-3:]
        raise UnprocessableError(
            "Could not process the audio/video file (it may be corrupt or an "
            "unsupported codec).",
            details={"ffmpeg_error": " ".join(tail)},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise UnprocessableError("Audio processing timed out.") from exc

    duration = get_media_duration(output_path)
    logger.info("ffmpeg_extract_done", output=output_path, duration_seconds=duration)
    return duration
