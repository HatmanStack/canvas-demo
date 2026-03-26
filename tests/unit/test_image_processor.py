"""Unit tests for image processor, including NSFW cache."""

import base64
import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.services.image_processor import (
    OptimizedImageProcessor,
    _NSFWCache,
    create_padded_image,
    process_and_encode_image,
    process_composite_to_mask,
)
from src.utils.exceptions import ImageError, NSFWError


class TestNSFWCache:
    """Tests for content-addressable NSFW cache."""

    def test_cache_miss_returns_none(self):
        """Test that a cache miss returns None."""
        cache = _NSFWCache(max_size=10)
        img = Image.new("RGB", (10, 10), color="red")
        assert cache.get(img) is None

    def test_cache_hit_after_put(self):
        """Test that a cached value is returned after put."""
        cache = _NSFWCache(max_size=10)
        img = Image.new("RGB", (10, 10), color="red")
        cache.put(img, False)
        assert cache.get(img) is False

    def test_cache_stores_nsfw_true(self):
        """Test that NSFW=True is cached correctly."""
        cache = _NSFWCache(max_size=10)
        img = Image.new("RGB", (10, 10), color="blue")
        cache.put(img, True)
        assert cache.get(img) is True

    def test_different_images_have_different_keys(self):
        """Test that different images produce different cache keys."""
        cache = _NSFWCache(max_size=10)
        img1 = Image.new("RGB", (10, 10), color="red")
        img2 = Image.new("RGB", (10, 10), color="blue")
        cache.put(img1, False)
        cache.put(img2, True)
        assert cache.get(img1) is False
        assert cache.get(img2) is True

    def test_fifo_eviction_at_max_size(self):
        """Test FIFO eviction when cache reaches max_size."""
        cache = _NSFWCache(max_size=2)
        img1 = Image.new("RGB", (10, 10), color="red")
        img2 = Image.new("RGB", (10, 10), color="green")
        img3 = Image.new("RGB", (10, 10), color="blue")

        cache.put(img1, False)
        cache.put(img2, True)
        # Cache is full, adding img3 should evict img1
        cache.put(img3, False)

        assert cache.get(img1) is None  # evicted
        assert cache.get(img2) is True  # still present
        assert cache.get(img3) is False  # newly added

    def test_identical_images_share_cache_key(self):
        """Test that identical images share the same cache key."""
        cache = _NSFWCache(max_size=10)
        img1 = Image.new("RGB", (10, 10), color="red")
        img2 = Image.new("RGB", (10, 10), color="red")
        cache.put(img1, True)
        # img2 has same content, should hit cache
        assert cache.get(img2) is True

    def test_large_image_does_not_allocate_full_tobytes(self):
        """Cache key for large image uses thumbnail, not full pixel data."""
        cache = _NSFWCache(max_size=10)
        img = Image.new("RGB", (2048, 2048), color="red")
        # Should not raise or cause excessive memory allocation
        cache.put(img, False)
        assert cache.get(img) is False

    def test_compute_key_consistency(self):
        """Same image always produces the same cache key."""
        cache = _NSFWCache(max_size=10)
        img = Image.new("RGB", (100, 100), color="green")
        key1 = cache._compute_key(img)
        key2 = cache._compute_key(img)
        assert key1 == key2


