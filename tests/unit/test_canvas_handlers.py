"""Unit tests for CanvasHandlers."""

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.handlers.canvas_handlers import CanvasHandlers
from src.utils.exceptions import ImageError, NSFWError, RateLimitError


class TestCanvasHandlers:
    """Tests for CanvasHandlers class."""

    @pytest.fixture
    def mock_bedrock(self):
        """Mock BedrockService."""
        return MagicMock()

    @pytest.fixture
    def mock_limiter(self):
        """Mock OptimizedRateLimiter."""
        return MagicMock()

    @pytest.fixture
    def handlers(self, mock_bedrock, mock_limiter):
        """Create CanvasHandlers with mocked dependencies."""
        return CanvasHandlers(mock_bedrock, mock_limiter)

    @pytest.fixture
    def img_bytes(self):
        """Create real PNG bytes for testing."""
        img = Image.new("RGB", (10, 10), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_text_to_image_success(self, handlers, mock_bedrock, mock_limiter, img_bytes):
        """Test successful text-to-image generation."""
        mock_bedrock.generate_image.return_value = img_bytes

        image, update = handlers.text_to_image("a cute sloth")

        assert image is not None
        assert isinstance(image, Image.Image)
        assert update["visible"] is False
        mock_limiter.check_rate_limit.assert_called_once()
        mock_bedrock.generate_image.assert_called_once()

    def test_text_to_image_rate_limit(self, handlers, mock_bedrock, mock_limiter):
        """Test rate limit handling."""
        mock_limiter.check_rate_limit.side_effect = RateLimitError("Too many requests")

        image, update = handlers.text_to_image("a cute sloth")

        assert image is None
        assert update["visible"] is True
        assert "Too many requests" in update["value"]
        mock_bedrock.generate_image.assert_not_called()

    def test_text_to_image_empty_prompt(self, handlers):
        """Test handling of empty prompt."""
        image, update = handlers.text_to_image("")

        assert image is None
        assert update["visible"] is True
        assert "Please provide a text prompt" in update["value"]

    def test_inpainting_no_mask(self, handlers):
        """Test inpainting without mask."""
        image, update = handlers.inpainting(None)

        assert image is None
        assert update["visible"] is True
        assert "Please provide a base image" in update["value"]

    def test_inpainting_image_error(self, handlers):
        """Test inpainting with image processing error."""
        mask_image = {
            "background": Image.new("RGB", (10, 10)),
            "composite": Image.new("RGB", (10, 10)),
        }

        with patch(
            "src.handlers.canvas_handlers.process_and_encode_image",
            side_effect=ImageError("Bad image"),
        ):
            image, update = handlers.inpainting(mask_image)

        assert image is None
        assert update["visible"] is True
        assert "Bad image" in update["value"]

    def test_image_variation_no_images(self, handlers):
        """Test image variation without input images."""
        image, update = handlers.image_variation([])

        assert image is None
        assert update["visible"] is True
        assert "Please provide at least one input image" in update["value"]

    def test_background_removal_success(self, handlers, mock_bedrock, img_bytes):
        """Test successful background removal."""
        mock_bedrock.generate_image.return_value = img_bytes
        img = Image.new("RGB", (100, 100), color="blue")

        long_base64 = "a" * 201
        with patch("src.handlers.canvas_handlers.process_and_encode_image") as mock_process:
            mock_process.return_value = long_base64

            image, update = handlers.background_removal(img)

            assert image is not None, f"Background removal failed: {update['value']}"
            assert update["visible"] is False
            mock_bedrock.generate_image.assert_called_once()

    def test_background_removal_nsfw_error(self, handlers):
        """Test background removal with NSFW error."""
        img = Image.new("RGB", (100, 100), color="blue")

        with patch(
            "src.handlers.canvas_handlers.process_and_encode_image",
            side_effect=NSFWError("Inappropriate content"),
        ):
            image, update = handlers.background_removal(img)

        assert image is None
        assert update["visible"] is True
        assert "Inappropriate content" in update["value"]

    def test_outpainting_success(self, handlers, mock_bedrock, img_bytes):
        """Test successful outpainting."""
        mock_bedrock.generate_image.return_value = img_bytes
        mask_image = {"background": "bg_path", "composite": "comp_path"}

        long_base64 = "a" * 201

        with (
            patch(
                "src.handlers.canvas_handlers.process_and_encode_image", return_value=long_base64
            ),
            patch(
                "src.handlers.canvas_handlers.process_composite_to_mask", return_value="mask_path"
            ),
        ):
            image, update = handlers.outpainting(mask_image=mask_image, outpainting_mode="DEFAULT")

            assert image is not None, f"Outpainting failed: {update['value']}"
            assert update["visible"] is False

    def test_generate_nova_prompt(self, handlers, mock_bedrock):
        """Test nova prompt generation."""
        mock_bedrock.generate_prompt.return_value = "A creative prompt"

        with patch("builtins.open", new_callable=MagicMock) as mock_open:
            mock_file = MagicMock()
            mock_file.__enter__.return_value = mock_file
            mock_open.return_value = mock_file
            with patch("json.load", return_value={"seeds": ["concept1", "concept2"]}):
                result = handlers.generate_nova_prompt()
                assert result == "A creative prompt"
