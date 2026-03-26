"""Rate limiter with S3-backed tracking for distributed environments."""

import json
import time
from typing import Any, Final

from botocore.exceptions import ClientError

from src.models.config import get_config
from src.services.aws_client import AWSClientManager
from src.types.common import RateLimitData, RateLimitUsage
from src.utils.exceptions import RateLimitError
from src.utils.logger import app_logger, log_performance


class OptimizedRateLimiter:
    """
    Rate limiter using S3 for distributed tracking.

    Uses simple GET → check → PUT for a 20-req/20-min demo app.
    Eventual consistency is acceptable at this scale.
    """

    # Configuration constants
    WINDOW_SIZE_SECONDS: Final[int] = 1200  # 20 minutes
    S3_KEY: Final[str] = "rate-limit/jsonData.json"

    def __init__(self) -> None:
        """Initialize the rate limiter."""
        self.client_manager = AWSClientManager()

        self.rate_limit_message: str = (
            "<div style='text-align: center;'>Rate limit exceeded. "
            "Try again later or use the "
            "<a href='https://docs.aws.amazon.com/bedrock/latest/userguide/playgrounds.html'>"
            "Bedrock Playground</a>.</div>"
        )

    @log_performance
    def check_rate_limit(self, request_body: str) -> None:
        """
        Check if request should be rate limited.

        Args:
            request_body: JSON string containing the request parameters

        Raises:
            RateLimitError: If rate limit is exceeded
        """
        try:
            body_dict = json.loads(request_body)
            quality = body_dict.get("imageGenerationConfig", {}).get("quality", "standard")

            allowed = self._check_and_increment(quality)

            if not allowed:
                app_logger.warning(f"Rate limit exceeded for {quality} request")
                raise RateLimitError(self.rate_limit_message)

        except json.JSONDecodeError as e:
            app_logger.error("Invalid JSON in request body for rate limiting")
            raise RateLimitError("Invalid request format") from e
        except RateLimitError:
            raise
        except Exception as e:
            app_logger.error(
                f"Rate limiter fail-open: {type(e).__name__}: {e!s}. "
                "Request allowed despite rate limit check failure."
            )

    def _check_and_increment(self, quality: str) -> bool:
        """
        Check rate limit and increment counter with optimistic locking.

        Args:
            quality: Request quality level ("standard" or "premium")

        Returns:
            True if request is allowed, False if rate limited
        """
        cost = 2 if quality == "premium" else 1
        max_retries = 3

        for attempt in range(max_retries):
            try:
                rate_data, etag = self._get_rate_data()
                current_time = time.time()
                self._clean_old_entries(rate_data, current_time)
                total = self._calculate_total(rate_data)

                if total + cost > get_config().rate_limit:
                    return False

                if quality == "premium":
                    rate_data["premium"].append(current_time)
                else:
                    rate_data["standard"].append(current_time)

                try:
                    self._put_rate_data(rate_data, etag)
                    app_logger.debug(f"Rate check passed: {total + cost}/{get_config().rate_limit}")
                    return True
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "")
                    if error_code == "PreconditionFailed" and attempt < max_retries - 1:
                        app_logger.debug(
                            f"Rate limit ETag conflict, retrying (attempt {attempt + 1})"
                        )
                        continue
                    raise

            except ClientError as e:
                if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                    return self._initialize_rate_data(quality)
                app_logger.warning(
                    f"Rate limit S3 error (fail-open): "
                    f"{e.response.get('Error', {}).get('Code', 'unknown')}. "
                    "Request allowed."
                )
                return True  # Fail open

        app_logger.warning("Rate limit check exhausted retries, allowing request")
        return True  # Fail open after max retries

    def _get_rate_data(self) -> tuple[RateLimitData, str]:
        """
        Get rate data and ETag from S3.

        Returns:
            Tuple of (rate limit data dict, ETag string)

        Raises:
            ClientError: If S3 operation fails
        """
        response = self.client_manager.s3_client.get_object(
            Bucket=get_config().nova_image_bucket,
            Key=self.S3_KEY,
        )

        etag = response.get("ETag", "")
        body = response["Body"].read().decode("utf-8")
        rate_data: RateLimitData = json.loads(body)

        if "premium" not in rate_data:
            rate_data["premium"] = []
        if "standard" not in rate_data:
            rate_data["standard"] = []

        return rate_data, etag

    def _put_rate_data(self, rate_data: RateLimitData, etag: str = "") -> None:
        """Write rate data to S3 with optimistic locking."""
        kwargs: dict[str, Any] = {
            "Bucket": get_config().nova_image_bucket,
            "Key": self.S3_KEY,
            "Body": json.dumps(rate_data),
            "ContentType": "application/json",
        }
        if etag:
            kwargs["IfMatch"] = etag
        self.client_manager.s3_client.put_object(**kwargs)

    def _initialize_rate_data(self, quality: str) -> bool:
        """
        Initialize rate data file for first request using conditional write.

        Uses If-None-Match to prevent concurrent creators from overwriting
        each other. If the conditional write fails (object already exists),
        retries through the normal optimistic-locking read-modify-write flow.

        Args:
            quality: Quality level of the first request

        Returns:
            True if request is allowed, False if rate limited
        """
        rate_data: RateLimitData = {
            "premium": [],
            "standard": [],
        }
        if quality == "premium":
            rate_data["premium"].append(time.time())
        else:
            rate_data["standard"].append(time.time())

        try:
            self.client_manager.s3_client.put_object(
                Bucket=get_config().nova_image_bucket,
                Key=self.S3_KEY,
                Body=json.dumps(rate_data),
                ContentType="application/json",
                IfNoneMatch="*",
            )
            app_logger.info("Initialized rate limit data in S3")
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("PreconditionFailed", "ConditionalCheckFailedException"):
                # Another invocation created it first; retry through normal flow
                app_logger.debug("Race on rate data init, retrying via optimistic lock")
                return self._check_and_increment(quality)
            app_logger.warning(f"Failed to initialize rate data: {e!s}")
            return True  # Fail open

    def _clean_old_entries(self, rate_data: RateLimitData, current_time: float) -> None:
        """Remove entries older than the window size."""
        cutoff = current_time - self.WINDOW_SIZE_SECONDS

        rate_data["premium"] = [t for t in rate_data.get("premium", []) if t > cutoff]
        rate_data["standard"] = [t for t in rate_data.get("standard", []) if t > cutoff]

    def _calculate_total(self, rate_data: RateLimitData) -> int:
        """Calculate total weighted request count (premium=2, standard=1)."""
        premium_count = len(rate_data.get("premium", []))
        standard_count = len(rate_data.get("standard", []))
        return premium_count * 2 + standard_count

    @classmethod
    def _empty_usage(cls) -> RateLimitUsage:
        """Return a zero-value usage dict for fallback responses."""
        return {
            "premium_requests": 0,
            "standard_requests": 0,
            "total_usage": 0,
            "limit": get_config().rate_limit,
            "remaining": get_config().rate_limit,
        }

    def get_current_usage(self) -> RateLimitUsage:
        """Get current rate limit usage for monitoring."""
        try:
            rate_data, _etag = self._get_rate_data()
            current_time = time.time()
            self._clean_old_entries(rate_data, current_time)

            premium_count = len(rate_data.get("premium", []))
            standard_count = len(rate_data.get("standard", []))
            total_requests = premium_count * 2 + standard_count

            return {
                "premium_requests": premium_count,
                "standard_requests": standard_count,
                "total_usage": total_requests,
                "limit": get_config().rate_limit,
                "remaining": max(0, get_config().rate_limit - total_requests),
            }

        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                return self._empty_usage()
            app_logger.error(f"Failed to get current usage: {e!s}")
            return self._empty_usage()
        except Exception as e:
            app_logger.error(f"Failed to get current usage: {e!s}")
            return self._empty_usage()


_rate_limiter: OptimizedRateLimiter | None = None


def get_rate_limiter() -> OptimizedRateLimiter:
    """Get or create the rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = OptimizedRateLimiter()
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset rate limiter for testing. Not for production use."""
    global _rate_limiter
    _rate_limiter = None