class TestOptimizedImageProcessor:
    """Tests for OptimizedImageProcessor."""

    def test_open_image_pil_passthrough(self):
        """PIL Image input is used directly."""
        img = Image.new("RGB", (512, 512), color="red")
        proc = OptimizedImageProcessor(img)
        assert proc.image is img

    def test_open_image_from_file_path(self, tmp_path):
        """String file path is opened correctly."""
        path = tmp_path / "test.png"
        Image.new("RGB", (64, 64), color="green").save(path)
        proc = OptimizedImageProcessor(str(path))
        assert proc.image.size == (64, 64)

    def test_open_image_from_bytesio(self):
        """BytesIO input is opened correctly."""
        buf = io.BytesIO()
        Image.new("RGB", (32, 32), color="blue").save(buf, format="PNG")
        buf.seek(0)
        proc = OptimizedImageProcessor(buf)
        assert proc.image.size == (32, 32)

    def test_open_image_none_raises(self):
        """None input raises ImageError."""
        with pytest.raises(ImageError, match="Input image is required"):
            OptimizedImageProcessor(None)

    def test_open_image_invalid_path_raises(self):
        """Invalid file path raises ImageError."""
        with pytest.raises(ImageError, match="Failed to open image"):
            OptimizedImageProcessor("/nonexistent/path.png")

    def test_convert_color_mode_rgb_noop(self):
        """RGB image is not modified."""
        img = Image.new("RGB", (256, 256), color="red")
        proc = OptimizedImageProcessor(img)
        proc._convert_color_mode()
        assert proc.image.mode == "RGB"

    def test_convert_color_mode_rgba_to_rgb(self):
        """RGBA is composited onto white background."""
        img = Image.new("RGBA", (256, 256), color=(255, 0, 0, 128))
        proc = OptimizedImageProcessor(img)
        proc._convert_color_mode()
        assert proc.image.mode == "RGB"

    def test_convert_color_mode_grayscale_to_rgb(self):
        """Grayscale L mode is converted to RGB."""
        img = Image.new("L", (256, 256), color=128)
        proc = OptimizedImageProcessor(img)
        proc._convert_color_mode()
        assert proc.image.mode == "RGB"

    def test_resize_for_pixels_no_resize_under_limit(self):
        """Image under pixel limit is not resized."""
        img = Image.new("RGB", (512, 512))
        proc = OptimizedImageProcessor(img)
        proc._resize_for_pixels(max_pixels=512 * 512 + 1)
        assert proc.image.size == (512, 512)

    def test_resize_for_pixels_downscale_large_image(self):
        """Large image is downscaled to fit pixel limit."""
        img = Image.new("RGB", (3000, 3000))
        proc = OptimizedImageProcessor(img)
        proc._resize_for_pixels(max_pixels=4194304)
        w, h = proc.image.size
        assert w * h <= 4194304
        assert w % 16 == 0
        assert h % 16 == 0

    def test_ensure_dimensions_clamp_too_small(self):
        """Small image is clamped up to min_size."""
        img = Image.new("RGB", (100, 100))
        proc = OptimizedImageProcessor(img)
        proc._ensure_dimensions(min_size=256, max_size=2048)
        w, h = proc.image.size
        assert w >= 256
        assert h >= 256

    def test_ensure_dimensions_clamp_too_large(self):
        """Large image is clamped down to max_size."""
        img = Image.new("RGB", (3000, 3000))
        proc = OptimizedImageProcessor(img)
        proc._ensure_dimensions(min_size=256, max_size=2048)
        w, h = proc.image.size
        assert w <= 2048
        assert h <= 2048

    def test_ensure_dimensions_extreme_aspect_ratio(self):
        """Extreme aspect ratio (>4:1) is corrected."""
        img = Image.new("RGB", (2048, 100))
        proc = OptimizedImageProcessor(img)
        proc._ensure_dimensions(min_size=256, max_size=2048)
        w, h = proc.image.size
        aspect = max(w / h, h / w)
        assert aspect <= 4.0

    def test_encode_returns_valid_base64(self):
        """Encode returns a decodable base64 string."""
        img = Image.new("RGB", (256, 256), color="red")
        proc = OptimizedImageProcessor(img)
        encoded = proc.encode()
        decoded = base64.b64decode(encoded)
        result_img = Image.open(io.BytesIO(decoded))
        assert result_img.size == (256, 256)

    def test_process_full_pipeline(self):
        """Process runs convert -> resize -> ensure -> encode."""
        img = Image.new("RGBA", (3000, 3000), color=(255, 0, 0, 128))
        proc = OptimizedImageProcessor(img)
        with patch.object(proc, "check_nsfw", return_value=False):
            result = proc.process(check_nsfw=False)
        decoded = base64.b64decode(result)
        result_img = Image.open(io.BytesIO(decoded))
        assert result_img.mode == "RGB"
        assert result_img.width * result_img.height <= 4194304

    def test_process_nsfw_cache_hit_raises(self):
        """Cached NSFW=True raises NSFWError without API call."""
        img = Image.new("RGB", (256, 256), color="red")
        proc = OptimizedImageProcessor(img)

        with patch("src.services.image_processor.get_config") as mock_get_config:
            mock_cfg = mock_get_config.return_value
            mock_cfg.enable_nsfw_check = True
            mock_cfg.max_pixels = 4194304
            mock_cfg.min_image_size = 256
            mock_cfg.max_image_size = 2048
            with patch("src.services.image_processor._nsfw_cache") as mock_cache:
                mock_cache.get.return_value = True
                with pytest.raises(NSFWError):
                    proc.process(check_nsfw=True)


