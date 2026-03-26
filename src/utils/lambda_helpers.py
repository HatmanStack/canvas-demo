"""Lambda-specific utilities for handling Gradio and file serving."""

import time
from pathlib import Path

from src.utils.logger import app_logger


class LambdaImageHandler:
    """Handle image serving in Lambda environment."""

    @staticmethod
    def cleanup_temp_files(max_age_seconds: int = 3600) -> None:
        """
        Clean up old temporary image files.

        Args:
            max_age_seconds: Maximum age of files to keep (default: 1 hour)
        """
        try:
            current_time = time.time()
            tmp_dir = Path("/tmp")

            if not tmp_dir.exists():
                return

            cleaned_count = 0
            for file_path in tmp_dir.iterdir():
                if file_path.name.startswith("canvas_gen_") and file_path.suffix == ".png":
                    try:
                        file_age = current_time - file_path.stat().st_mtime
                        if file_age > max_age_seconds:
                            file_path.unlink()
                            cleaned_count += 1
                    except OSError:
                        # File might be in use or already deleted
                        pass

            if cleaned_count > 0:
                app_logger.debug(f"Cleaned up {cleaned_count} old temporary image files")

        except Exception as e:
            app_logger.warning(f"Failed to cleanup temp files: {e!s}")


# Global instance
lambda_image_handler = LambdaImageHandler()
