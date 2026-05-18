"""Tests for app.services.scanner — file discovery and scan-and-ingest logic."""

import shutil
from unittest.mock import patch

import pytest

from app.services.scanner import discover_media_files

# ---------------------------------------------------------------------------
# discover_media_files
# ---------------------------------------------------------------------------

class TestDiscoverMediaFiles:
    def test_finds_supported_files(self, tmp_media_dir):
        (tmp_media_dir / "photo.png").write_bytes(b"\x89PNG")
        (tmp_media_dir / "photo.jpg").write_bytes(b"\xff\xd8")
        (tmp_media_dir / "video.mp4").write_bytes(b"\x00")
        (tmp_media_dir / "readme.txt").write_text("not media")
        (tmp_media_dir / "data.log").write_text("log")

        result = discover_media_files(str(tmp_media_dir))
        names = [p.name for p in result]
        assert "photo.png" in names
        assert "photo.jpg" in names
        assert "video.mp4" in names
        assert "readme.txt" not in names
        assert "data.log" not in names

    def test_empty_directory(self, tmp_media_dir):
        result = discover_media_files(str(tmp_media_dir))
        assert result == []

    def test_nested_subdirectories(self, tmp_media_dir):
        sub1 = tmp_media_dir / "sub1"
        sub2 = tmp_media_dir / "sub2"
        sub1.mkdir()
        sub2.mkdir()
        (sub1 / "img.png").write_bytes(b"\x89PNG")
        (sub2 / "vid.mp4").write_bytes(b"\x00")

        result = discover_media_files(str(tmp_media_dir))
        names = [p.name for p in result]
        assert "img.png" in names
        assert "vid.mp4" in names

    def test_case_insensitive_extensions(self, tmp_media_dir):
        (tmp_media_dir / "PHOTO.PNG").write_bytes(b"\x89PNG")
        (tmp_media_dir / "Video.Mp4").write_bytes(b"\x00")
        (tmp_media_dir / "pic.Jpg").write_bytes(b"\xff\xd8")

        result = discover_media_files(str(tmp_media_dir))
        assert len(result) == 3

    def test_returns_sorted(self, tmp_media_dir):
        (tmp_media_dir / "c.png").write_bytes(b"\x89PNG")
        (tmp_media_dir / "a.png").write_bytes(b"\x89PNG")
        (tmp_media_dir / "b.png").write_bytes(b"\x89PNG")

        result = discover_media_files(str(tmp_media_dir))
        names = [p.name for p in result]
        assert names == ["a.png", "b.png", "c.png"]

    def test_all_supported_extensions(self, tmp_media_dir):
        extensions = [".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov", ".avi", ".mkv"]
        for ext in extensions:
            (tmp_media_dir / f"file{ext}").write_bytes(b"\x00")

        result = discover_media_files(str(tmp_media_dir))
        assert len(result) == len(extensions)


# ---------------------------------------------------------------------------
# scan_and_ingest (requires DB + mocking)
# ---------------------------------------------------------------------------

