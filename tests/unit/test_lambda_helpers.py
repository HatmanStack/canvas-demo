"""Unit tests for LambdaImageHandler."""

import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.utils.lambda_helpers import LambdaImageHandler


class TestLambdaImageHandler:
    """Tests for LambdaImageHandler class."""

    @pytest.fixture
    def sample_image(self):
        """Create a sample RGB image."""
        return Image.new("RGB", (100, 100), color="red")

    @pytest.fixture
    def sample_rgba_image(self):
        """Create a sample RGBA image."""
        return Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))

    def test_process_image_local_env(self, sample_image):
        """Test processing in local environment (not Lambda)."""
        with patch("src.utils.lambda_helpers.config.is_lambda", False):
            result = LambdaImageHandler.process_image_for_lambda(sample_image)
            assert isinstance(result, Image.Image)
            assert result == sample_image

    def test_process_image_lambda_env(self, sample_image):
        """Test processing in Lambda environment."""
        with patch("src.utils.lambda_helpers.config.is_lambda", True), \
             patch("PIL.Image.Image.save") as mock_save, \
             patch("pathlib.Path.stat") as mock_stat:
            
            mock_stat.return_value.st_size = 1024
            
            result = LambdaImageHandler.process_image_for_lambda(sample_image)
            assert isinstance(result, str)
            assert "/tmp/canvas_gen_" in result
            assert result.endswith(".png")
            mock_save.assert_called_once()

    def test_cleanup_temp_files(self):
        """Test cleaning up old temp files."""
        # Create a real temp dir to simulate /tmp
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create old file
            old_file = temp_path / "canvas_gen_old.png"
            old_file.touch()
            # Set mtime to 2 hours ago
            os.utime(old_file, (time.time() - 7200, time.time() - 7200))
            
            # Create new file
            new_file = temp_path / "canvas_gen_new.png"
            new_file.touch()
            
            # Create non-matching file
            other_file = temp_path / "other.txt"
            other_file.touch()
            os.utime(other_file, (time.time() - 7200, time.time() - 7200))

            # Mock Path("/tmp") to return our temp_path
            with patch("src.utils.lambda_helpers.Path") as mock_path_cls:
                # When Path("/tmp") is called, return temp_path
                # When Path(temp_path) is called (iterdir returns paths), return them as is?
                # No, iterdir yields Path objects.
                
                # The code: tmp_dir = Path("/tmp")
                # Then tmp_dir.iterdir()
                
                # We can mock the instance returned by Path("/tmp")
                mock_tmp_instance = MagicMock()
                mock_tmp_instance.exists.return_value = True
                mock_tmp_instance.iterdir.return_value = [old_file, new_file, other_file]
                
                # Configure Path class to return our mock when initialized with "/tmp"
                def side_effect(arg=None):
                    if str(arg) == "/tmp":
                        return mock_tmp_instance
                    return Path(arg) if arg else Path()
                
                mock_path_cls.side_effect = side_effect
                
                LambdaImageHandler.cleanup_temp_files(max_age_seconds=3600)
                
                # Verify files status
                assert not old_file.exists()
                assert new_file.exists()
                assert other_file.exists()
