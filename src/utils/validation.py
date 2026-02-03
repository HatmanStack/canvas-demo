"""Input validation utilities for Canvas Demo application."""

from typing import Final
import re

# Constants
HEX_COLOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^#[0-9A-Fa-f]{6}$")
MIN_ENCODED_IMAGE_LENGTH: Final[int] = 200
MAX_PROMPT_LENGTH: Final[int] = 1024
MIN_PROMPT_LENGTH: Final[int] = 1
MAX_COLORS: Final[int] = 10

# Default color palette when none provided
DEFAULT_COLORS: Final[list[str]] = [
    "#FF5733",
    "#33FF57",
    "#3357FF",
    "#FF33A1",
    "#33FFF5",
    "#FF8C33",
    "#8C33FF",
    "#33FF8C",
    "#FF3333",
    "#33A1FF",
]


class ValidationError(ValueError):
    """Raised when input validation fails."""

    pass


def validate_hex_color(color: str) -> str:
    """
    Validate a single hex color string.

    Args:
        color: Hex color string (e.g., "#FF5733")

    Returns:
        Uppercase validated hex color

    Raises:
        ValidationError: If color format is invalid
    """
    color = color.strip()
    if not HEX_COLOR_PATTERN.match(color):
        raise ValidationError(
            f"Invalid hex color format: '{color}'. Expected format: #RRGGBB"
        )
    return color.upper()


def validate_hex_colors(
    colors_str: str | None, max_colors: int = MAX_COLORS
) -> list[str]:
    """
    Validate and parse comma-separated hex colors.

    Args:
        colors_str: Comma-separated hex color string
        max_colors: Maximum number of colors allowed

    Returns:
        List of validated uppercase hex colors

    Raises:
        ValidationError: If any color format is invalid or too many colors
    """
    if not colors_str or not colors_str.strip():
        return []

    colors = [c.strip() for c in colors_str.split(",") if c.strip()]

    if len(colors) > max_colors:
        raise ValidationError(
            f"Maximum {max_colors} colors allowed, got {len(colors)}"
        )

    return [validate_hex_color(c) for c in colors]


def is_error_response(encoded_data: str) -> bool:
    """
    Check if encoded string is an error message rather than image data.

    Base64-encoded images are always longer than error messages.

    Args:
        encoded_data: String that is either base64 image or error message

    Returns:
        True if the string appears to be an error message
    """
    return len(encoded_data) < MIN_ENCODED_IMAGE_LENGTH


def validate_prompt(
    prompt: str | None,
    min_length: int = MIN_PROMPT_LENGTH,
    max_length: int = MAX_PROMPT_LENGTH,
) -> str:
    """
    Validate text prompt.

    Args:
        prompt: Text prompt to validate
        min_length: Minimum allowed length
        max_length: Maximum allowed length

    Returns:
        Stripped and validated prompt

    Raises:
        ValidationError: If prompt is empty or exceeds length limits
    """
    if not prompt or not prompt.strip():
        raise ValidationError("Prompt cannot be empty")

    prompt = prompt.strip()

    if len(prompt) < min_length:
        raise ValidationError(f"Prompt must be at least {min_length} characters")

    if len(prompt) > max_length:
        raise ValidationError(f"Prompt must be at most {max_length} characters")

    return prompt


def validate_dimensions(
    width: int, height: int, min_size: int = 256, max_size: int = 2048, step: int = 16
) -> tuple[int, int]:
    """
    Validate image dimensions.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        min_size: Minimum dimension size
        max_size: Maximum dimension size
        step: Dimensions must be divisible by this value

    Returns:
        Tuple of (validated_width, validated_height)

    Raises:
        ValidationError: If dimensions are out of range or not divisible by step
    """
    errors: list[str] = []

    if width < min_size or width > max_size:
        errors.append(f"Width must be between {min_size} and {max_size}, got {width}")

    if height < min_size or height > max_size:
        errors.append(
            f"Height must be between {min_size} and {max_size}, got {height}"
        )

    if width % step != 0:
        errors.append(f"Width must be divisible by {step}, got {width}")

    if height % step != 0:
        errors.append(f"Height must be divisible by {step}, got {height}")

    # Check aspect ratio (1:4 to 4:1)
    aspect_ratio = max(width / height, height / width)
    if aspect_ratio > 4:
        errors.append(
            f"Aspect ratio must be between 1:4 and 4:1, got {width}:{height}"
        )

    if errors:
        raise ValidationError("; ".join(errors))

    return width, height


def validate_seed(seed: int, min_seed: int = 0, max_seed: int = 2147483647) -> int:
    """
    Validate random seed value.

    Args:
        seed: Seed value to validate
        min_seed: Minimum allowed seed
        max_seed: Maximum allowed seed

    Returns:
        Validated seed

    Raises:
        ValidationError: If seed is out of range
    """
    if seed < min_seed or seed > max_seed:
        raise ValidationError(f"Seed must be between {min_seed} and {max_seed}")
    return seed


def validate_cfg_scale(
    cfg_scale: float, min_scale: float = 1.0, max_scale: float = 20.0
) -> float:
    """
    Validate CFG scale value.

    Args:
        cfg_scale: CFG scale to validate
        min_scale: Minimum allowed scale
        max_scale: Maximum allowed scale

    Returns:
        Validated CFG scale

    Raises:
        ValidationError: If scale is out of range
    """
    if cfg_scale < min_scale or cfg_scale > max_scale:
        raise ValidationError(
            f"CFG scale must be between {min_scale} and {max_scale}"
        )
    return cfg_scale