class TestScanAndIngest:
    @pytest.fixture
    def media_with_sample(self, tmp_media_dir, sample_png_path):
        """Copy the real ComfyUI sample into a temp media dir."""
        shutil.copy2(sample_png_path, tmp_media_dir / "ComfyUI_00001_.png")
        return tmp_media_dir

    async def test_first_scan_new_files(self, db_session, media_with_sample):
        from app.services.scanner import scan_and_ingest

        with patch("app.services.scanner.settings") as mock_settings:
            mock_settings.media_root = str(media_with_sample)
            mock_settings.thumbnail_dir = str(media_with_sample / "thumbs")
            mock_settings.thumbnail_size = 400
            stats = await scan_and_ingest(db_session)

        assert stats["discovered"] == 1
        assert stats["new"] == 1
        assert stats["errors"] == 0

    async def test_rescan_no_new_files(self, db_session, media_with_sample):
        from app.services.scanner import scan_and_ingest

        with patch("app.services.scanner.settings") as mock_settings:
            mock_settings.media_root = str(media_with_sample)
            mock_settings.thumbnail_dir = str(media_with_sample / "thumbs")
            mock_settings.thumbnail_size = 400

            await scan_and_ingest(db_session)
            stats2 = await scan_and_ingest(db_session)

        assert stats2["discovered"] == 1
        assert stats2["new"] == 0
        assert stats2["updated"] == 0

    async def test_scan_with_corrupt_file(self, db_session, tmp_media_dir):
        from app.services.scanner import scan_and_ingest

        # A corrupt file is still processed — metadata extraction returns None
        # and thumbnail generation fails gracefully (returns None).
        # The scan loop only counts errors when an exception propagates.
        (tmp_media_dir / "corrupt.png").write_bytes(b"not a real png at all")

        with patch("app.services.scanner.settings") as mock_settings:
            mock_settings.media_root = str(tmp_media_dir)
            mock_settings.thumbnail_dir = str(tmp_media_dir / "thumbs")
            mock_settings.thumbnail_size = 400
            stats = await scan_and_ingest(db_session)

        assert stats["discovered"] == 1
        # File is still ingested with null metadata/thumbnail
        assert stats["new"] == 1
        assert stats["errors"] == 0

    async def test_scan_continues_after_error(self, db_session, media_with_sample):
        """When one file raises, the scanner skips it and processes the rest."""
        from PIL import Image

        from app.services.scanner import scan_and_ingest

        # Add a second valid image
        Image.new("RGB", (50, 50), "red").save(media_with_sample / "good.png")

        call_count = 0
        original_extract = __import__(
            "app.services.metadata", fromlist=["extract_metadata"]
        ).extract_metadata

        def _bomb_on_first(fp):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("simulated corruption")
            return original_extract(fp)

        with (
            patch("app.services.scanner.settings") as mock_settings,
            patch("app.services.scanner.extract_metadata", side_effect=_bomb_on_first),
        ):
            mock_settings.media_root = str(media_with_sample)
            mock_settings.thumbnail_dir = str(media_with_sample / "thumbs")
            mock_settings.thumbnail_size = 400
            stats = await scan_and_ingest(db_session)

        assert stats["errors"] == 1
        assert stats["new"] == 1
        assert len(stats["error_details"]) == 1
        assert "simulated corruption" in stats["error_details"][0]["error"]

    async def test_scan_error_details_contain_file_path(self, db_session, tmp_media_dir):
        """error_details entries include the file path and error message."""
        from app.services.scanner import scan_and_ingest

        (tmp_media_dir / "bad.png").write_bytes(b"\x89PNG")

        with (
            patch("app.services.scanner.settings") as mock_settings,
            patch(
                "app.services.scanner.extract_metadata",
                side_effect=ValueError("bad value"),
            ),
        ):
            mock_settings.media_root = str(tmp_media_dir)
            mock_settings.thumbnail_dir = str(tmp_media_dir / "thumbs")
            mock_settings.thumbnail_size = 400
            stats = await scan_and_ingest(db_session)

        assert stats["errors"] == 1
        assert stats["new"] == 0
        detail = stats["error_details"][0]
        assert "bad.png" in detail["file"]
        assert "ValueError" in detail["error"]
        assert "bad value" in detail["error"]

    async def test_scan_adds_new_file_on_rescan(self, db_session, media_with_sample):
        from app.services.scanner import scan_and_ingest

        with patch("app.services.scanner.settings") as mock_settings:
            mock_settings.media_root = str(media_with_sample)
            mock_settings.thumbnail_dir = str(media_with_sample / "thumbs")
            mock_settings.thumbnail_size = 400

            stats1 = await scan_and_ingest(db_session)
            assert stats1["new"] == 1

            # Add another file
            from PIL import Image

            Image.new("RGB", (100, 100), "blue").save(media_with_sample / "new_image.png")

            stats2 = await scan_and_ingest(db_session)
            assert stats2["discovered"] == 2
            assert stats2["new"] == 1

    async def test_scan_empty_directory(self, db_session, tmp_media_dir):
        from app.services.scanner import scan_and_ingest

        with patch("app.services.scanner.settings") as mock_settings:
            mock_settings.media_root = str(tmp_media_dir)
            mock_settings.thumbnail_dir = str(tmp_media_dir / "thumbs")
            mock_settings.thumbnail_size = 400
            stats = await scan_and_ingest(db_session)

        assert stats["discovered"] == 0
        assert stats["new"] == 0

    async def test_seed_large_value(self, db_session, media_with_sample):
        """Verify that large ComfyUI seeds (> int32) are stored correctly."""
        from sqlalchemy import select

        from app.models.media import MediaFile
        from app.services.scanner import scan_and_ingest

        with patch("app.services.scanner.settings") as mock_settings:
            mock_settings.media_root = str(media_with_sample)
            mock_settings.thumbnail_dir = str(media_with_sample / "thumbs")
            mock_settings.thumbnail_size = 400
            await scan_and_ingest(db_session)

        result = await db_session.execute(select(MediaFile))
        media = result.scalar_one()
        assert media.seed == 721897303308196
