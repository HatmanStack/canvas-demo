"""Unit tests for AWS client manager and Bedrock service."""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from src.services.aws_client import AWSClientManager, BedrockService
from src.utils.exceptions import BedrockError


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton state between tests."""
    AWSClientManager._instance = None
    AWSClientManager._bedrock_client = None
    AWSClientManager._s3_client = None
    AWSClientManager._logs_client = None
    AWSClientManager._executor = None
    yield
    AWSClientManager._instance = None
    AWSClientManager._bedrock_client = None
    AWSClientManager._s3_client = None
    AWSClientManager._logs_client = None
    AWSClientManager._executor = None


@pytest.fixture
def bedrock_service():
    """Create a BedrockService with mocked client manager."""
    with patch("src.services.aws_client.AWSClientManager") as mock_manager:
        mock_instance = MagicMock()
        mock_manager.return_value = mock_instance
        svc = BedrockService()
        svc.client_manager = mock_instance
        yield svc, mock_instance


class TestGenerateImage:
    """Tests for BedrockService.generate_image."""

    def test_success_returns_decoded_bytes(self, bedrock_service):
        """Successful call returns decoded image bytes."""
        svc, mock_cm = bedrock_service
        image_b64 = base64.b64encode(b"fake-image-data").decode()
        response_body = json.dumps({"images": [image_b64]}).encode()

        mock_cm.bedrock_client.invoke_model.return_value = {
            "body": MagicMock(read=lambda: response_body),
        }
        mock_cm.executor = None  # No async storage

        result = svc.generate_image('{"taskType": "TEXT_IMAGE"}')

        assert result == b"fake-image-data"
        mock_cm.bedrock_client.invoke_model.assert_called_once()

    def test_client_error_raises_bedrock_error(self, bedrock_service):
        """ClientError from Bedrock raises BedrockError."""
        from botocore.exceptions import ClientError

        svc, mock_cm = bedrock_service
        mock_cm.bedrock_client.invoke_model.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Bad request"}},
            "InvokeModel",
        )

        with pytest.raises(BedrockError, match="Image generation failed"):
            svc.generate_image('{"taskType": "TEXT_IMAGE"}')


class TestGeneratePrompt:
    """Tests for BedrockService.generate_prompt."""

    def test_success_returns_text(self, bedrock_service):
        """Successful converse call returns text string."""
        svc, mock_cm = bedrock_service
        mock_cm.bedrock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": "A beautiful sunset"}]}}
        }

        result = svc.generate_prompt([{"role": "user", "content": [{"text": "generate"}]}])

        assert result == "A beautiful sunset"


class TestProcessImageResponse:
    """Tests for BedrockService._process_image_response."""

    def test_error_key_raises(self, bedrock_service):
        """Response with 'error' key raises BedrockError."""
        svc, _ = bedrock_service
        response_body = json.dumps({"error": "content policy violation"}).encode()

        with pytest.raises(BedrockError, match="Generation error"):
            svc._process_image_response({"body": MagicMock(read=lambda: response_body)})

    def test_unexpected_format_raises(self, bedrock_service):
        """Response without 'images' or 'error' raises BedrockError."""
        svc, _ = bedrock_service
        response_body = json.dumps({"unexpected": "data"}).encode()

        with pytest.raises(BedrockError, match="Unexpected response format"):
            svc._process_image_response({"body": MagicMock(read=lambda: response_body)})


class TestStoreResponse:
    """Tests for async/sync storage methods."""

    def test_store_response_async_submits_to_executor(self, bedrock_service):
        """_store_response_async submits task to executor."""
        svc, mock_cm = bedrock_service
        mock_executor = MagicMock()
        mock_cm.executor = mock_executor

        svc._store_response_async('{"test": true}', b"image-data")

        mock_executor.submit.assert_called_once_with(
            svc._store_response_sync, '{"test": true}', b"image-data"
        )

    def test_store_response_sync_failure_logs_warning(self, bedrock_service):
        """_store_response_sync failure logs warning but doesn't raise."""
        svc, mock_cm = bedrock_service
        mock_cm.s3_client.put_object.side_effect = RuntimeError("S3 down")

        # Should not raise
        svc._store_response_sync('{"test": true}', b"image-data")
