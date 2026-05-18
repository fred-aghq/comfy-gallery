"""Tests for app.services.thumbnails — thumbnail generation."""

from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.models.media import MediaType
from app.services.thumbnails import _thumbnail_output_path, generate_thumbnail


class TestThumbnailOutputPath:
    def test_deterministic(self):
        p1 = _thumbnail_output_path(Path("/a/b/c.png"))
        p2 = _thumbnail_output_path(Path("/a/b/c.png"))
        assert p1 == p2

    def test_different_files_different_paths(self):
        p1 = _thumbnail_output_path(Path("/a/b/c.png"))
        p2 = _thumbnail_output_path(Path("/a/b/d.png"))
        assert p1 != p2

    def test_output_is_webp(self):
        p = _thumbnail_output_path(Path("/test.png"))
        assert p.suffix == ".webp"


class TestGenerateImageThumbnail:
    def test_generates_thumbnail(self, tmp_path, sample_png_path):
        with patch("app.services.thumbnails.settings") as mock_settings:
            thumb_dir = tmp_path / "thumbs"
            thumb_dir.mkdir()
            mock_settings.thumbnail_dir = str(thumb_dir)
            mock_settings.thumbnail_size = 200

            result = generate_thumbnail(sample_png_path, MediaType.IMAGE)

        assert result is not None
        assert result.endswith(".webp")
        output_file = thumb_dir / result
        assert output_file.exists()

        with Image.open(output_file) as img:
            assert max(img.size) <= 200

    def test_cache_hit(self, tmp_path, sample_png_path):
        with patch("app.services.thumbnails.settings") as mock_settings:
            thumb_dir = tmp_path / "thumbs"
            thumb_dir.mkdir()
            mock_settings.thumbnail_dir = str(thumb_dir)
            mock_settings.thumbnail_size = 200

            result1 = generate_thumbnail(sample_png_path, MediaType.IMAGE)
            result2 = generate_thumbnail(sample_png_path, MediaType.IMAGE)

        assert result1 == result2

    def test_corrupt_image(self, tmp_path):
        corrupt = tmp_path / "bad.png"
        corrupt.write_bytes(b"not an image")
        with patch("app.services.thumbnails.settings") as mock_settings:
            thumb_dir = tmp_path / "thumbs"
            thumb_dir.mkdir()
            mock_settings.thumbnail_dir = str(thumb_dir)
            mock_settings.thumbnail_size = 200

            result = generate_thumbnail(corrupt, MediaType.IMAGE)

        assert result is None


class TestGenerateVideoThumbnail:
    def test_corrupt_video(self, tmp_path):
        video = tmp_path / "bad.mp4"
        video.write_bytes(b"\x00" * 100)
        with patch("app.services.thumbnails.settings") as mock_settings:
            thumb_dir = tmp_path / "thumbs"
            thumb_dir.mkdir()
            mock_settings.thumbnail_dir = str(thumb_dir)
            mock_settings.thumbnail_size = 200

            result = generate_thumbnail(video, MediaType.VIDEO)

        assert result is None
