"""Custom exceptions for the Canvas Demo application."""


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
