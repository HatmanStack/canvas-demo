import io
import base64
import asyncio
import aiohttp
from typing import Optional, Union
from PIL import Image
import numpy as np
from src.models.config import config
from src.utils.logger import app_logger, log_performance
from src.utils.exceptions import ImageError, NSFWError, handle_gracefully

class OptimizedImageProcessor:
    """Optimized image processor with async NSFW checking and efficient operations"""
    
    def __init__(self, image: Union[str, Image.Image, io.IOBase]):
        self.image = self._open_image(image)
        app_logger.debug(f"ImageProcessor initialized for image: {self.image.size}")
    
    def _open_image(self, image) -> Image.Image:
        """Convert input to PIL Image with validation"""
        if image is None:
            raise ImageError("Input image is required")
        
        try:
            if isinstance(image, Image.Image):
                return image
            elif isinstance(image, str):
                return Image.open(image)
            else:
                return Image.open(image)
        except Exception as e:
            raise ImageError(f"Failed to open image: {str(e)}")
    
    @log_performance
    async def check_nsfw_async(self, timeout: int = None, max_retries: int = None) -> bool:
        """Async NSFW check with circuit breaker pattern"""
        if not config.enable_nsfw_check or not config.hf_token:
            app_logger.debug("NSFW check skipped (disabled or no token)")
            return False
        
        timeout = timeout or config.nsfw_timeout
        max_retries = max_retries or config.nsfw_max_retries
        
        # Prepare image data
        temp_buffer = io.BytesIO()
        self.image.save(temp_buffer, format='PNG')
        temp_buffer.seek(0)
        
        headers = {
            "Authorization": f"Bearer {config.hf_token}",
            "x-use-cache": "0",
            'Content-Type': 'application/json'
        }
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                    async with session.post(
                        config.nsfw_api_url,
                        headers=headers,
                        data=temp_buffer.getvalue()
                    ) as response:
                        
                        if response.status == 200:
                            json_response = await response.json()
                            nsfw_score = next(
                                (item['score'] for item in json_response if item['label'] == 'nsfw'), 
                                0
                            )
                            
                            app_logger.debug(f"NSFW Score: {nsfw_score}")
                            return nsfw_score > 0.5
                        
                        elif response.status == 503:  # Service Unavailable
                            retry_after = int(response.headers.get('Retry-After', 5))
                            app_logger.warning(f"NSFW API unavailable, retry in {retry_after}s")
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            app_logger.warning(f"NSFW API returned status {response.status}")
                            
            except asyncio.TimeoutError:
                app_logger.warning(f"NSFW check timeout (attempt {attempt + 1}/{max_retries})")
            except Exception as e:
                app_logger.warning(f"NSFW check error (attempt {attempt + 1}/{max_retries}): {str(e)}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        # If all retries failed, disable NSFW check for this session and continue
        app_logger.warning("NSFW check failed after all retries, continuing without check")
        return False
    
    def check_nsfw_sync(self) -> bool:
        """Synchronous wrapper for NSFW check"""
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.check_nsfw_async())
        except RuntimeError:
            # If no event loop is running, create a new one
            return asyncio.run(self.check_nsfw_async())
    
    @log_performance
    def _convert_color_mode(self) -> 'OptimizedImageProcessor':
        """Optimized color mode conversion"""
        if self.image.mode not in ('RGB', 'RGBA'):
            app_logger.debug(f"Converting from {self.image.mode} to RGB")
            self.image = self.image.convert('RGB')
        elif self.image.mode == 'RGBA':
            # More efficient RGBA to RGB conversion
            background = Image.new('RGB', self.image.size, (255, 255, 255))
            background.paste(self.image, mask=self.image.split()[3])
            self.image = background
            app_logger.debug("Converted RGBA to RGB")
        
        return self
    
    @log_performance
    def _resize_for_pixels(self, max_pixels: int = None) -> 'OptimizedImageProcessor':
        """Efficient pixel-based resizing"""
        max_pixels = max_pixels or config.max_pixels
        current_pixels = self.image.width * self.image.height
        
        if current_pixels <= max_pixels:
            return self
        
        # Calculate new dimensions maintaining aspect ratio
        aspect_ratio = self.image.width / self.image.height
        scale_factor = (max_pixels / current_pixels) ** 0.5
        
        new_width = int(self.image.width * scale_factor)
        new_height = int(self.image.height * scale_factor)
        
        # Ensure dimensions are divisible by 16
        new_width = (new_width // 16) * 16
        new_height = (new_height // 16) * 16
        
        app_logger.debug(f"Resizing from {self.image.size} to ({new_width}, {new_height})")
        self.image = self.image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        return self
    
    @log_performance
    def _ensure_dimensions(self, min_size: int = None, max_size: int = None) -> 'OptimizedImageProcessor':
        """Ensure image meets dimension requirements"""
        min_size = min_size or config.min_image_size
        max_size = max_size or config.max_image_size
        
        width, height = self.image.size
        
        # Clamp dimensions to valid range
        width = max(min(width, max_size), min_size)
        height = max(min(height, max_size), min_size)
        
        # Ensure divisibility by 16
        width = (width // 16) * 16
        height = (height // 16) * 16
        
        # Enforce aspect ratio constraints (1:4 to 4:1)
        aspect_ratio = max(width / height, height / width)
        if aspect_ratio > 4:
            if width > height:
                height = max(min_size, (width // 4 // 16) * 16)
            else:
                width = max(min_size, (height // 4 // 16) * 16)
        
        if (width, height) != self.image.size:
            app_logger.debug(f"Adjusting dimensions to ({width}, {height})")
            self.image = self.image.resize((width, height), Image.Resampling.LANCZOS)
        
        return self
    
    @log_performance
    def encode(self) -> str:
        """Encode image to base64 string"""
        image_bytes = io.BytesIO()
        self.image.save(image_bytes, format='PNG', optimize=True)
        encoded_string = base64.b64encode(image_bytes.getvalue()).decode('utf8')
        app_logger.debug(f"Image encoded (size: {len(encoded_string)} chars)")
        return encoded_string
    
    @log_performance
    def process(self, check_nsfw: bool = True, **kwargs) -> str:
        """Process image with all transformations"""
        app_logger.info("Starting image processing")
        
        # Apply transformations
        self._convert_color_mode()
        self._resize_for_pixels(kwargs.get('max_pixels'))
        self._ensure_dimensions(kwargs.get('min_size'), kwargs.get('max_size'))
        
        # NSFW check if enabled
        if check_nsfw and config.enable_nsfw_check:
            is_nsfw = self.check_nsfw_sync()
            if is_nsfw:
                raise NSFWError("Image flagged as inappropriate")
        
        return self.encode()

def create_padded_image(image_dict: dict, padding_percent: int = 100) -> Image.Image:
    """Create padded image for outpainting"""
    image = image_dict.get('background')
    if not image:
        raise ImageError("No background image provided")
    
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    width, height = image.size
    new_width = int(width * (1 + padding_percent / 100))
    new_height = int(height * (1 + padding_percent / 100))
    
    # Create white background
    padded = Image.new('RGBA', (new_width, new_height), (255, 255, 255, 255))
    
    # Center original image
    x_offset = (new_width - width) // 2
    y_offset = (new_height - height) // 2
    
    padded.paste(image, (x_offset, y_offset))
    app_logger.debug(f"Created padded image: {padded.size}")
    
    return padded

def process_composite_to_mask(original_image: Image.Image, composite_image: Optional[Image.Image] = None, 
                            transparent: bool = False) -> Image.Image:
    """Process composite image to create mask"""
    original_array = np.array(original_image.convert('RGBA'))
    
    if transparent:
        # Convert non-white areas to black mask
        is_not_white_mask = ~((original_array[:, :, 0] == 255) &
                              (original_array[:, :, 1] == 255) &
                              (original_array[:, :, 2] == 255))
        
        output_image = Image.new('RGBA', original_image.size, (255, 255, 255, 255))
        output_array = np.array(output_image)
        output_array[is_not_white_mask] = [0, 0, 0, 255]
        
        return Image.fromarray(output_array, mode='RGBA')
    
    if composite_image is None:
        # Create mask from transparent areas
        mask = np.full(original_array.shape[:2], 0, dtype=np.uint8)
        transparent_areas = original_array[:, :, 3] == 0
        mask[transparent_areas] = 255
    else:
        # Create mask from differences between original and composite
        composite_array = np.array(composite_image.convert('RGBA'))
        difference = np.any(original_array != composite_array, axis=2)
        mask = np.full(original_array.shape[:2], 255, dtype=np.uint8)
        mask[difference] = 0
    
    return Image.fromarray(mask, mode='L')

@handle_gracefully(default_return="Error processing image")
def process_and_encode_image(image: Union[str, Image.Image, io.IOBase], **kwargs) -> str:
    """Main entry point for image processing"""
    try:
        processor = OptimizedImageProcessor(image)
        return processor.process(**kwargs)
    except NSFWError as e:
        app_logger.warning(f"NSFW content detected: {e.message}")
        return e.message
    except ImageError as e:
        app_logger.error(f"Image processing error: {e.message}")
        return e.message
    except Exception as e:
        app_logger.error(f"Unexpected image processing error: {str(e)}")
        raise ImageError(f"Unexpected error during image processing: {str(e)}")