"""Lambda-specific utilities for handling Gradio and file serving."""

import base64
import io
import time
import uuid
from pathlib import Path

from PIL import Image

from src.models.config import config
from src.utils.logger import app_logger


class LambdaImageHandler:
    """Handle image serving in Lambda environment."""

    @staticmethod
    def process_image_for_lambda(image: Image.Image) -> str | Image.Image:
        """
        Process image for optimal display in Lambda environment.

        Args:
            image: PIL Image object

        Returns:
            str: File path for Lambda environments
            Image.Image: PIL Image for local environments
        """
        if not config.is_lambda:
            # Local environment - return PIL Image directly
            app_logger.debug("Local environment: returning PIL Image")
            return image

        # Lambda environment - use temporary file approach
        try:
            app_logger.debug("Lambda environment: processing image for file serving")

            # Ensure image is in RGB format
            if image.mode != "RGB":
                if image.mode == "RGBA":
                    # Handle transparency with white background
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[3])
                    image = background
                else:
                    image = image.convert("RGB")
                app_logger.debug("Converted image to RGB mode")

            # Create temporary file with unique name
            temp_filename = f"canvas_gen_{uuid.uuid4().hex[:12]}.png"
            temp_path = Path("/tmp") / temp_filename

            # Save with optimization for web serving
            image.save(
                temp_path,
                format="PNG",
                optimize=True,
                compress_level=6,  # Good compression without too much processing time
            )

            # Log file details
            file_size = temp_path.stat().st_size
            app_logger.info(f"Saved optimized image: {temp_path} ({file_size} bytes)")

            return str(temp_path)

        except Exception as e:
            app_logger.error(f"Failed to process image for Lambda: {e!s}")
            # Fallback to returning PIL Image
            return image

    @staticmethod
    def create_data_url(image: Image.Image, fmt: str = "PNG") -> str:
        """
        Create base64 data URL from PIL Image.

        Args:
            image: PIL Image object
            fmt: Image format (PNG, JPEG)

        Returns:
            str: Base64 data URL
        """
        try:
            buffer = io.BytesIO()

            # Optimize based on format
            if fmt.upper() == "JPEG":
                # Convert to RGB for JPEG (no transparency)
                if image.mode in ("RGBA", "LA"):
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    if image.mode == "RGBA":
                        background.paste(image, mask=image.split()[3])
                    else:
                        background.paste(image)
                    image = background
                elif image.mode != "RGB":
                    image = image.convert("RGB")

                image.save(buffer, format="JPEG", quality=85, optimize=True)
                mime_type = "image/jpeg"
            else:
                # PNG format
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA" if image.mode in ("LA", "P") else "RGB")

                image.save(buffer, format="PNG", optimize=True)
                mime_type = "image/png"

            # Create base64 string
            img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
            data_url = f"data:{mime_type};base64,{img_str}"

            app_logger.debug(f"Created {fmt} data URL: {len(data_url)} characters")
            return data_url

        except Exception as e:
            app_logger.error(f"Failed to create data URL: {e!s}")
            raise

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
