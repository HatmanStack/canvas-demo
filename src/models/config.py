import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    # AWS Configuration - Use non-reserved names for Lambda
    aws_access_key_id: str = os.getenv("AMP_AWS_ID", os.getenv("AWS_ID", ""))
    aws_secret_access_key: str = os.getenv("AMP_AWS_SECRET", os.getenv("AWS_SECRET", ""))
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    bucket_region: str = os.getenv("BUCKET_REGION", "us-west-2")
    nova_image_bucket: str = os.getenv("NOVA_IMAGE_BUCKET", "")

    # Model Configuration
    nova_canvas_model: str = "amazon.nova-canvas-v1:0"
    nova_lite_model: str = "us.amazon.nova-lite-v1:0"
    bedrock_timeout: int = 300

    # Application Settings
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    enable_nsfw_check: bool = os.getenv("ENABLE_NSFW_CHECK", "true").lower() == "true"
    rate_limit: int = int(os.getenv("RATE_LIMIT", "20"))

    # Image Processing
    min_image_size: int = 256
    max_image_size: int = 2048
    step_size: int = 64
    default_size: int = 1024
    default_cfg_scale: float = 8.0
    default_seed: int = 8
    max_pixels: int = 4194304

    # External APIs
    hf_token: str = os.getenv("HF_TOKEN", "")
    nsfw_api_url: str = "https://api-inference.huggingface.co/models/Falconsai/nsfw_image_detection"
    nsfw_timeout: int = 10
    nsfw_max_retries: int = 3

    # Lambda Configuration
    is_lambda: bool = "AWS_LAMBDA_FUNCTION_NAME" in os.environ
    lambda_port: int = int(os.getenv("AWS_LAMBDA_HTTP_PORT", "8080"))

    def __post_init__(self):
        """Validate configuration after initialization"""
        if not self.aws_access_key_id or not self.aws_secret_access_key:
            raise ValueError("AWS credentials are required")

        if not self.nova_image_bucket:
            raise ValueError("NOVA_IMAGE_BUCKET is required")

        if self.enable_nsfw_check and not self.hf_token:
            logging.warning(
                "NSFW check enabled but HF_TOKEN not provided. NSFW check will be disabled."
            )
            self.enable_nsfw_check = False


# Global configuration instance
config = AppConfig()

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)
logger.info("Configuration loaded successfully")
