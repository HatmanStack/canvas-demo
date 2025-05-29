"""
Lambda-specific utilities for handling Gradio and file serving
"""

import os
import tempfile
import uuid
import base64
from typing import Union, Optional
from PIL import Image
import io
from src.models.config import config
from src.utils.logger import app_logger

class LambdaImageHandler:
    """Handle image serving in Lambda environment"""
    
    @staticmethod
    def process_image_for_lambda(image: Image.Image) -> Union[str, Image.Image]:
        """
        Process image for optimal display in Lambda environment
        
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
            if image.mode != 'RGB':
                if image.mode == 'RGBA':
                    # Handle transparency with white background
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[3])
                    image = background
                else:
                    image = image.convert('RGB')
                app_logger.debug(f"Converted image to RGB mode")
            
            # Create temporary file with unique name
            temp_filename = f"canvas_gen_{uuid.uuid4().hex[:12]}.png"
            temp_path = os.path.join("/tmp", temp_filename)
            
            # Save with optimization for web serving
            image.save(
                temp_path, 
                format='PNG', 
                optimize=True,
                compress_level=6  # Good compression without too much processing time
            )
            
            # Log file details
            file_size = os.path.getsize(temp_path)
            app_logger.info(f"Saved optimized image: {temp_path} ({file_size} bytes)")
            
            return temp_path
            
        except Exception as e:
            app_logger.error(f"Failed to process image for Lambda: {str(e)}")
            # Fallback to returning PIL Image
            return image
    
    @staticmethod
    def create_data_url(image: Image.Image, format: str = 'PNG') -> str:
        """
        Create base64 data URL from PIL Image
        
        Args:
            image: PIL Image object
            format: Image format (PNG, JPEG)
            
        Returns:
            str: Base64 data URL
        """
        try:
            buffer = io.BytesIO()
            
            # Optimize based on format
            if format.upper() == 'JPEG':
                # Convert to RGB for JPEG (no transparency)
                if image.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    if image.mode == 'RGBA':
                        background.paste(image, mask=image.split()[3])
                    else:
                        background.paste(image)
                    image = background
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
                
                image.save(buffer, format='JPEG', quality=85, optimize=True)
                mime_type = 'image/jpeg'
            else:
                # PNG format
                if image.mode not in ('RGB', 'RGBA'):
                    image = image.convert('RGBA' if image.mode in ('LA', 'P') else 'RGB')
                
                image.save(buffer, format='PNG', optimize=True)
                mime_type = 'image/png'
            
            # Create base64 string
            img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
            data_url = f"data:{mime_type};base64,{img_str}"
            
            app_logger.debug(f"Created {format} data URL: {len(data_url)} characters")
            return data_url
            
        except Exception as e:
            app_logger.error(f"Failed to create data URL: {str(e)}")
            raise
    
    @staticmethod
    def cleanup_temp_files(max_age_seconds: int = 3600):
        """
        Clean up old temporary image files
        
        Args:
            max_age_seconds: Maximum age of files to keep (default: 1 hour)
        """
        try:
            import time
            current_time = time.time()
            tmp_dir = "/tmp"
            
            if not os.path.exists(tmp_dir):
                return
            
            cleaned_count = 0
            for filename in os.listdir(tmp_dir):
                if filename.startswith('canvas_gen_') and filename.endswith('.png'):
                    file_path = os.path.join(tmp_dir, filename)
                    try:
                        file_age = current_time - os.path.getmtime(file_path)
                        if file_age > max_age_seconds:
                            os.remove(file_path)
                            cleaned_count += 1
                    except (OSError, IOError):
                        # File might be in use or already deleted
                        pass
            
            if cleaned_count > 0:
                app_logger.debug(f"Cleaned up {cleaned_count} old temporary image files")
                
        except Exception as e:
            app_logger.warning(f"Failed to cleanup temp files: {str(e)}")

# Global instance
lambda_image_handler = LambdaImageHandler()