class TestCheckNsfw:
    """Tests for synchronous NSFW check."""

    def test_nsfw_check_skips_when_disabled(self):
        """NSFW check returns None when disabled."""
        img = Image.new("RGB", (256, 256), color="red")
        proc = OptimizedImageProcessor(img)

        with patch("src.services.image_processor.get_config") as mock_get_config:
            mock_cfg = mock_get_config.return_value
            mock_cfg.enable_nsfw_check = False
            result = proc.check_nsfw()

        assert result is None

    def test_nsfw_check_skips_when_no_token(self):
        """NSFW check returns None when no HF token."""
        img = Image.new("RGB", (256, 256), color="red")
        proc = OptimizedImageProcessor(img)

        with patch("src.services.image_processor.get_config") as mock_get_config:
            mock_cfg = mock_get_config.return_value
            mock_cfg.enable_nsfw_check = True
            mock_cfg.hf_token = ""
            result = proc.check_nsfw()

        assert result is None

    def test_nsfw_check_returns_true_on_nsfw_content(self):
        """NSFW check returns True when API reports nsfw score > 0.5."""
        img = Image.new("RGB", (256, 256), color="red")
        proc = OptimizedImageProcessor(img)

        response_data = json.dumps([{"label": "nsfw", "score": 0.9}]).encode()

        with (
            patch("src.services.image_processor.get_config") as mock_get_config,
            patch("src.services.image_processor.urllib.request.urlopen") as mock_urlopen,
        ):
            mock_cfg = mock_get_config.return_value
            mock_cfg.enable_nsfw_check = True
            mock_cfg.hf_token = "test-token"
            mock_cfg.nsfw_api_url = "https://example.com/nsfw"
            mock_cfg.nsfw_timeout = 10
            mock_cfg.nsfw_max_retries = 1

            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.read.return_value = response_data
            mock_urlopen.return_value = mock_response

            result = proc.check_nsfw()

        assert result is True

    def test_nsfw_check_returns_false_on_safe_content(self):
        """NSFW check returns False when nsfw score < 0.5."""
        img = Image.new("RGB", (256, 256), color="red")
        proc = OptimizedImageProcessor(img)

        response_data = json.dumps([{"label": "nsfw", "score": 0.1}]).encode()

        with (
            patch("src.services.image_processor.get_config") as mock_get_config,
            patch("src.services.image_processor.urllib.request.urlopen") as mock_urlopen,
        ):
            mock_cfg = mock_get_config.return_value
            mock_cfg.enable_nsfw_check = True
            mock_cfg.hf_token = "test-token"
            mock_cfg.nsfw_api_url = "https://example.com/nsfw"
            mock_cfg.nsfw_timeout = 10
            mock_cfg.nsfw_max_retries = 1

            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.read.return_value = response_data
            mock_urlopen.return_value = mock_response

            result = proc.check_nsfw()

        assert result is False

    def test_nsfw_check_503_retry(self):
        """NSFW check retries on 503 errors."""
        img = Image.new("RGB", (256, 256), color="red")
        proc = OptimizedImageProcessor(img)

        with (
            patch("src.services.image_processor.get_config") as mock_get_config,
            patch("src.services.image_processor.urllib.request.urlopen") as mock_urlopen,
            patch("src.services.image_processor.time.sleep") as mock_sleep,
        ):
            mock_cfg = mock_get_config.return_value
            mock_cfg.enable_nsfw_check = True
            mock_cfg.hf_token = "test-token"
            mock_cfg.nsfw_api_url = "https://example.com/nsfw"
            mock_cfg.nsfw_timeout = 10
            mock_cfg.nsfw_max_retries = 2

            # First call: 503, second: success
            http_error = urllib.error.HTTPError(
                "https://example.com/nsfw",
                503,
                "Service Unavailable",
                {"Retry-After": "1"},
                None,
            )
            success_response = MagicMock()
            success_response.__enter__ = MagicMock(return_value=success_response)
            success_response.__exit__ = MagicMock(return_value=False)
            success_response.read.return_value = json.dumps(
                [{"label": "nsfw", "score": 0.1}]
            ).encode()

            mock_urlopen.side_effect = [http_error, success_response]

            result = proc.check_nsfw()

        assert result is False
        mock_sleep.assert_called_once_with(1)


