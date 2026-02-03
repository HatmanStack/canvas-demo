"""Tests for validation utilities."""

import pytest

from src.utils.validation import (
    ValidationError,
    validate_hex_color,
    validate_hex_colors,
    is_error_response,
    validate_prompt,
    validate_dimensions,
    validate_seed,
    validate_cfg_scale,
    MIN_ENCODED_IMAGE_LENGTH,
    DEFAULT_COLORS,
)


class TestValidateHexColor:
    """Tests for validate_hex_color function."""

    def test_valid_lowercase_color(self):
        """Test valid lowercase hex color."""
        assert validate_hex_color("#ff5733") == "#FF5733"

    def test_valid_uppercase_color(self):
        """Test valid uppercase hex color."""
        assert validate_hex_color("#FF5733") == "#FF5733"

    def test_valid_mixed_case_color(self):
        """Test valid mixed case hex color."""
        assert validate_hex_color("#Ff5733") == "#FF5733"

    def test_color_with_whitespace(self):
        """Test color with leading/trailing whitespace."""
        assert validate_hex_color("  #ff5733  ") == "#FF5733"

    def test_invalid_color_no_hash(self):
        """Test color without hash prefix."""
        with pytest.raises(ValidationError, match="Invalid hex color format"):
            validate_hex_color("ff5733")

    def test_invalid_color_short(self):
        """Test color that's too short."""
        with pytest.raises(ValidationError, match="Invalid hex color format"):
            validate_hex_color("#fff")

    def test_invalid_color_long(self):
        """Test color that's too long."""
        with pytest.raises(ValidationError, match="Invalid hex color format"):
            validate_hex_color("#ff5733aa")

    def test_invalid_color_non_hex(self):
        """Test color with non-hex characters."""
        with pytest.raises(ValidationError, match="Invalid hex color format"):
            validate_hex_color("#gggggg")


class TestValidateHexColors:
    """Tests for validate_hex_colors function."""

    def test_valid_colors_string(self):
        """Test valid comma-separated colors."""
        result = validate_hex_colors("#ff5733,#33ff57,#3357ff")
        assert result == ["#FF5733", "#33FF57", "#3357FF"]

    def test_colors_with_spaces(self):
        """Test colors with spaces around them."""
        result = validate_hex_colors(" #ff5733 , #33ff57 ")
        assert result == ["#FF5733", "#33FF57"]

    def test_empty_string(self):
        """Test empty string returns empty list."""
        assert validate_hex_colors("") == []

    def test_none_input(self):
        """Test None input returns empty list."""
        assert validate_hex_colors(None) == []

    def test_whitespace_only(self):
        """Test whitespace-only string returns empty list."""
        assert validate_hex_colors("   ") == []

    def test_too_many_colors(self):
        """Test that too many colors raises error."""
        colors = ",".join([f"#{i:06x}" for i in range(15)])
        with pytest.raises(ValidationError, match="Maximum 10 colors"):
            validate_hex_colors(colors)

    def test_one_invalid_color(self):
        """Test that one invalid color raises error."""
        with pytest.raises(ValidationError, match="Invalid hex color format"):
            validate_hex_colors("#ff5733,invalid,#3357ff")


class TestIsErrorResponse:
    """Tests for is_error_response function."""

    def test_short_string_is_error(self):
        """Test that short string is considered error."""
        assert is_error_response("Error: something failed") is True

    def test_long_string_is_not_error(self):
        """Test that long string is not considered error."""
        long_string = "a" * (MIN_ENCODED_IMAGE_LENGTH + 1)
        assert is_error_response(long_string) is False

    def test_exact_threshold(self):
        """Test string at exact threshold."""
        exact = "a" * MIN_ENCODED_IMAGE_LENGTH
        assert is_error_response(exact) is False

    def test_empty_string(self):
        """Test empty string is error."""
        assert is_error_response("") is True


class TestValidatePrompt:
    """Tests for validate_prompt function."""

    def test_valid_prompt(self):
        """Test valid prompt passes."""
        assert validate_prompt("A beautiful sunset") == "A beautiful sunset"

    def test_prompt_with_whitespace(self):
        """Test prompt with whitespace is trimmed."""
        assert validate_prompt("  A sunset  ") == "A sunset"

    def test_empty_prompt(self):
        """Test empty prompt raises error."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_prompt("")

    def test_none_prompt(self):
        """Test None prompt raises error."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_prompt(None)

    def test_too_long_prompt(self):
        """Test prompt exceeding max length."""
        long_prompt = "a" * 1025
        with pytest.raises(ValidationError, match="at most 1024"):
            validate_prompt(long_prompt)


class TestValidateDimensions:
    """Tests for validate_dimensions function."""

    def test_valid_dimensions(self):
        """Test valid dimensions pass."""
        assert validate_dimensions(1024, 1024) == (1024, 1024)

    def test_too_small_width(self):
        """Test width below minimum."""
        with pytest.raises(ValidationError, match="Width must be between"):
            validate_dimensions(100, 1024)

    def test_too_large_height(self):
        """Test height above maximum."""
        with pytest.raises(ValidationError, match="Height must be between"):
            validate_dimensions(1024, 3000)

    def test_not_divisible_by_step(self):
        """Test dimensions not divisible by step."""
        with pytest.raises(ValidationError, match="divisible by"):
            validate_dimensions(1000, 1024)

    def test_extreme_aspect_ratio(self):
        """Test aspect ratio exceeding 4:1."""
        with pytest.raises(ValidationError, match="Aspect ratio"):
            validate_dimensions(2048, 256)


class TestValidateSeed:
    """Tests for validate_seed function."""

    def test_valid_seed(self):
        """Test valid seed passes."""
        assert validate_seed(12345) == 12345

    def test_zero_seed(self):
        """Test zero seed is valid."""
        assert validate_seed(0) == 0

    def test_negative_seed(self):
        """Test negative seed raises error."""
        with pytest.raises(ValidationError, match="Seed must be between"):
            validate_seed(-1)


class TestValidateCfgScale:
    """Tests for validate_cfg_scale function."""

    def test_valid_cfg_scale(self):
        """Test valid CFG scale passes."""
        assert validate_cfg_scale(8.0) == 8.0

    def test_min_cfg_scale(self):
        """Test minimum CFG scale is valid."""
        assert validate_cfg_scale(1.0) == 1.0

    def test_max_cfg_scale(self):
        """Test maximum CFG scale is valid."""
        assert validate_cfg_scale(20.0) == 20.0

    def test_below_min(self):
        """Test CFG scale below minimum."""
        with pytest.raises(ValidationError, match="CFG scale must be between"):
            validate_cfg_scale(0.5)

    def test_above_max(self):
        """Test CFG scale above maximum."""
        with pytest.raises(ValidationError, match="CFG scale must be between"):
            validate_cfg_scale(25.0)


class TestDefaultColors:
    """Tests for DEFAULT_COLORS constant."""

    def test_default_colors_count(self):
        """Test default colors has 10 entries."""
        assert len(DEFAULT_COLORS) == 10

    def test_default_colors_are_valid(self):
        """Test all default colors are valid hex colors."""
        for color in DEFAULT_COLORS:
            # Should not raise
            validate_hex_color(color)
