"""Rate limiter with S3-backed tracking for distributed environments."""

import json
import time
from typing import Final

from botocore.exceptions import ClientError

from src.models.config import config
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
            app_logger.error(f"Rate limiting error: {e!s}")
            # Fail open - allow request if rate limiting system fails
            app_logger.warning("Rate limit check failed, allowing request")

    def _check_and_increment(self, quality: str) -> bool:
        """
        Check rate limit and increment counter.

        Args:
            quality: Request quality level ("standard" or "premium")

        Returns:
            True if request is allowed, False if rate limited
        """
        cost = 2 if quality == "premium" else 1

        try:
            rate_data = self._get_rate_data()
            current_time = time.time()
            self._clean_old_entries(rate_data, current_time)
            total = self._calculate_total(rate_data)

            if total + cost > config.rate_limit:
                return False

            if quality == "premium":
                rate_data["premium"].append(current_time)
            else:
                rate_data["standard"].append(current_time)

            self._put_rate_data(rate_data)
            app_logger.debug(f"Rate check passed: {total + cost}/{config.rate_limit}")
            return True

        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                return self._initialize_rate_data(quality)
            app_logger.warning(f"Rate limit check failed: {e!s}")
            return True  # Fail open

    def _get_rate_data(self) -> RateLimitData:
        """
        Get rate data from S3.

        Returns:
            Rate limit data dict

        Raises:
            ClientError: If S3 operation fails
        """
        response = self.client_manager.s3_client.get_object(
            Bucket=config.nova_image_bucket,
            Key=self.S3_KEY,
        )

        body = response["Body"].read().decode("utf-8")
        rate_data: RateLimitData = json.loads(body)

        if "premium" not in rate_data:
            rate_data["premium"] = []
        if "standard" not in rate_data:
            rate_data["standard"] = []

        return rate_data

    def _put_rate_data(self, rate_data: RateLimitData) -> None:
        """Write rate data to S3."""
        self.client_manager.s3_client.put_object(
            Bucket=config.nova_image_bucket,
            Key=self.S3_KEY,
            Body=json.dumps(rate_data),
            ContentType="application/json",
        )

    def _initialize_rate_data(self, quality: str) -> bool:
        """
        Initialize rate data file for first request.

        Args:
            quality: Quality level of the first request

        Returns:
            True (first request is always allowed)
        """
        try:
            rate_data: RateLimitData = {
                "premium": [],
                "standard": [],
            }
            if quality == "premium":
                rate_data["premium"].append(time.time())
            else:
                rate_data["standard"].append(time.time())

            self._put_rate_data(rate_data)
            app_logger.info("Initialized rate limit data in S3")
            return True

        except Exception as e:
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
            "limit": config.rate_limit,
            "remaining": config.rate_limit,
        }

    def get_current_usage(self) -> RateLimitUsage:
        """Get current rate limit usage for monitoring."""
        try:
            rate_data = self._get_rate_data()
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
                return self._empty_usage()
            app_logger.error(f"Failed to get current usage: {e!s}")
            return self._empty_usage()
        except Exception as e:
            app_logger.error(f"Failed to get current usage: {e!s}")
            return self._empty_usage()


# Global rate limiter instance
rate_limiter = OptimizedRateLimiter()