class TestCreatePaddedImage:
    """Tests for create_padded_image."""

    def test_padding_doubles_dimensions(self):
        """100% padding roughly doubles each dimension."""
        img = Image.new("RGB", (200, 200), color="red")
        result = create_padded_image({"background": img}, padding_percent=100)
        assert result.size == (400, 400)

    def test_no_background_raises(self):
        """Missing background raises ImageError."""
        with pytest.raises(ImageError, match="No background image"):
            create_padded_image({})

    def test_rgb_converted_to_rgba(self):
        """RGB input is converted to RGBA before padding."""
        img = Image.new("RGB", (100, 100), color="green")
        result = create_padded_image({"background": img}, padding_percent=50)
        # Result is RGBA
        assert result.mode == "RGBA"


class TestProcessCompositeToMask:
    """Tests for process_composite_to_mask."""

    def test_transparent_mode(self):
        """transparent=True creates mask from non-white areas."""
        img = Image.new("RGBA", (100, 100), color=(255, 255, 255, 255))
        result = process_composite_to_mask(img, transparent=True)
        assert result.mode == "RGBA"
        assert result.size == (100, 100)

    def test_no_composite_mask_from_alpha(self):
        """Without composite, mask is created from transparent areas."""
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 0))
        result = process_composite_to_mask(img)
        assert result.mode == "L"
        assert result.size == (100, 100)

    def test_with_composite_difference_mask(self):
        """With composite, mask shows difference between original and composite."""
        original = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
        composite = Image.new("RGBA", (100, 100), color=(0, 255, 0, 255))
        result = process_composite_to_mask(original, composite)
        assert result.mode == "L"
        assert result.size == (100, 100)


class TestProcessAndEncodeImage:
    """Tests for process_and_encode_image convenience function."""

    def test_returns_base64_string(self):
        """Returns a valid base64 string."""
        img = Image.new("RGB", (512, 512), color="red")
        with patch("src.services.image_processor.get_config") as mock_get_config:
            mock_cfg = mock_get_config.return_value
            mock_cfg.enable_nsfw_check = False
            mock_cfg.max_pixels = 4194304
            mock_cfg.min_image_size = 256
            mock_cfg.max_image_size = 2048
            result = process_and_encode_image(img)
        assert isinstance(result, str)
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_handles_pil_image_input(self):
        """Handles PIL Image input directly."""
        img = Image.new("RGB", (256, 256), color="blue")
        with patch("src.services.image_processor.get_config") as mock_get_config:
            mock_cfg = mock_get_config.return_value
            mock_cfg.enable_nsfw_check = False
            mock_cfg.max_pixels = 4194304
            mock_cfg.min_image_size = 256
            mock_cfg.max_image_size = 2048
            result = process_and_encode_image(img)
        assert isinstance(result, str)
