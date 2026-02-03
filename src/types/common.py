"""Common type definitions for Canvas Demo application."""

from typing import (
    Generic,
    Literal,
    NotRequired,
    Protocol,
    TypedDict,
    TypeVar,
)

# Type aliases for constrained string values
QualityLevel = Literal["standard", "premium"]
ControlMode = Literal["CANNY_EDGE", "SEGMENTATION"]
OutpaintingMode = Literal["DEFAULT", "PRECISE"]
TaskType = Literal[
    "TEXT_IMAGE",
    "INPAINTING",
    "OUTPAINTING",
    "IMAGE_VARIATION",
    "COLOR_GUIDED_GENERATION",
    "BACKGROUND_REMOVAL",
]


class ImageGenerationConfig(TypedDict):
    """Configuration for Bedrock image generation."""

    numberOfImages: int
    height: int
    width: int
    quality: QualityLevel
    cfgScale: float
    seed: int


class RateLimitUsage(TypedDict):
    """Current rate limit usage statistics."""

    premium_requests: int
    standard_requests: int
    total_usage: int
    limit: int
    remaining: int


class RateLimitData(TypedDict):
    """Rate limit tracking data stored in S3."""

    premium: list[float]
    standard: list[float]


class TextToImageParams(TypedDict, total=False):
    """Parameters for text-to-image generation."""

    text: str
    negativeText: str
    controlMode: ControlMode
    controlStrength: float
    conditionImage: str


class InPaintingParams(TypedDict, total=False):
    """Parameters for inpainting operations."""

    image: str
    maskImage: str
    maskPrompt: str
    text: str
    negativeText: str


class OutPaintingParams(TypedDict, total=False):
    """Parameters for outpainting operations."""

    image: str
    maskImage: str
    maskPrompt: str
    text: str
    negativeText: str
    outPaintingMode: OutpaintingMode


class ImageVariationParams(TypedDict, total=False):
    """Parameters for image variation generation."""

    images: list[str]
    text: str
    negativeText: str
    similarityStrength: float


class ColorGuidedParams(TypedDict, total=False):
    """Parameters for color-guided generation."""

    text: str
    colors: list[str]
    referenceImage: str
    negativeText: str


class BackgroundRemovalParams(TypedDict):
    """Parameters for background removal."""

    image: str


class BedrockRequest(TypedDict, total=False):
    """Complete Bedrock API request structure."""

    taskType: TaskType
    textToImageParams: TextToImageParams
    inPaintingParams: InPaintingParams
    outPaintingParams: OutPaintingParams
    imageVariationParams: ImageVariationParams
    colorGuidedGenerationParams: ColorGuidedParams
    backgroundRemovalParams: BackgroundRemovalParams
    imageGenerationConfig: ImageGenerationConfig


class ServiceStatus(TypedDict):
    """Status of an individual service."""

    status: Literal["healthy", "unhealthy", "degraded", "error"]
    message: str
    region: NotRequired[str]
    bucket: NotRequired[str]
    issues: NotRequired[list[str]]


class MemoryInfo(TypedDict, total=False):
    """Memory usage information."""

    rss_mb: float
    vms_mb: float
    percent: float
    status: str


class MetricsInfo(TypedDict):
    """Performance metrics."""

    total_requests: int
    total_errors: int
    error_rate: float
    requests_per_second: float
    memory_info: MemoryInfo


class HealthStatus(TypedDict):
    """Complete health status response."""

    status: Literal["healthy", "unhealthy", "degraded", "error"]
    timestamp: str
    uptime_seconds: float
    uptime_human: str
    environment: Literal["lambda", "local"]
    version: str
    services: dict[str, ServiceStatus]
    metrics: MetricsInfo
    rate_limiting: RateLimitUsage


# Protocols for dependency injection and testing
class RateLimiterProtocol(Protocol):
    """Protocol for rate limiter implementations."""

    def check_rate_limit(self, request_body: str) -> None:
        """Check if request should be rate limited. Raises RateLimitError if exceeded."""
        ...

    def get_current_usage(self) -> RateLimitUsage:
        """Get current rate limit usage statistics."""
        ...


class ImageProcessorProtocol(Protocol):
    """Protocol for image processor implementations."""

    def process(self, check_nsfw: bool = True) -> str:
        """Process image and return base64 encoded string."""
        ...

    def encode(self) -> str:
        """Encode image to base64 string."""
        ...


# Generic Result type for operations that can fail
T = TypeVar("T")


class Result(Generic[T]):
    """
    Result type for operations that can fail.

    Provides a clean way to handle success/failure without exceptions
    for cases where failure is expected and part of normal flow.
    """

    __slots__ = ("_error", "_value")

    def __init__(self, value: T | None = None, error: str | None = None) -> None:
        self._value = value
        self._error = error

    @property
    def is_ok(self) -> bool:
        """Check if result is successful."""
        return self._error is None

    @property
    def is_err(self) -> bool:
        """Check if result is an error."""
        return self._error is not None

    @property
    def value(self) -> T:
        """Get the success value. Raises ValueError if result is an error."""
        if self._error is not None:
            raise ValueError(f"Result is an error: {self._error}")
        return self._value

    @property
    def error(self) -> str | None:
        """Get the error message, or None if successful."""
        return self._error

    def unwrap_or(self, default: T) -> T:
        """Get the value or return default if error."""
        if self._error is not None:
            return default
        return self._value

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        """Create a successful result."""
        return cls(value=value)

    @classmethod
    def err(cls, error: str) -> "Result[T]":
        """Create an error result."""
        return cls(error=error)

    def __repr__(self) -> str:
        if self._error is not None:
            return f"Result.err({self._error!r})"
        return f"Result.ok({self._value!r})"
