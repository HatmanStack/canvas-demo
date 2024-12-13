import os
import base64
import json
import io
import time
import requests
from dotenv import load_dotenv
from PIL import Image
from dataclasses import dataclass

load_dotenv()
# Move custom exceptions to the top
class ImageError(Exception):
    def __init__(self, message):
        self.message = message

@dataclass
class ImageConfig:
    min_size: int = 320
    max_size: int = 4096
    max_pixels: int = 4194304
    quality: str = "standard"
    format: str = "PNG"

config = ImageConfig()

token = os.environ.get("HF_TOKEN")
headers = {"Authorization": f"Bearer {token}", "x-use-cache": "0", 'Content-Type': 'application/json'}

class ImageProcessor:
    def __init__(self, image):
        self.image = self._open_image(image)
        
    def _open_image(self, image):
        """Convert input to PIL Image if necessary."""
        if image is None:
            raise ValueError("Input image is required.")
        return Image.open(image) if not isinstance(image, Image.Image) else image
    
    def _check_nsfw(self, attempts=1):
        """Check if image is NSFW using Hugging Face API."""
        API_URL = "https://api-inference.huggingface.co/models/Falconsai/nsfw_image_detection"
        
        # Prepare image data
        temp_buffer = io.BytesIO()
        self.image.save(temp_buffer, format='PNG')
        temp_buffer.seek(0)
        
        try:
            response = requests.request("POST", API_URL, headers=headers, data=temp_buffer.getvalue())
            json_response = json.loads(response.content.decode("utf-8"))
            print(json_response)
            if "error" in json_response:
                if attempts > 30:
                    raise ImageError("NSFW check failed after multiple attempts")
                time.sleep(json_response["estimated_time"])
                return self._check_nsfw(attempts + 1)
            
            nsfw_score = next((item['score'] for item in json_response if item['label'] == 'nsfw'), 0)
            print(f"NSFW Score: {nsfw_score}")
            
            if nsfw_score > 0.1:
                return None
                  
            return self
            
        except json.JSONDecodeError as e:
            raise ImageError(f"NSFW check failed: Invalid response format - {str(e)}")
        except Exception as e:
            if attempts > 30:
                raise ImageError("NSFW check failed after multiple attempts")
            return self._check_nsfw(attempts + 1)
    
    def _convert_color_mode(self):
        """Handle color mode conversion."""
        if self.image.mode not in ('RGB', 'RGBA'):
            self.image = self.image.convert('RGB')
        elif self.image.mode == 'RGBA':
            background = Image.new('RGB', self.image.size, (255, 255, 255))
            background.paste(self.image, mask=self.image.split()[3])
            self.image = background
        return self
    
    def _resize_for_pixels(self, max_pixels):
        """Resize image to meet pixel limit."""
        current_pixels = self.image.width * self.image.height
        if current_pixels > max_pixels:
            aspect_ratio = self.image.width / self.image.height
            if aspect_ratio > 1:
                new_width = int((max_pixels * aspect_ratio) ** 0.5)
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = int((max_pixels / aspect_ratio) ** 0.5)
                new_width = int(new_height * aspect_ratio)
            self.image = self.image.resize((new_width, new_height), Image.LANCZOS)
        return self
    
    def _ensure_dimensions(self, min_size=320, max_size=4096):
        if (self.image.width < min_size or 
            self.image.width > max_size or 
            self.image.height < min_size or 
            self.image.height > max_size):
            
            new_width = min(max(self.image.width, min_size), max_size)
            new_height = min(max(self.image.height, min_size), max_size)
            self.image = self.image.resize((new_width, new_height), Image.LANCZOS)
        
        return self
    
    def encode(self):
        image_bytes = io.BytesIO()
        self.image.save(image_bytes, format='PNG', optimize=True)
        return base64.b64encode(image_bytes.getvalue()).decode('utf8')
        
    def process(self, min_size=320, max_size=4096, max_pixels=4194304):
        """Process image with all necessary transformations."""
        result = (self
            ._convert_color_mode()
            ._resize_for_pixels(max_pixels)
            ._ensure_dimensions(min_size, max_size)
            ._check_nsfw())  # Add NSFW check before encoding
    
        if result is None:
            raise ImageError("Image <b>Not Appropriate</b>")
            
        return result.encode()

def process_and_encode_image(image, **kwargs):
    """Process and encode image with default parameters."""
    try:
        image = ImageProcessor(image).process(**kwargs)
        return image
    except ImageError as e:
        return str(e)