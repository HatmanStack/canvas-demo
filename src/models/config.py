import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class AppConfig:
    # AWS Configuration - Use non-reserved names for Lambda
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = ""
    bucket_region: str = ""
    nova_image_bucket: str = ""

    # Model Configuration
    nova_canvas_model: str = "amazon.nova-canvas-v1:0"
    nova_lite_model: str = "us.amazon.nova-lite-v1:0"
    bedrock_timeout: int = 300

    # Application Settings
    log_level: str = ""
    enable_nsfw_check: bool = True
    rate_limit: int = 20

    # Image Processing
    min_image_size: int = 256
    max_image_size: int = 2048
    step_size: int = 64
    default_size: int = 1024
    default_cfg_scale: float = 8.0
    default_seed: int = 8
    max_pixels: int = 4194304

    # External APIs
    hf_token: str = ""
    nsfw_api_url: str = "https://api-inference.huggingface.co/models/Falconsai/nsfw_image_detection"
    nsfw_timeout: int = 10
    nsfw_max_retries: int = 3

    # Lambda Configuration
    is_lambda: bool = False
    lambda_port: int = 8080

    def __post_init__(self) -> None:
        """Read env vars at instantiation time and validate."""
        import logging

        from src.utils.exceptions import ConfigurationError

        # Read env vars at instantiation, not class definition
        if not self.aws_access_key_id:
            self.aws_access_key_id = os.getenv(
                "AMP_AWS_ID", os.getenv("AWS_ID", os.getenv("AWS_ACCESS_KEY_ID", ""))
            )
        if not self.aws_secret_access_key:
            self.aws_secret_access_key = os.getenv(
                "AMP_AWS_SECRET", os.getenv("AWS_SECRET", os.getenv("AWS_SECRET_ACCESS_KEY", ""))
            )
        if not self.aws_region:
            self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        if not self.bucket_region:
            self.bucket_region = os.getenv("BUCKET_REGION", "us-west-2")
        if not self.nova_image_bucket:
            self.nova_image_bucket = os.getenv("NOVA_IMAGE_BUCKET", "")
        if not self.log_level:
            self.log_level = os.getenv("LOG_LEVEL", "INFO")

        self.enable_nsfw_check = os.getenv("ENABLE_NSFW_CHECK", "true").lower() == "true"
        self.rate_limit = int(os.getenv("RATE_LIMIT", "20"))

        if not self.hf_token:
            self.hf_token = os.getenv("HF_TOKEN", "")

        self.is_lambda = "AWS_LAMBDA_FUNCTION_NAME" in os.environ
        self.lambda_port = int(os.getenv("AWS_LAMBDA_HTTP_PORT", "8080"))

        # Validation
        if not self.aws_access_key_id or not self.aws_secret_access_key:
            raise ConfigurationError("AWS credentials are required")

        if not self.nova_image_bucket:
            raise ConfigurationError("NOVA_IMAGE_BUCKET is required")

        if self.enable_nsfw_check and not self.hf_token:
            logging.warning(
                "NSFW check enabled but HF_TOKEN not provided. NSFW check will be disabled."
            )
            self.enable_nsfw_check = False


_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get or create the application config singleton."""
    global _config
    if _config is None:
        load_dotenv()
        _config = AppConfig()
    return _config


def reset_config() -> None:
    """Reset config for testing. Not for production use."""
    global _config
    _config = None
