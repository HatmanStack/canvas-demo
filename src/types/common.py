"""Common type definitions for Canvas Demo application."""

from typing import (
    Literal,
    NotRequired,
    TypedDict,
)

from PIL import Image

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


class GradioImageMask(TypedDict, total=False):
    """Gradio ImageMask dict structure."""

    background: Image.Image
    composite: Image.Image
    layers: list[Image.Image]
