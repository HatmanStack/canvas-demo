"""Custom exceptions for the Canvas Demo application."""

from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class CanvasError(Exception):
    """Base exception for Canvas Demo application."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ImageError(CanvasError):
    """Exception raised for image processing errors."""

    pass


class NSFWError(ImageError):
    """Exception raised when content is flagged as NSFW."""

    def __init__(self, message: str = "Content flagged as inappropriate") -> None:
        super().__init__(message, "NSFW_DETECTED")


class RateLimitError(CanvasError):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message, "RATE_LIMIT_EXCEEDED")


class ConfigurationError(CanvasError):
    """Exception raised for configuration issues."""

    def __init__(self, message: str = "Configuration error") -> None:
        super().__init__(message, "CONFIG_ERROR")


class ExternalAPIError(CanvasError):
    """Exception raised for external API failures."""

    def __init__(self, message: str = "External API error", service: str | None = None) -> None:
        self.service = service
        super().__init__(message, "EXTERNAL_API_ERROR")


class BedrockError(ExternalAPIError):
    """Exception raised for AWS Bedrock service errors."""

    def __init__(self, message: str = "Bedrock service error") -> None:
        super().__init__(message, "bedrock")


def handle_gracefully(
    default_return: Any = None, log_error: bool = True
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to handle exceptions gracefully with fallback values.

    Args:
        default_return: Value to return when an exception occurs
        log_error: Whether to log the error

    Returns:
        Decorated function that catches exceptions and returns default value
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_error:
                    from src.utils.logger import app_logger

                    app_logger.error(f"Error in {func.__name__}: {e!s}")
                return default_return  # type: ignore

        return wrapper

    return decorator
