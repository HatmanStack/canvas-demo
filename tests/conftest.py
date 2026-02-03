"""Shared test fixtures for Canvas Demo application."""

import io
import json
import base64
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


@pytest.fixture
def mock_config():
    """Mock application configuration."""
    with patch("src.models.config.config") as mock:
        mock.rate_limit = 20
        mock.is_lambda = False
        mock.enable_nsfw_check = False
        mock.aws_access_key_id = "test-access-key"
        mock.aws_secret_access_key = "test-secret-key"
        mock.aws_region = "us-east-1"
        mock.bucket_region = "us-west-2"
        mock.nova_image_bucket = "test-bucket"
        mock.nova_canvas_model = "amazon.nova-canvas-v1:0"
        mock.nova_lite_model = "us.amazon.nova-lite-v1:0"
        mock.bedrock_timeout = 300
        mock.min_image_size = 256
        mock.max_image_size = 2048
        mock.max_pixels = 4194304
        mock.hf_token = ""
        mock.nsfw_api_url = "https://example.com/nsfw"
        mock.nsfw_timeout = 10
        mock.nsfw_max_retries = 3
        yield mock


@pytest.fixture
def mock_boto3_client():
    """Mock boto3 client for all AWS services."""
    with patch("boto3.client") as mock:
        yield mock


@pytest.fixture
def mock_s3_client():
    """Mock S3 client with common operations."""
    mock = MagicMock()
    mock.get_object.return_value = {
        "ETag": '"abc123"',
        "Body": MagicMock(read=lambda: json.dumps({"premium": [], "standard": []}).encode()),
    }
    mock.put_object.return_value = {}
    mock.generate_presigned_url.return_value = "https://s3.example.com/presigned"
    return mock


@pytest.fixture
def sample_image():
    """Create a sample RGB PIL Image for testing."""
    return Image.new("RGB", (512, 512), color="red")


@pytest.fixture
def sample_rgba_image():
    """Create a sample RGBA PIL Image for testing."""
    return Image.new("RGBA", (512, 512), color=(255, 0, 0, 128))


@pytest.fixture
def small_image():
    """Create a small image that needs resizing."""
    return Image.new("RGB", (100, 100), color="blue")


@pytest.fixture
def large_image():
    """Create a large image that exceeds max pixels."""
    return Image.new("RGB", (3000, 3000), color="green")


@pytest.fixture
def sample_image_bytes(sample_image):
    """Get sample image as bytes."""
    buffer = io.BytesIO()
    sample_image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def sample_image_base64(sample_image_bytes):
    """Get sample image as base64 string."""
    return base64.b64encode(sample_image_bytes).decode("utf-8")


@pytest.fixture
def mock_bedrock_response(sample_image_base64):
    """Sample Bedrock image generation response."""
    response_body = json.dumps({"images": [sample_image_base64]}).encode()
    return {
        "body": MagicMock(read=lambda: response_body),
    }


@pytest.fixture
def mock_bedrock_text_response():
    """Sample Bedrock text generation response."""
    return {
        "output": {
            "message": {
                "content": [{"text": "A beautiful sunset over mountains"}]
            }
        }
    }


@pytest.fixture
def rate_limit_request_body():
    """Sample request body for rate limiting tests."""
    return json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {"text": "test prompt"},
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": 1024,
            "width": 1024,
            "quality": "standard",
            "cfgScale": 8.0,
            "seed": 0,
        },
    })


@pytest.fixture
def premium_rate_limit_request_body():
    """Sample premium request body for rate limiting tests."""
    return json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {"text": "test prompt"},
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": 1024,
            "width": 1024,
            "quality": "premium",
            "cfgScale": 8.0,
            "seed": 0,
        },
    })
