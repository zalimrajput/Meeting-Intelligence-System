"""File validation module: magic byte verification and file size checks."""

from typing import BinaryIO

MAX_FILE_SIZE_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GB (per rules.md / prd.md)

ALLOWED_EXTENSIONS: set[str] = {
    # Audio
    "mp3",
    "wav",
    "m4a",
    "ogg",
    "flac",
    "aac",
    # Video
    "mp4",
    "mkv",
    "mov",
    "avi",
    "webm",
}


def _check_audio_mime(header: bytes) -> str | None:
    """Helper to detect audio formats from header bytes."""
    if header.startswith(b"OggS"):
        return "audio/ogg"
    if header.startswith(b"fLaC"):
        return "audio/flac"
    if header.startswith(b"ID3") or header[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if header[:2] in (b"\xff\xf1", b"\xff\xf9"):
        return "audio/aac"
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WAVE":
        return "audio/wav"
    return None


def _check_video_mime(header: bytes) -> str | None:
    """Helper to detect video / container formats from header bytes."""
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"AVI ":
        return "video/x-msvideo"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand in (b"M4A ", b"M4B "):
            return "audio/mp4"
        if brand == b"qt  ":
            return "video/quicktime"
        return "video/mp4"
    return None


def detect_mime_type_from_bytes(header: bytes) -> str | None:
    """Inspect the first 32-64 bytes of a file to detect its actual MIME type."""
    if len(header) < 4:
        return None
    return _check_audio_mime(header) or _check_video_mime(header)


def validate_file_content(
    file_obj: BinaryIO, filename: str, file_size: int
) -> tuple[bool, str, str]:
    """
    Validates uploaded file size and content type from magic bytes.
    Returns (is_valid, detected_mime, error_message).
    """
    if file_size > MAX_FILE_SIZE_BYTES:
        return False, "", f"File size ({file_size} bytes) exceeds maximum limit of 2GB."

    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return (
            False,
            "",
            f"Unsupported file extension: .{ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    pos = file_obj.tell()
    header = file_obj.read(64)
    file_obj.seek(pos)

    detected_mime = detect_mime_type_from_bytes(header)
    if not detected_mime:
        return (
            False,
            "",
            "Unable to verify file format from magic bytes. File may be corrupted or unsupported.",
        )

    return True, detected_mime, ""
