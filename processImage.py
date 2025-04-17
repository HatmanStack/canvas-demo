import os
import base64
import json
import io
import time
import requests
from dotenv import load_dotenv
from PIL import Image
from dataclasses import dataclass
from datetime import datetime # Import datetime

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
amp_aws_id = os.getenv('AMP_AWS_ID')
token = os.getenv('HF_TOKEN')

headers = {"Authorization": f"Bearer {token}", "x-use-cache": "0", 'Content-Type': 'application/json'}

class ImageProcessor:
    def __init__(self, image):
        print(f"[{datetime.now()}] Initializing ImageProcessor...")
        self.image = self._open_image(image)
        print(f"[{datetime.now()}] ImageProcessor initialized.")

    def _open_image(self, image):
        """Convert input to PIL Image if necessary."""
        print(f"[{datetime.now()}] Opening image...")
        if image is None:
            print(f"[{datetime.now()}] Error: Input image is None.")
            raise ValueError("Input image is required.")
        opened_image = Image.open(image) if not isinstance(image, Image.Image) else image
        print(f"[{datetime.now()}] Image opened successfully. Mode: {opened_image.mode}, Size: {opened_image.size}")
        return opened_image

    def _check_nsfw(self, attempts=1):
        """Check if image is NSFW using Hugging Face API."""
        print(f"[{datetime.now()}] Checking NSFW (Attempt {attempts})...")
        API_URL = "https://api-inference.huggingface.co/models/Falconsai/nsfw_image_detection"

        # Prepare image data
        temp_buffer = io.BytesIO()
        self.image.save(temp_buffer, format='PNG')
        temp_buffer.seek(0)

        try:
            print(f"[{datetime.now()}] Sending request to NSFW API: {API_URL}")
            response = requests.request("POST", API_URL, headers=headers, data=temp_buffer.getvalue())
            print(f"[{datetime.now()}] Received NSFW API response (Status: {response.status_code}).")
            json_response = json.loads(response.content.decode("utf-8"))
            print(f"[{datetime.now()}] NSFW API JSON Response: {json_response}")

            if "error" in json_response:
                print(f"[{datetime.now()}] NSFW API Error: {json_response['error']}")
                if attempts > 30:
                    print(f"[{datetime.now()}] NSFW check failed after max attempts.")
                    raise ImageError("NSFW check failed after multiple attempts")
                estimated_time = json_response.get("estimated_time", 5) # Default wait time
                print(f"[{datetime.now()}] Waiting {estimated_time}s before retry...")
                time.sleep(estimated_time)
                return self._check_nsfw(attempts + 1)

            nsfw_score = next((item['score'] for item in json_response if item['label'] == 'nsfw'), 0)
            print(f"[{datetime.now()}] NSFW Score: {nsfw_score}")

            if nsfw_score > 0.5:
                print(f"[{datetime.now()}] Image flagged as NSFW.")
                return None # Indicate NSFW

            print(f"[{datetime.now()}] Image passed NSFW check.")
            return self # Indicate OK

        except json.JSONDecodeError as e:
            print(f"[{datetime.now()}] NSFW check failed: Invalid JSON response - {str(e)}")
            raise ImageError(f"NSFW check failed: Invalid response format - {str(e)}")
        except requests.exceptions.RequestException as e:
             print(f"[{datetime.now()}] NSFW check failed: Request error - {str(e)}")
             # Optional: Retry logic for network errors
             if attempts > 5: # Fewer retries for network issues
                 raise ImageError(f"NSFW check failed due to network error: {str(e)}")
             print(f"[{datetime.now()}] Waiting 5s before retry due to network error...")
             time.sleep(5)
             return self._check_nsfw(attempts + 1)
        except Exception as e:
            print(f"[{datetime.now()}] NSFW check failed: Unexpected error - {str(e)}")
            if attempts > 30: # Use general retry limit
                print(f"[{datetime.now()}] NSFW check failed after max attempts (unexpected error).")
                raise ImageError("NSFW check failed after multiple attempts (unexpected error)")
            print(f"[{datetime.now()}] Waiting 5s before retry due to unexpected error...")
            time.sleep(5) # Generic wait
            return self._check_nsfw(attempts + 1)

    def _convert_color_mode(self):
        """Handle color mode conversion."""
        print(f"[{datetime.now()}] Converting color mode (Current: {self.image.mode})...")
        if self.image.mode not in ('RGB', 'RGBA'):
            self.image = self.image.convert('RGB')
            print(f"[{datetime.now()}] Converted to RGB.")
        elif self.image.mode == 'RGBA':
            background = Image.new('RGB', self.image.size, (255, 255, 255))
            background.paste(self.image, mask=self.image.split()[3])
            self.image = background
            print(f"[{datetime.now()}] Converted RGBA to RGB by pasting on white background.")
        else:
             print(f"[{datetime.now()}] Color mode is already RGB.")
        return self

    def _resize_for_pixels(self, max_pixels):
        """Resize image to meet pixel limit."""
        print(f"[{datetime.now()}] Resizing for max pixels ({max_pixels})...")
        current_pixels = self.image.width * self.image.height
        print(f"[{datetime.now()}] Current pixels: {current_pixels}")
        if current_pixels > max_pixels:
            aspect_ratio = self.image.width / self.image.height
            if aspect_ratio > 1:
                new_width = int((max_pixels * aspect_ratio) ** 0.5)
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = int((max_pixels / aspect_ratio) ** 0.5)
                new_width = int(new_height * aspect_ratio)
            print(f"[{datetime.now()}] Resizing from {self.image.size} to ({new_width}, {new_height})")
            self.image = self.image.resize((new_width, new_height), Image.LANCZOS)
        else:
            print(f"[{datetime.now()}] No pixel resize needed.")
        return self

    def _ensure_dimensions(self, min_size=320, max_size=4096):
        print(f"[{datetime.now()}] Ensuring dimensions (Min: {min_size}, Max: {max_size})...")
        print(f"[{datetime.now()}] Current dimensions: {self.image.size}")
        width, height = self.image.size
        needs_resize = False
        if width < min_size or width > max_size or height < min_size or height > max_size:
            needs_resize = True
            new_width = min(max(width, min_size), max_size)
            new_height = min(max(height, min_size), max_size)
            print(f"[{datetime.now()}] Resizing from {self.image.size} to ({new_width}, {new_height})")
            self.image = self.image.resize((new_width, new_height), Image.LANCZOS)
        else:
            print(f"[{datetime.now()}] No dimension resize needed.")
        return self

    def encode(self):
        print(f"[{datetime.now()}] Encoding image to base64 PNG...")
        image_bytes = io.BytesIO()
        self.image.save(image_bytes, format='PNG', optimize=True)
        encoded_string = base64.b64encode(image_bytes.getvalue()).decode('utf8')
        print(f"[{datetime.now()}] Image encoded (Length: {len(encoded_string)}).")
        return encoded_string

    def process(self, min_size=320, max_size=4096, max_pixels=4194304):
        """Process image with all necessary transformations."""
        print(f"[{datetime.now()}] --- Starting ImageProcessor.process ---")
        result = (self
            ._convert_color_mode()
            ._resize_for_pixels(max_pixels)
            ._ensure_dimensions(min_size, max_size)
            ._check_nsfw())  # Add NSFW check before encoding

        if result is None:
            print(f"[{datetime.now()}] Image processing stopped due to NSFW flag.")
            raise ImageError("Image <b>Not Appropriate</b>")

        encoded_image = result.encode()
        print(f"[{datetime.now()}] --- Finished ImageProcessor.process ---")
        return encoded_image

def process_and_encode_image(image, **kwargs):
    """Process and encode image with default parameters."""
    print(f"[{datetime.now()}] --- Starting process_and_encode_image ---")
    try:
        processed_image = ImageProcessor(image).process(**kwargs)
        print(f"[{datetime.now()}] --- Finished process_and_encode_image (Success) ---")
        return processed_image
    except ImageError as e:
        print(f"[{datetime.now()}] --- Finished process_and_encode_image (ImageError: {e.message}) ---")
        return e.message # Return the error message string
    except Exception as e:
        print(f"[{datetime.now()}] --- Finished process_and_encode_image (Unexpected Error: {str(e)}) ---")
        # Log the full traceback here if needed for debugging
        logging.exception("Unexpected error in process_and_encode_image")
        return f"An unexpected error occurred during image processing: {str(e)}"