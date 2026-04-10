"""AWS client management with thread-safe singleton and async storage."""

import atexit
import base64
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, cast

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from src.models.config import get_config
from src.utils.exceptions import BedrockError, ConfigurationError
from src.utils.logger import app_logger, log_performance

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient
    from mypy_boto3_bedrock_runtime.type_defs import (
        ConverseResponseTypeDef,
        InvokeModelResponseTypeDef,
        MessageTypeDef,
    )
    from mypy_boto3_logs import CloudWatchLogsClient
    from mypy_boto3_s3 import S3Client


class AWSClientManager:
    """Thread-safe singleton for AWS client management with connection pooling."""

    _instance: "AWSClientManager | None" = None
    _lock: threading.Lock = threading.Lock()
    _client_lock: threading.Lock = threading.Lock()

    # Clients stored at class level for singleton behavior
    _bedrock_client: "BedrockRuntimeClient | None" = None
    _s3_client: "S3Client | None" = None
    _logs_client: "CloudWatchLogsClient | None" = None

    # Thread pool for async operations
    _executor: ThreadPoolExecutor | None = None
    MAX_WORKERS: Final[int] = 2

    def __new__(cls) -> "AWSClientManager":
        """Thread-safe singleton creation using double-checked locking."""
        if cls._instance is None:
            with cls._lock:
                # Double-check after acquiring lock
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    # Initialize thread pool
                    cls._executor = ThreadPoolExecutor(max_workers=cls.MAX_WORKERS)
                    # Register cleanup on exit
                    atexit.register(cls._shutdown_executor)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the client manager (only runs once due to singleton)."""
        if not hasattr(self, "_initialized"):
            self._initialized = True
            app_logger.info("Initializing AWS Client Manager")

    @classmethod
    def _shutdown_executor(cls) -> None:
        """Shutdown the thread pool executor on exit."""
        if cls._executor is not None:
            cls._executor.shutdown(wait=False)
            cls._executor = None

    @classmethod
    def _reset(cls) -> None:
        """Reset singleton state for testing. Not for production use."""
        with cls._lock, cls._client_lock:
            if cls._executor is not None:
                cls._executor.shutdown(wait=False)
            cls._instance = None
            cls._bedrock_client = None
            cls._s3_client = None
            cls._logs_client = None
            cls._executor = None

    @property
    def bedrock_client(self) -> "BedrockRuntimeClient":
        """Thread-safe lazy initialization of Bedrock client with connection pooling."""
        if self._bedrock_client is None:
            with self._client_lock:
                # Double-check after acquiring lock
                if self._bedrock_client is None:
                    try:
                        client_kwargs: dict[str, Any] = {
                            "service_name": "bedrock-runtime",
                            "region_name": "us-east-1",  # Nova Canvas only in us-east-1
                            "config": Config(
                                read_timeout=get_config().bedrock_timeout,
                                max_pool_connections=10,
                                retries={"max_attempts": 3},
                            ),
                        }
                        if get_config().aws_access_key_id:
                            client_kwargs["aws_access_key_id"] = get_config().aws_access_key_id
                            client_kwargs["aws_secret_access_key"] = (
                                get_config().aws_secret_access_key
                            )
                        AWSClientManager._bedrock_client = boto3.client(**client_kwargs)
                        app_logger.info("Bedrock client initialized")
                    except Exception as e:
                        raise ConfigurationError(
                            f"Failed to initialize Bedrock client: {e!s}"
                        ) from e
        assert self._bedrock_client is not None
        return self._bedrock_client

    @property
    def s3_client(self) -> "S3Client":
        """Thread-safe lazy initialization of S3 client."""
        if self._s3_client is None:
            with self._client_lock:
                # Double-check after acquiring lock
                if self._s3_client is None:
                    try:
                        s3_kwargs: dict[str, Any] = {
                            "service_name": "s3",
                            "region_name": get_config().bucket_region,
                            "config": Config(max_pool_connections=5),
                        }
                        if get_config().aws_access_key_id:
                            s3_kwargs["aws_access_key_id"] = get_config().aws_access_key_id
                            s3_kwargs["aws_secret_access_key"] = get_config().aws_secret_access_key
                        AWSClientManager._s3_client = boto3.client(**s3_kwargs)
                        app_logger.info("S3 client initialized")
                    except Exception as e:
                        raise ConfigurationError(f"Failed to initialize S3 client: {e!s}") from e
        assert self._s3_client is not None
        return self._s3_client

    @property
    def logs_client(self) -> "CloudWatchLogsClient | None":
        """Thread-safe lazy initialization of CloudWatch Logs client."""
        if self._logs_client is None and get_config().is_lambda:
            with self._client_lock:
                # Double-check after acquiring lock
                if self._logs_client is None and get_config().is_lambda:
                    try:
                        logs_kwargs: dict[str, Any] = {
                            "service_name": "logs",
                            "region_name": get_config().aws_region,
                        }
                        if get_config().aws_access_key_id:
                            logs_kwargs["aws_access_key_id"] = get_config().aws_access_key_id
                            logs_kwargs["aws_secret_access_key"] = (
                                get_config().aws_secret_access_key
                            )
                        AWSClientManager._logs_client = boto3.client(**logs_kwargs)
                        app_logger.info("CloudWatch Logs client initialized")
                    except Exception as e:
                        app_logger.warning(f"Failed to initialize CloudWatch Logs client: {e!s}")
        return self._logs_client

    @property
    def executor(self) -> ThreadPoolExecutor | None:
        """Get the thread pool executor for async operations."""
        return self._executor


class BedrockService:
    """Service class for AWS Bedrock operations."""

    def __init__(self) -> None:
        """Initialize the Bedrock service."""
        self.client_manager = AWSClientManager()

    @log_performance
    def generate_image(self, request_body: str) -> bytes:
        """
        Generate image using Bedrock Nova Canvas model.

        Args:
            request_body: JSON string containing the generation parameters

        Returns:
            Raw image bytes

        Raises:
            BedrockError: If image generation fails
        """
        try:
            app_logger.info("Calling Bedrock invoke_model for image generation")

            body_bytes = (
                request_body.encode("utf-8") if isinstance(request_body, str) else request_body
            )

            response = self.client_manager.bedrock_client.invoke_model(
                body=body_bytes,
                modelId=get_config().nova_canvas_model,
                accept="application/json",
                contentType="application/json",
            )

            image_data = self._process_image_response(response)

            # Store response asynchronously (truly non-blocking now)
            self._store_response_async(request_body, image_data)

            return image_data

        except ClientError as e:
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            app_logger.error(f"Bedrock client error: {error_msg}")
            raise BedrockError(f"Image generation failed: {error_msg}") from e
        except Exception as e:
            app_logger.error(f"Unexpected error in image generation: {e!s}")
            raise BedrockError(f"Unexpected error: {e!s}") from e

    @log_performance
    def generate_prompt(self, messages: list[dict[str, Any]]) -> str:
        """
        Generate text prompt using Bedrock Nova Lite model.

        Args:
            messages: List of message dictionaries for the converse API

        Returns:
            Generated prompt text

        Raises:
            BedrockError: If prompt generation fails
        """
        try:
            app_logger.info("Calling Bedrock converse for prompt generation")

            response = self.client_manager.bedrock_client.converse(
                modelId=get_config().nova_lite_model,
                messages=cast("list[MessageTypeDef]", messages),
            )

            return self._process_text_response(response)

        except ClientError as e:
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            app_logger.error(f"Bedrock client error: {error_msg}")
            raise BedrockError(f"Prompt generation failed: {error_msg}") from e
        except Exception as e:
            app_logger.error(f"Unexpected error in prompt generation: {e!s}")
            raise BedrockError(f"Unexpected error: {e!s}") from e

    def _process_image_response(self, response: "InvokeModelResponseTypeDef") -> bytes:
        """
        Process Bedrock image response.

        Args:
            response: Raw response from Bedrock API

        Returns:
            Decoded image bytes

        Raises:
            BedrockError: If response format is invalid
        """
        try:
            response_body_stream = response.get("body")
            if not response_body_stream:
                raise BedrockError("Invalid response format: Missing body")

            response_body = json.loads(response_body_stream.read())
            app_logger.debug(f"Bedrock response keys: {list(response_body.keys())}")

            if (
                "images" in response_body
                and isinstance(response_body["images"], list)
                and len(response_body["images"]) > 0
            ):
                image_b64 = response_body["images"][0]
                app_logger.debug(f"Base64 image length: {len(image_b64)} characters")

                # Decode base64 to bytes
                image_bytes = base64.b64decode(image_b64)
                app_logger.info(f"Decoded image to {len(image_bytes)} bytes")

                return image_bytes
            elif "error" in response_body:
                raise BedrockError(f"Generation error: {response_body['error']}")
            else:
                raise BedrockError("Unexpected response format")

        except json.JSONDecodeError as e:
            raise BedrockError(f"Error decoding response: {e!s}") from e
        except BedrockError:
            raise
        except Exception as e:
            raise BedrockError(f"Error processing image response: {e!s}") from e

    def _process_text_response(self, response: "ConverseResponseTypeDef") -> str:
        """
        Process Bedrock text response.

        Args:
            response: Raw response from Bedrock converse API

        Returns:
            Extracted text content

        Raises:
            BedrockError: If response format is invalid
        """
        try:
            if "output" in response and "message" in response["output"]:
                message_content = response["output"]["message"]["content"]
                if (
                    message_content
                    and isinstance(message_content, list)
                    and len(message_content) > 0
                    and "text" in message_content[0]
                ):
                    return str(message_content[0]["text"])

            raise BedrockError("Unexpected converse response format")

        except BedrockError:
            raise
        except Exception as e:
            raise BedrockError(f"Error processing text response: {e!s}") from e

    def _store_response_async(self, request_body: str, image_data: bytes) -> None:
        """
        Store response to S3 asynchronously using thread pool (truly non-blocking).

        Args:
            request_body: The original request JSON
            image_data: The generated image bytes
        """
        executor = self.client_manager.executor
        if executor is not None:
            executor.submit(self._store_response_sync, request_body, image_data)
        else:
            # Fallback to sync if executor not available
            self._store_response_sync(request_body, image_data)

    def _store_response_sync(self, request_body: str, image_data: bytes) -> None:
        """
        Synchronous implementation of S3 storage.

        Args:
            request_body: The original request JSON
            image_data: The generated image bytes
        """
        try:
            timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S_%f")
            unique_id = uuid.uuid4().hex[:8]

            # Store response body
            response_key = f"responses/{timestamp}_{unique_id}_response.json"
            self.client_manager.s3_client.put_object(
                Bucket=get_config().nova_image_bucket,
                Key=response_key,
                Body=request_body,
                ContentType="application/json",
            )

            # Store image if present
            if image_data:
                image_key = f"images/{timestamp}_{unique_id}_image.png"
                self.client_manager.s3_client.put_object(
                    Bucket=get_config().nova_image_bucket,
                    Key=image_key,
                    Body=image_data,
                    ContentType="image/png",
                )

            app_logger.debug(f"Stored response and image to S3: {timestamp}")

        except Exception as e:
            # Don't fail the main operation if storage fails
            app_logger.warning(f"Failed to store response to S3: {e!s}")


_bedrock_service: BedrockService | None = None


def get_bedrock_service() -> BedrockService:
    """Get or create the BedrockService singleton."""
    global _bedrock_service
    if _bedrock_service is None:
        _bedrock_service = BedrockService()
    return _bedrock_service


def reset_bedrock_service() -> None:
    """Reset BedrockService for testing. Not for production use."""
    global _bedrock_service
    _bedrock_service = None
