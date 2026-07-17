"""
Upload validation — the security gate before any bytes are stored.

Defense in depth, three independent checks:
  1. Extension allow-list (cheap first filter).
  2. MAGIC BYTES sniff (the real check): the file's actual header must match
     an allowed media type. A '.mp3' that is really a PE executable is
     rejected here — extensions and Content-Type headers are attacker-
     controlled and must never be trusted alone.
  3. Size cap enforced WHILE streaming (see stream_with_limit), so a client
     lying about Content-Length cannot exhaust the disk.
"""

from dataclasses import dataclass
from typing import BinaryIO

from app.core.exceptions import BadRequestError, PayloadTooLargeError

# ext -> canonical content type we store
_ALLOWED_EXTENSIONS: dict[str, str] = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "mp4": "video/mp4",
}

# Magic-byte signatures. Each entry: (offset, byte-prefix).
# A file matches a format if ANY of its signatures matches.
_MAGIC_SIGNATURES: dict[str, list[tuple[int, bytes]]] = {
    "mp3": [
        (0, b"ID3"),          # ID3v2-tagged mp3
        (0, b"\xff\xfb"),     # MPEG-1 Layer 3 frame sync
        (0, b"\xff\xf3"),
        (0, b"\xff\xf2"),
    ],
    "wav": [(0, b"RIFF")],    # RIFF container (WAVE checked below at offset 8)
    "mp4": [(4, b"ftyp")],    # ISO Base Media: 'ftyp' box at offset 4
}


@dataclass(frozen=True)
class ValidatedUpload:
    extension: str
    content_type: str


def validate_extension_and_magic(filename: str, header: bytes) -> ValidatedUpload:
    """Validate by extension AND magic bytes. Raises BadRequestError on fail.

    `header` should be the first >= 16 bytes of the file.
    """
    if "." not in filename:
        raise BadRequestError("File has no extension")

    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise BadRequestError(
            f"Unsupported file type '.{ext}'. Allowed: "
            + ", ".join(f".{e}" for e in _ALLOWED_EXTENSIONS)
        )

    if not _matches_magic(ext, header):
        raise BadRequestError(
            f"File content does not match a valid .{ext} file "
            "(possible renamed or corrupt file)"
        )

    return ValidatedUpload(extension=ext, content_type=_ALLOWED_EXTENSIONS[ext])


def _matches_magic(ext: str, header: bytes) -> bool:
    for offset, sig in _MAGIC_SIGNATURES[ext]:
        if header[offset : offset + len(sig)] == sig:
            # WAV extra guard: RIFF is also AVI/others — require 'WAVE' tag.
            if ext == "wav" and header[8:12] != b"WAVE":
                continue
            return True
    return False


def enforce_size_limit(size_bytes: int, max_bytes: int) -> None:
    """Post-write guard: reject an oversize/empty upload."""
    if size_bytes > max_bytes:
        raise PayloadTooLargeError(
            f"File is {size_bytes / 1024 / 1024:.1f} MB; "
            f"limit is {max_bytes / 1024 / 1024:.0f} MB"
        )
    if size_bytes == 0:
        raise BadRequestError("Uploaded file is empty")


class LimitedReader:
    """Read-through wrapper that ABORTS once `max_bytes` is exceeded.

    Wrapping the upload stream in this before handing it to storage means a
    malicious 10 GB upload is killed mid-stream — bytes are never fully
    written, so disk/S3 can't be exhausted by a client lying about
    Content-Length. This is the real size defense; enforce_size_limit() is a
    belt-and-braces post-check.
    """

    def __init__(self, stream: BinaryIO, max_bytes: int) -> None:
        self._stream = stream
        self._max = max_bytes
        self._read = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._stream.read(size)
        self._read += len(chunk)
        if self._read > self._max:
            raise PayloadTooLargeError(
                f"Upload exceeds the {self._max / 1024 / 1024:.0f} MB limit"
            )
        return chunk

    def seek(self, offset: int, whence: int = 0) -> int:
        pos = self._stream.seek(offset, whence)
        # Reset the counter on rewind so post-validation peeks don't double-count.
        if offset == 0 and whence == 0:
            self._read = 0
        return pos

    def tell(self) -> int:
        return self._stream.tell()

    def __getattr__(self, name: str):
        """Delegate every other file method (close, readable, seekable, ...)
        to the wrapped stream. boto3's upload_fileobj probes these — a bare
        read/seek/tell wrapper isn't enough for a real S3 client. (The local
        backend only calls read(), which is why this only shows up against
        MinIO/S3.)"""
        return getattr(self._stream, name)
