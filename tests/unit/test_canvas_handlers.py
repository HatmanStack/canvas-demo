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
        """Test handling of empty prompt via validate_prompt."""
        image, update = handlers.text_to_image("")

        assert image is None
        assert update["visible"] is True
        assert "empty" in update["value"].lower()

    def test_text_to_image_prompt_too_long(self, handlers):
        """Test handling of prompt exceeding max length."""
        long_prompt = "x" * 1025

        image, update = handlers.text_to_image(long_prompt)

        assert image is None
        assert update["visible"] is True
        assert "1024" in update["value"]

    def test_text_to_image_invalid_seed(self, handlers):
        """Test handling of invalid seed value."""
        image, update = handlers.text_to_image("a prompt", seed=-1)

        assert image is None
        assert update["visible"] is True
        assert "Seed" in update["value"]

    def test_text_to_image_invalid_cfg_scale(self, handlers):
        """Test handling of invalid cfg_scale value."""
        image, update = handlers.text_to_image("a prompt", cfg_scale=25.0)

        assert image is None
        assert update["visible"] is True
        assert "CFG scale" in update["value"]

    def test_text_to_image_invalid_dimensions(self, handlers):
        """Test handling of invalid dimensions."""
        image, update = handlers.text_to_image("a prompt", width=100, height=100)

        assert image is None
        assert update["visible"] is True
        assert "Width" in update["value"] or "Height" in update["value"]

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

    def test_image_conditioning_empty_text(self, handlers):
        """Test image conditioning with empty text via validate_prompt."""
        img = Image.new("RGB", (100, 100), color="blue")
        image, update = handlers.image_conditioning(img, "")

        assert image is None
        assert update["visible"] is True
        assert "empty" in update["value"].lower()

    def test_color_guided_empty_text(self, handlers):
        """Test color-guided generation with empty text via validate_prompt."""
        image, update = handlers.color_guided_content("")

        assert image is None
        assert update["visible"] is True
        assert "empty" in update["value"].lower()

    def test_gradio_handler_catches_generic_exception(self, handlers, mock_bedrock):
        """Test that gradio_handler catches unexpected exceptions."""
        mock_bedrock.generate_image.side_effect = RuntimeError("Unexpected")

        image, update = handlers.text_to_image("a prompt")

        assert image is None
        assert update["visible"] is True
        assert "Text-to-image failed" in update["value"]

    def test_image_variation_parallel_processing(self, handlers, mock_bedrock, img_bytes):
        """Test image variation processes multiple images."""
        mock_bedrock.generate_image.return_value = img_bytes

        long_base64 = "a" * 201
        with patch(
            "src.handlers.canvas_handlers.process_and_encode_image", return_value=long_base64
        ):
            image, update = handlers.image_variation(["path1.png", "path2.png", "path3.png"])

            assert image is not None
            assert update["visible"] is False

    def test_inpainting_with_mask_prompt_success(self, handlers, mock_bedrock, img_bytes):
        """Test inpainting using mask_prompt (no composite mask needed)."""
        mock_bedrock.generate_image.return_value = img_bytes
        mask_image = {"background": Image.new("RGB", (10, 10))}
        long_base64 = "a" * 201

        with patch(
            "src.handlers.canvas_handlers.process_and_encode_image", return_value=long_base64
        ):
            image, update = handlers.inpainting(
                mask_image=mask_image,
                mask_prompt="the sky",
                text="a sunset",
            )

            assert image is not None
            assert update["visible"] is False
            mock_bedrock.generate_image.assert_called_once()

    def test_inpainting_no_mask_no_prompt_error(self, handlers):
        """Test inpainting with background but no mask and no prompt returns error."""
        mask_image = {"background": Image.new("RGB", (10, 10))}
        long_base64 = "a" * 201

        with patch(
            "src.handlers.canvas_handlers.process_and_encode_image", return_value=long_base64
        ):
            image, update = handlers.inpainting(mask_image=mask_image)

        assert image is None
        assert update["visible"] is True
        assert "mask" in update["value"].lower()

    def test_outpainting_with_mask_prompt_success(self, handlers, mock_bedrock, img_bytes):
        """Test outpainting using mask_prompt instead of drawn mask."""
        mock_bedrock.generate_image.return_value = img_bytes
        mask_image = {"background": Image.new("RGB", (10, 10))}
        long_base64 = "a" * 201

        with patch(
            "src.handlers.canvas_handlers.process_and_encode_image", return_value=long_base64
        ):
            image, update = handlers.outpainting(
                mask_image=mask_image,
                mask_prompt="the edges",
                text="expand the scene",
            )

            assert image is not None
            assert update["visible"] is False

    def test_image_conditioning_success(self, handlers, mock_bedrock, img_bytes):
        """Test image conditioning with condition_image + text."""
        mock_bedrock.generate_image.return_value = img_bytes
        condition_img = Image.new("RGB", (100, 100), color="blue")
        long_base64 = "a" * 201

        with patch(
            "src.handlers.canvas_handlers.process_and_encode_image", return_value=long_base64
        ):
            image, update = handlers.image_conditioning(
                condition_image=condition_img, text="a castle"
            )

            assert image is not None
            assert update["visible"] is False

    def test_image_conditioning_none_image(self, handlers):
        """Test image conditioning with None image returns error."""
        image, update = handlers.image_conditioning(condition_image=None, text="a castle")

        assert image is None
        assert update["visible"] is True
        assert "condition image" in update["value"].lower()

    def test_color_guided_no_reference_image(self, handlers, mock_bedrock, img_bytes):
        """Test color-guided generation without reference image."""
        mock_bedrock.generate_image.return_value = img_bytes

        with patch("src.handlers.canvas_handlers.process_and_encode_image", return_value="a" * 201):
            image, update = handlers.color_guided_content(
                text="a sunset",
                colors="#FF5733,#33FF57",
            )

            assert image is not None
            assert update["visible"] is False

    def test_color_guided_with_reference_image(self, handlers, mock_bedrock, img_bytes):
        """Test color-guided generation with reference image."""
        mock_bedrock.generate_image.return_value = img_bytes
        ref_img = Image.new("RGB", (100, 100), color="purple")

        with patch("src.handlers.canvas_handlers.process_and_encode_image", return_value="a" * 201):
            image, update = handlers.color_guided_content(
                text="a sunset",
                reference_image=ref_img,
                colors="#FF5733",
            )

            assert image is not None
            assert update["visible"] is False

    def test_color_guided_default_colors(self, handlers, mock_bedrock, img_bytes):
        """Test color-guided generation uses default colors when none provided."""
        mock_bedrock.generate_image.return_value = img_bytes

        with patch("src.handlers.canvas_handlers.process_and_encode_image", return_value="a" * 201):
            image, update = handlers.color_guided_content(text="a sunset")

            assert image is not None
            assert update["visible"] is False
            # Verify default colors were used in the request
            call_args = mock_bedrock.generate_image.call_args[0][0]
            import json

            body = json.loads(call_args)
            assert len(body["colorGuidedGenerationParams"]["colors"]) == 10

    def test_update_mask_editor_success(self, handlers):
        """Test update_mask_editor returns padded PIL Image."""
        img = Image.new("RGB", (200, 200), color="red")
        result = handlers.update_mask_editor({"background": img})

        assert isinstance(result, Image.Image)
        assert result.size[0] > 200
        assert result.size[1] > 200

    def test_update_mask_editor_none_input(self, handlers):
        """Test update_mask_editor with None returns None."""
        result = handlers.update_mask_editor(None)
        assert result is None

    def test_update_mask_editor_empty_dict(self, handlers):
        """Test update_mask_editor with empty dict returns None."""
        result = handlers.update_mask_editor({})
        assert result is None
