"""Unit tests for LambdaImageHandler."""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.utils.lambda_helpers import LambdaImageHandler


class TestLambdaImageHandler:
    """Tests for LambdaImageHandler class."""

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
                mock_tmp_instance = MagicMock()
                mock_tmp_instance.exists.return_value = True
                mock_tmp_instance.iterdir.return_value = [old_file, new_file, other_file]

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
