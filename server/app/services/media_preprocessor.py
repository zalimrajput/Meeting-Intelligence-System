"""Media preprocessor service handling FFmpeg audio extraction from video files."""

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def is_ffmpeg_available() -> bool:
    """Checks if the ffmpeg executable is installed and available in PATH or common locations."""
    if shutil.which("ffmpeg") is not None:
        return True
    
    # Check common Windows installation paths
    win_paths = [
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"),
    ]
    for p in win_paths:
        if p.exists():
            return True

    try:
        res = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return res.returncode == 0
    except (OSError, FileNotFoundError):
        return False


async def extract_audio_from_video(
    video_path: str | Path,
    output_audio_path: str | Path,
    sample_rate_hz: int = 16000,
) -> Path:
    """
    Extracts audio track from video file into 16kHz mono WAV format for DeepGram.

    Args:
        video_path: Input video file path
        output_audio_path: Output destination audio path (.wav)
        sample_rate_hz: Target sampling rate in Hz (default: 16000 Hz)

    Returns:
        Path: Path to extracted WAV audio file

    Raises:
        RuntimeError: If FFmpeg is not installed or execution fails
    """
    video_path = Path(video_path)
    output_audio_path = Path(output_audio_path)

    if not is_ffmpeg_available():
        error_msg = "FFmpeg not found in system PATH. Cannot extract audio from video."
        logger.warning(error_msg)
        raise RuntimeError(error_msg)

    if not video_path.exists():
        raise FileNotFoundError(f"Source video file not found: {video_path}")

    output_audio_path.parent.mkdir(parents=True, exist_ok=True)

    # Find ffmpeg binary
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    if not shutil.which("ffmpeg"):
        for p in [
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        ]:
            if Path(p).exists():
                ffmpeg_bin = p
                break

    cmd = [
        ffmpeg_bin,
        "-y",  # Overwrite output file without asking
        "-i",
        str(video_path),
        "-vn",  # Disable video stream recording
        "-acodec",
        "pcm_s16le",  # 16-bit uncompressed PCM
        "-ar",
        str(sample_rate_hz),  # 16000 Hz sampling rate
        "-ac",
        "1",  # Mono channel
        str(output_audio_path),
    ]

    logger.info("Running FFmpeg audio extraction: %s", " ".join(cmd))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_details = stderr.decode("utf-8", errors="replace")
        logger.error("FFmpeg execution failed (code=%d): %s", process.returncode, error_details)
        raise RuntimeError(f"FFmpeg extraction failed: {error_details}")

    logger.info("Successfully extracted audio from video: %s", str(output_audio_path))
    return output_audio_path

