import os
import base64
import boto3
import json
import logging
import io
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image
from functools import wraps
from dataclasses import dataclass
from botocore.config import Config
from botocore.exceptions import ClientError

load_dotenv()
# Move custom exceptions to the top
class ImageError(Exception):
    def __init__(self, message):
        self.message = message

def handle_bedrock_errors(func):
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ClientError as err:
            logger.error(f"Bedrock client error: {err.response['Error']['Message']}")
            raise ImageError(f"Client error: {err.response['Error']['Message']}")
        except Exception as err:
            logger.error(f"Unexpected error: {str(err)}")
            raise ImageError(f"Unexpected error: {str(err)}")
    return wrapper

@dataclass
class ImageConfig:
    min_size: int = 320
    max_size: int = 4096
    max_pixels: int = 4194304
    quality: str = "standard"
    format: str = "PNG"

config = ImageConfig()

model_id = 'amazon.nova-canvas-v1:0'
aws_id = os.getenv('AWS_ID')
aws_secret = os.getenv('AWS_SECRET')
nova_image_bucket='nova-image-data'
bucket_region='us-west-2'

class ImageProcessor:
    def __init__(self, image):
        self.image = self._open_image(image)
        
    def _open_image(self, image):
        """Convert input to PIL Image if necessary."""
        if image is None:
            raise ValueError("Input image is required.")
        return Image.open(image) if not isinstance(image, Image.Image) else image
    
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
        return (self
                ._convert_color_mode()
                ._resize_for_pixels(max_pixels)
                ._ensure_dimensions(min_size, max_size)
                .encode())

# Function to generate an image using Amazon Nova Canvas model
class BedrockClient:

    def __init__(self, aws_id, aws_secret, model_id, timeout=300):
        self.model_id = model_id
        self.bedrock_client = boto3.client(
            service_name='bedrock-runtime',
            aws_access_key_id=aws_id,
            aws_secret_access_key=aws_secret,
            region_name='us-east-1',
            config=Config(read_timeout=timeout)
        )
        self.s3_client = boto3.client(
            service_name='s3',
            aws_access_key_id=aws_id,
            aws_secret_access_key=aws_secret,
            region_name=bucket_region
        )

    def _store_response(self, response_body, image_data=None):
        """Store response and image in S3."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Store response body
        response_key = f'responses/{timestamp}_response.json'
        self.s3_client.put_object(
            Bucket=nova_image_bucket,
            Key=response_key,
            Body=json.dumps(response_body),
            ContentType='application/json'
        )
        
        # Store image if present
        if image_data:
            image_key = f'images/{timestamp}_image.png'
            self.s3_client.put_object(
                Bucket=nova_image_bucket,
                Key=image_key,
                Body=image_data,
                ContentType='image/png'
            )
    
    
    def _handle_error(self, err):
        """Handle client errors"""
        raise ImageError(f"Client error: {err.response['Error']['Message']}")
    
    def generate_image(self, body):
        """Generate image using Bedrock service."""
        try:
            response = self.bedrock_client.invoke_model(
                body=body,
                modelId=self.model_id,
                accept="application/json",
                contentType="application/json"
            )
            image_data =  self._process_response(response)

            self._store_response(
                body,
                image_data
            )

            return image_data
        except ClientError as err:
            self._handle_error(err)
    
    @handle_bedrock_errors
    def generate_prompt(self, body):
        try:
            response = self.bedrock_client.converse(
                modelId=self.model_id, 
                messages=body
            )
            return self._process_response(response)
        except ClientError as err:
            self._handle_error(err)

    @handle_bedrock_errors
    def _process_response(self, response):
        """Process successful response for both image and text."""
        if "error" in response:
            raise ImageError(f"Generation error: {response['error']}")
        
        if "output" in response and "message" in response["output"]:
            message_content = response["output"]["message"]["content"]
            if message_content and "text" in message_content[0]:
                return message_content[0]["text"]

        response_body = json.loads(response.get("body").read())    
        if "images" in response_body:
            return base64.b64decode(response_body.get("images")[0].encode('ascii'))
        
        raise ImageError("Unexpected response format.")

def process_and_encode_image(image, **kwargs):
    """Process and encode image with default parameters."""
    return ImageProcessor(image).process(**kwargs)

def generate_image(body):
    """Generate image using Bedrock service."""
    client = BedrockClient(
        aws_id=os.getenv('AWS_ID'),
        aws_secret=os.getenv('AWS_SECRET'),
        model_id='amazon.nova-canvas-v1:0'
    )
    return client.generate_image(body)

def generate_prompt(body):
    client = BedrockClient(
        aws_id=os.getenv('AWS_ID'),
        aws_secret=os.getenv('AWS_SECRET'),
        model_id='us.amazon.nova-lite-v1:0'
    )
    return client.generate_prompt(body)
    