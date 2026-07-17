"""Unit tests for upload validation — the security gate."""

import pytest

from app.core.exceptions import BadRequestError, PayloadTooLargeError
from app.services.file_validation import (
    LimitedReader,
    enforce_size_limit,
    validate_extension_and_magic,
)

# Minimal valid headers for each accepted format.
MP3_HEADER = b"ID3\x04\x00\x00\x00\x00\x00\x00rest-of-file"
WAV_HEADER = b"RIFF\x24\x00\x00\x00WAVEfmt rest"
MP4_HEADER = b"\x00\x00\x00\x18ftypmp42rest-of-file"


class TestExtensionAndMagic:
    def test_valid_mp3(self):
        v = validate_extension_and_magic("meeting.mp3", MP3_HEADER)
        assert v.extension == "mp3"
        assert v.content_type == "audio/mpeg"

    def test_valid_wav(self):
        assert validate_extension_and_magic("audio.wav", WAV_HEADER).content_type == "audio/wav"

    def test_valid_mp4(self):
        assert validate_extension_and_magic("video.mp4", MP4_HEADER).content_type == "video/mp4"

    def test_uppercase_extension_ok(self):
        assert validate_extension_and_magic("MEETING.MP3", MP3_HEADER).extension == "mp3"

    def test_unsupported_extension_rejected(self):
        with pytest.raises(BadRequestError, match="Unsupported"):
            validate_extension_and_magic("virus.exe", MP3_HEADER)

    def test_no_extension_rejected(self):
        with pytest.raises(BadRequestError, match="no extension"):
            validate_extension_and_magic("noext", MP3_HEADER)

    def test_renamed_file_rejected_by_magic(self):
        """A PE executable renamed to .mp3 must be caught by magic bytes."""
        exe_header = b"MZ\x90\x00\x03\x00\x00\x00fake-mp3-actually-exe"
        with pytest.raises(BadRequestError, match="does not match"):
            validate_extension_and_magic("malware.mp3", exe_header)

    def test_riff_but_not_wave_rejected(self):
        """RIFF is also AVI — must require the WAVE tag specifically."""
        avi_header = b"RIFF\x24\x00\x00\x00AVI rest-of-file"
        with pytest.raises(BadRequestError, match="does not match"):
            validate_extension_and_magic("fake.wav", avi_header)


class TestSizeLimit:
    def test_within_limit_ok(self):
        enforce_size_limit(1000, 2000)  # no raise

    def test_over_limit_rejected(self):
        with pytest.raises(PayloadTooLargeError, match="limit"):
            enforce_size_limit(3000, 2000)

    def test_empty_file_rejected(self):
        with pytest.raises(BadRequestError, match="empty"):
            enforce_size_limit(0, 2000)


class TestLimitedReader:
    def test_reads_through_under_limit(self):
        import io

        reader = LimitedReader(io.BytesIO(b"hello world"), max_bytes=100)
        assert reader.read() == b"hello world"

    def test_aborts_when_exceeding_limit(self):
        import io

        reader = LimitedReader(io.BytesIO(b"x" * 5000), max_bytes=1000)
        with pytest.raises(PayloadTooLargeError):
            reader.read()  # reading all 5000 bytes trips the cap

    def test_chunked_read_trips_limit_midstream(self):
        import io

        reader = LimitedReader(io.BytesIO(b"x" * 300), max_bytes=100)
        reader.read(50)   # ok, 50 total
        reader.read(40)   # ok, 90 total
        with pytest.raises(PayloadTooLargeError):
            reader.read(50)  # 140 > 100

    def test_delegates_full_file_interface(self):
        """boto3's S3 client probes close/readable/seekable on the stream —
        the wrapper must delegate them, not just expose read/seek/tell.
        (Regression: a bare wrapper broke real MinIO uploads.)"""
        import io

        underlying = io.BytesIO(b"data")
        reader = LimitedReader(underlying, max_bytes=100)
        assert reader.readable() is True
        assert reader.seekable() is True
        reader.close()                 # must not raise
        assert underlying.closed       # delegated to the real stream
