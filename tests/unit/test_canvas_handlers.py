"""Unit tests for CanvasHandlers."""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.handlers.canvas_handlers import CanvasHandlers
from src.utils.exceptions import RateLimitError


class TestCanvasHandlers:
    """Tests for CanvasHandlers class."""

    @pytest.fixture
    def mock_deps(self):
        """Mock external dependencies."""
        with patch("src.handlers.canvas_handlers.bedrock_service") as mock_bedrock, \
             patch("src.handlers.canvas_handlers.rate_limiter") as mock_limiter:
            yield mock_bedrock, mock_limiter

    def test_text_to_image_success(self, mock_deps):
        """Test successful text-to-image generation."""
        mock_bedrock, mock_limiter = mock_deps

        # Mock successful response
        # Create a real small image bytes
        img = Image.new('RGB', (10, 10), color='red')
        import io
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_bytes = img_byte_arr.getvalue()

        mock_bedrock.generate_image.return_value = img_bytes

        image, update = CanvasHandlers.text_to_image("a cute sloth")

        assert image is not None
        assert isinstance(image, Image.Image)
        assert update['visible'] is False
        mock_limiter.check_rate_limit.assert_called_once()
        mock_bedrock.generate_image.assert_called_once()

    def test_text_to_image_rate_limit(self, mock_deps):
        """Test rate limit handling."""
        mock_bedrock, mock_limiter = mock_deps
        mock_limiter.check_rate_limit.side_effect = RateLimitError("Too many requests")

        image, update = CanvasHandlers.text_to_image("a cute sloth")

        assert image is None
        assert update['visible'] is True
        assert "Too many requests" in update['value']
        mock_bedrock.generate_image.assert_not_called()

    def test_text_to_image_empty_prompt(self):
        """Test handling of empty prompt."""
        image, update = CanvasHandlers.text_to_image("")

        assert image is None
        assert update['visible'] is True
        assert "Please provide a text prompt" in update['value']

    def test_inpainting_no_mask(self):
        """Test inpainting without mask."""
        image, update = CanvasHandlers.inpainting(None)

        assert image is None
        assert update['visible'] is True
        assert "Please provide a base image" in update['value']

    def test_image_variation_no_images(self):
        """Test image variation without input images."""
        image, update = CanvasHandlers.image_variation([])

        assert image is None
        assert update['visible'] is True
        assert "Please provide at least one input image" in update['value']

    def test_background_removal_success(self, mock_deps):
        """Test successful background removal."""
        mock_bedrock, _ = mock_deps

        # Mock Image
        img = Image.new('RGB', (100, 100), color='blue')

        # Mock response
        import io
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_bytes = img_byte_arr.getvalue()
        mock_bedrock.generate_image.return_value = img_bytes

        # Mock validation
        # The base64 string needs to be long enough (>200 chars) to pass is_error_response check
        long_base64 = "a" * 201
        with patch("src.handlers.canvas_handlers.process_and_encode_image") as mock_process:
            mock_process.return_value = long_base64

            image, update = CanvasHandlers.background_removal(img)

            assert image is not None, f"Background removal failed: {update['value']}"
            assert update['visible'] is False
            mock_bedrock.generate_image.assert_called_once()

    def test_outpainting_success(self, mock_deps):
        """Test successful outpainting."""
        mock_bedrock, _ = mock_deps

        # Mock Inputs
        mask_image = {"background": "bg_path", "composite": "comp_path"}

        # Mock response
        img = Image.new('RGB', (100, 100), color='green')
        import io
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_bytes = img_byte_arr.getvalue()
        mock_bedrock.generate_image.return_value = img_bytes

        long_base64 = "a" * 201

        with patch("src.handlers.canvas_handlers.process_and_encode_image", return_value=long_base64), \
             patch("src.handlers.canvas_handlers.process_composite_to_mask", return_value="mask_path"):

            image, update = CanvasHandlers.outpainting(
                mask_image=mask_image,
                outpainting_mode="DEFAULT"
            )

            assert image is not None, f"Outpainting failed: {update['value']}"
            assert update['visible'] is False

    def test_generate_nova_prompt(self, mock_deps):
        """Test nova prompt generation."""
        mock_bedrock, _ = mock_deps
        mock_bedrock.generate_prompt.return_value = "A creative prompt"

        with patch("builtins.open", new_callable=MagicMock) as mock_open:
            mock_file = MagicMock()
            mock_file.__enter__.return_value = mock_file
            mock_open.return_value = mock_file
            # Mock json.load
            with patch("json.load", return_value={"seeds": ["concept1", "concept2"]}):
                result = CanvasHandlers.generate_nova_prompt()
                assert result == "A creative prompt"

