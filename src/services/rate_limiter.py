"""Rate limiter with S3 optimistic locking for distributed environments."""

import json
import threading
import time
from typing import Final

import requests
from botocore.exceptions import ClientError

from src.models.config import config
from src.services.aws_client import AWSClientManager
from src.types.common import RateLimitData, RateLimitUsage
from src.utils.exceptions import RateLimitError
from src.utils.logger import app_logger, log_performance


class OptimizedRateLimiter:
    """
    Thread-safe rate limiter using S3 optimistic locking with ETags.

    Uses conditional writes (If-Match header) to prevent race conditions
    when multiple Lambda instances update rate limit data simultaneously.
    """

    # Configuration constants
    WINDOW_SIZE_SECONDS: Final[int] = 1200  # 20 minutes
    MAX_RETRIES: Final[int] = 3
    S3_KEY: Final[str] = "rate-limit/jsonData.json"

    # Thread safety
    _lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        """Initialize the rate limiter."""
        self.client_manager = AWSClientManager()

        # User-friendly rate limit message
        self.rate_limit_message: str = (
            "<div style='text-align: center;'>Rate limit exceeded. "
            "Try again later or use the "
            "<a href='https://docs.aws.amazon.com/bedrock/latest/userguide/playgrounds.html'>"
            "Bedrock Playground</a>.</div>"
        )

    @log_performance
    def check_rate_limit(self, request_body: str) -> None:
        """
        Check if request should be rate limited using S3 optimistic locking.

        This method atomically checks and increments the rate counter using
        ETag-based optimistic concurrency control.

        Args:
            request_body: JSON string containing the request parameters

        Raises:
            RateLimitError: If rate limit is exceeded
        """
        try:
            # Parse quality from request
            body_dict = json.loads(request_body)
            quality = body_dict.get("imageGenerationConfig", {}).get("quality", "standard")

            # Perform atomic check-and-increment
            allowed = self._check_and_increment_atomic(quality)

            if not allowed:
                app_logger.warning(f"Rate limit exceeded for {quality} request")
                raise RateLimitError(self.rate_limit_message)

        except json.JSONDecodeError as e:
            app_logger.error("Invalid JSON in request body for rate limiting")
            raise RateLimitError("Invalid request format") from e
        except RateLimitError:
            raise
        except Exception as e:
            app_logger.error(f"Rate limiting error: {e!s}")
            # Fail open - allow request if rate limiting system fails
            app_logger.warning("Rate limit check failed, allowing request")

    def _check_and_increment_atomic(self, quality: str) -> bool:
        """
        Atomically check rate limit and increment counter using optimistic locking.

        Uses S3 ETag for optimistic concurrency control:
        1. GET object with ETag
        2. Check if under limit
        3. PUT with If-Match condition
        4. Retry on conflict (412 Precondition Failed)

        Args:
            quality: Request quality level ("standard" or "premium")

        Returns:
            True if request is allowed, False if rate limited
        """
        cost = 2 if quality == "premium" else 1

        for attempt in range(self.MAX_RETRIES):
            try:
                # Step 1: Get current rate data with ETag
                rate_data, etag = self._get_rate_data_with_etag()

                # Step 2: Clean old entries and check limit
                current_time = time.time()
                self._clean_old_entries(rate_data, current_time)
                total = self._calculate_total(rate_data)

                if total + cost > config.rate_limit:
                    return False  # Rate limited

                # Step 3: Add current request
                rate_data[quality].append(current_time)

                # Step 4: Attempt conditional PUT with ETag
                success = self._conditional_put(rate_data, etag)

                if success:
                    app_logger.debug(f"Rate check passed: {total + cost}/{config.rate_limit}")
                    return True

                # If conditional PUT failed, retry
                app_logger.debug(f"Optimistic lock conflict, retrying (attempt {attempt + 1})")

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "NoSuchKey":
                    # First request - initialize the file
                    return self._initialize_rate_data(quality)
                raise

        # After max retries, fail open (allow request)
        app_logger.warning(
            f"Rate limit check failed after {self.MAX_RETRIES} retries, allowing request"
        )
        return True

    def _get_rate_data_with_etag(self) -> tuple[RateLimitData, str]:
        """
        Get rate data from S3 with ETag for conditional updates.

        Returns:
            Tuple of (rate_data dict, etag string)

        Raises:
            ClientError: If S3 operation fails
        """
        response = self.client_manager.s3_client.get_object(
            Bucket=config.nova_image_bucket,
            Key=self.S3_KEY,
        )

        etag = response["ETag"]
        body = response["Body"].read().decode("utf-8")
        rate_data: RateLimitData = json.loads(body)

        # Ensure required keys exist
        if "premium" not in rate_data:
            rate_data["premium"] = []
        if "standard" not in rate_data:
            rate_data["standard"] = []

        return rate_data, etag

    def _conditional_put(self, rate_data: RateLimitData, etag: str) -> bool:
        """
        Perform conditional PUT using If-Match header.

        boto3 doesn't directly support If-Match for put_object, so we use
        presigned URL with requests library.

        Args:
            rate_data: Updated rate data to write
            etag: ETag from the GET request for conditional write

        Returns:
            True if write succeeded, False if precondition failed (conflict)
        """
        try:
            # Generate presigned URL for PUT
            presigned_url = self.client_manager.s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": config.nova_image_bucket,
                    "Key": self.S3_KEY,
                },
                ExpiresIn=60,
            )

            # Perform PUT with If-Match header
            # Note: ETag from S3 includes quotes, strip them for If-Match
            clean_etag = etag.strip('"')

            response = requests.put(
                presigned_url,
                data=json.dumps(rate_data),
                headers={
                    "Content-Type": "application/json",
                    "If-Match": clean_etag,
                },
                timeout=10,
            )

            if response.status_code == 412:
                # Precondition Failed - another writer updated the object
                return False

            response.raise_for_status()
            return True

        except requests.exceptions.RequestException as e:
            app_logger.warning(f"Conditional PUT failed: {e!s}")
            return False

    def _initialize_rate_data(self, quality: str) -> bool:
        """
        Initialize rate data file for first request.

        Args:
            quality: Quality level of the first request

        Returns:
            True (first request is always allowed)
        """
        with self._lock:
            try:
                rate_data: RateLimitData = {
                    "premium": [],
                    "standard": [],
                }
                rate_data[quality].append(time.time())

                self.client_manager.s3_client.put_object(
                    Bucket=config.nova_image_bucket,
                    Key=self.S3_KEY,
                    Body=json.dumps(rate_data),
                    ContentType="application/json",
                )

                app_logger.info("Initialized rate limit data in S3")
                return True

            except Exception as e:
                app_logger.warning(f"Failed to initialize rate data: {e!s}")
                return True  # Fail open

    def _clean_old_entries(self, rate_data: RateLimitData, current_time: float) -> None:
        """
        Remove entries older than the window size.

        Args:
            rate_data: Rate data to clean (modified in place)
            current_time: Current timestamp
        """
        cutoff = current_time - self.WINDOW_SIZE_SECONDS

        rate_data["premium"] = [t for t in rate_data.get("premium", []) if t > cutoff]
        rate_data["standard"] = [t for t in rate_data.get("standard", []) if t > cutoff]

    def _calculate_total(self, rate_data: RateLimitData) -> int:
        """
        Calculate total weighted request count.

        Premium requests count as 2, standard as 1.

        Args:
            rate_data: Rate data to calculate from

        Returns:
            Total weighted request count
        """
        premium_count = len(rate_data.get("premium", []))
        standard_count = len(rate_data.get("standard", []))
        return premium_count * 2 + standard_count

    def get_current_usage(self) -> RateLimitUsage:
        """
        Get current rate limit usage for monitoring.

        Returns:
            Dictionary with usage statistics
        """
        try:
            rate_data, _ = self._get_rate_data_with_etag()
            current_time = time.time()
            self._clean_old_entries(rate_data, current_time)

            premium_count = len(rate_data.get("premium", []))
            standard_count = len(rate_data.get("standard", []))
            total_requests = premium_count * 2 + standard_count

            return {
                "premium_requests": premium_count,
                "standard_requests": standard_count,
                "total_usage": total_requests,
                "limit": config.rate_limit,
                "remaining": max(0, config.rate_limit - total_requests),
            }

        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                # No rate data yet
                return {
                    "premium_requests": 0,
                    "standard_requests": 0,
                    "total_usage": 0,
                    "limit": config.rate_limit,
                    "remaining": config.rate_limit,
                }
            app_logger.error(f"Failed to get current usage: {e!s}")
            return {
                "premium_requests": 0,
                "standard_requests": 0,
                "total_usage": 0,
                "limit": config.rate_limit,
                "remaining": config.rate_limit,
            }
        except Exception as e:
            app_logger.error(f"Failed to get current usage: {e!s}")
            return {
                "premium_requests": 0,
                "standard_requests": 0,
                "total_usage": 0,
                "limit": config.rate_limit,
                "remaining": config.rate_limit,
            }


# Global rate limiter instance
rate_limiter = OptimizedRateLimiter()
