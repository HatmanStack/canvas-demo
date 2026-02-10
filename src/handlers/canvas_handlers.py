"""Handlers for all Canvas operations with improved error handling."""

import io
import json
import random
from pathlib import Path
from typing import Any

import gradio as gr
from PIL import Image

from src.services.aws_client import BedrockService, bedrock_service
from src.services.image_processor import (
    create_padded_image,
    process_and_encode_image,
    process_composite_to_mask,
)
from src.services.rate_limiter import OptimizedRateLimiter, rate_limiter
from src.types.common import (
    ControlMode,
    GradioImageMask,
    OutpaintingMode,
    QualityLevel,
    TaskType,
)
from src.utils.exceptions import (
    ImageError,
    NSFWError,
    RateLimitError,
)
from src.utils.logger import app_logger, log_performance
from src.utils.validation import (
    DEFAULT_COLORS,
    ValidationError,
    validate_hex_colors,
)

# Type aliases for Gradio return types
GradioImageResult = tuple[Image.Image | None, dict[str, Any]]
GradioTextResult = str


class CanvasHandlers:
    """Handlers for all Canvas operations with dependency injection."""

    def __init__(self, bedrock: BedrockService, limiter: OptimizedRateLimiter) -> None:
        self.bedrock = bedrock
        self.limiter = limiter

    def _build_request(
        self,
        task_type: TaskType,
        params: dict[str, Any],
        height: int = 1024,
        width: int = 1024,
        quality: QualityLevel = "standard",
        cfg_scale: float = 8.0,
        seed: int = 0,
    ) -> str:
        """Build standardized request for Bedrock."""
        param_dict = {
            "TEXT_IMAGE": "textToImageParams",
            "INPAINTING": "inPaintingParams",
            "OUTPAINTING": "outPaintingParams",
            "IMAGE_VARIATION": "imageVariationParams",
            "COLOR_GUIDED_GENERATION": "colorGuidedGenerationParams",
            "BACKGROUND_REMOVAL": "backgroundRemovalParams",
        }

        request_body = {
            "taskType": task_type,
            param_dict[task_type]: params,
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": height,
                "width": width,
                "quality": quality,
                "cfgScale": cfg_scale,
                "seed": seed,
            },
        }

        return json.dumps(request_body)

    def _process_response(self, result: Any) -> GradioImageResult:
        """Process response and return appropriate Gradio outputs."""
        app_logger.debug(f"Processing response type: {type(result)}")

        if isinstance(result, bytes):
            app_logger.info(f"Processing image bytes: {len(result)} bytes")

            try:
                image = Image.open(io.BytesIO(result))
                app_logger.info(f"Created PIL Image: {image.size}, mode: {image.mode}")
                return image, gr.update(value=None, visible=False)
            except Exception as e:
                app_logger.error(f"Failed to process image bytes: {e!s}")
                return None, gr.update(visible=True, value=f"Failed to process image: {e!s}")
        else:
            error_msg = str(result) if result else "Unknown error occurred"
            app_logger.error(f"Operation failed: {error_msg}")
            return None, gr.update(visible=True, value=error_msg)

    @log_performance
    def text_to_image(
        self,
        prompt: str,
        negative_text: str | None = None,
        height: int = 1024,
        width: int = 1024,
        quality: QualityLevel = "standard",
        cfg_scale: float = 8.0,
        seed: int = 0,
    ) -> GradioImageResult:
        """Generate image from text prompt."""
        app_logger.info("Starting text-to-image generation")

        if not prompt or not prompt.strip():
            return None, gr.update(visible=True, value="Please provide a text prompt")

        try:
            text_to_image_params: dict[str, Any] = {
                "text": prompt.strip(),
            }
            if negative_text and negative_text.strip():
                text_to_image_params["negativeText"] = negative_text.strip()

            body = self._build_request(
                "TEXT_IMAGE", text_to_image_params, height, width, quality, cfg_scale, seed
            )

            self.limiter.check_rate_limit(body)
            result = self.bedrock.generate_image(body)
            return self._process_response(result)

        except RateLimitError as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Text-to-image error: {e!s}")
            return None, gr.update(visible=True, value="Image generation failed. Please try again.")

    @log_performance
    def inpainting(
        self,
        mask_image: GradioImageMask | None,
        mask_prompt: str | None = None,
        text: str | None = None,
        negative_text: str | None = None,
        height: int = 1024,
        width: int = 1024,
        quality: QualityLevel = "standard",
        cfg_scale: float = 8.0,
        seed: int = 0,
    ) -> GradioImageResult:
        """Perform inpainting on masked areas."""
        app_logger.info("Starting inpainting operation")

        try:
            if not mask_image or "background" not in mask_image:
                return None, gr.update(visible=True, value="Please provide a base image")

            image_encoded = process_and_encode_image(mask_image["background"])

            mask_image_encoded: str | None = None

            if mask_prompt and mask_prompt.strip():
                app_logger.debug("Using mask prompt for inpainting")
            elif mask_image and isinstance(mask_image, dict) and "composite" in mask_image:
                app_logger.debug("Processing composite mask for inpainting")
                mask = process_composite_to_mask(mask_image["background"], mask_image["composite"])
                mask_image_encoded = process_and_encode_image(mask)
            else:
                return None, gr.update(
                    visible=True,
                    value="Please provide either a mask prompt or draw a mask on the image",
                )

            in_painting_params: dict[str, Any] = {"image": image_encoded}
            if mask_image_encoded:
                in_painting_params["maskImage"] = mask_image_encoded
            if mask_prompt and mask_prompt.strip():
                in_painting_params["maskPrompt"] = mask_prompt.strip()
            if text and text.strip():
                in_painting_params["text"] = text.strip()
            if negative_text and negative_text.strip():
                in_painting_params["negativeText"] = negative_text.strip()

            body = self._build_request(
                "INPAINTING", in_painting_params, height, width, quality, cfg_scale, seed
            )

            self.limiter.check_rate_limit(body)
            result = self.bedrock.generate_image(body)
            return self._process_response(result)

        except (ImageError, NSFWError, RateLimitError) as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Inpainting error: {e!s}")
            return None, gr.update(visible=True, value="Inpainting failed. Please try again.")

    @log_performance
    def outpainting(
        self,
        mask_image: GradioImageMask | None,
        mask_prompt: str | None = None,
        text: str | None = None,
        negative_text: str | None = None,
        outpainting_mode: OutpaintingMode = "DEFAULT",
        height: int = 1024,
        width: int = 1024,
        quality: QualityLevel = "standard",
        cfg_scale: float = 8.0,
        seed: int = 0,
    ) -> GradioImageResult:
        """Perform outpainting to extend image boundaries."""
        app_logger.info("Starting outpainting operation")

        try:
            if not mask_image or "background" not in mask_image:
                return None, gr.update(visible=True, value="Please provide a base image")

            image_encoded = process_and_encode_image(mask_image["background"])

            mask_image_encoded: str | None = None

            if mask_prompt and mask_prompt.strip():
                app_logger.debug("Using mask prompt for outpainting")
            elif mask_image and isinstance(mask_image, dict) and "composite" in mask_image:
                app_logger.debug("Processing composite mask for outpainting")
                mask = process_composite_to_mask(mask_image["background"], None)
                image_with_alpha = process_composite_to_mask(mask_image["background"], None, True)

                image_encoded = process_and_encode_image(image_with_alpha)
                mask_image_encoded = process_and_encode_image(mask)
            else:
                return None, gr.update(
                    visible=True,
                    value="Please provide either a mask prompt or draw a mask on the image",
                )

            out_painting_params: dict[str, Any] = {
                "image": image_encoded,
                "outPaintingMode": outpainting_mode,
            }
            if mask_image_encoded:
                out_painting_params["maskImage"] = mask_image_encoded
            if mask_prompt and mask_prompt.strip():
                out_painting_params["maskPrompt"] = mask_prompt.strip()
            out_painting_params["text"] = text.strip() if text and text.strip() else " "
            if negative_text and negative_text.strip():
                out_painting_params["negativeText"] = negative_text.strip()

            body = self._build_request(
                "OUTPAINTING", out_painting_params, height, width, quality, cfg_scale, seed
            )

            self.limiter.check_rate_limit(body)
            result = self.bedrock.generate_image(body)
            return self._process_response(result)

        except (ImageError, NSFWError, RateLimitError) as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Outpainting error: {e!s}")
            return None, gr.update(visible=True, value="Outpainting failed. Please try again.")

    @log_performance
    def update_mask_editor(self, img: dict[str, Any]) -> Image.Image | None:
        """Create padded image for mask editor."""
        try:
            if not img or "background" not in img or img["background"] is None:
                return None
            return create_padded_image(img)
        except Exception as e:
            app_logger.error(f"Error creating padded image: {e!s}")
            return None

    @log_performance
    def image_variation(
        self,
        images: list[str],
        text: str | None = None,
        negative_text: str | None = None,
        similarity_strength: float = 0.5,
        height: int = 1024,
        width: int = 1024,
        quality: QualityLevel = "standard",
        cfg_scale: float = 8.0,
        seed: int = 0,
    ) -> GradioImageResult:
        """Generate image variations."""
        app_logger.info("Starting image variation generation")

        try:
            if not images:
                return None, gr.update(
                    visible=True, value="Please provide at least one input image"
                )

            encoded_images: list[str] = []
            for image_path in images:
                encoded_image = process_and_encode_image(image_path)
                encoded_images.append(encoded_image)

            image_variation_params: dict[str, Any] = {"images": encoded_images}
            if similarity_strength is not None:
                image_variation_params["similarityStrength"] = similarity_strength
            if text and text.strip():
                image_variation_params["text"] = text.strip()
            if negative_text and negative_text.strip():
                image_variation_params["negativeText"] = negative_text.strip()

            body = self._build_request(
                "IMAGE_VARIATION",
                image_variation_params,
                height,
                width,
                quality,
                cfg_scale,
                seed,
            )

            self.limiter.check_rate_limit(body)
            result = self.bedrock.generate_image(body)
            return self._process_response(result)

        except (ImageError, NSFWError, RateLimitError) as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Image variation error: {e!s}")
            return None, gr.update(visible=True, value="Image variation failed. Please try again.")

    @log_performance
    def image_conditioning(
        self,
        condition_image: Image.Image,
        text: str,
        negative_text: str | None = None,
        control_mode: ControlMode = "CANNY_EDGE",
        control_strength: float = 0.7,
        height: int = 1024,
        width: int = 1024,
        quality: QualityLevel = "standard",
        cfg_scale: float = 8.0,
        seed: int = 0,
    ) -> GradioImageResult:
        """Generate image with conditioning."""
        app_logger.info("Starting image conditioning generation")

        try:
            if not condition_image:
                return None, gr.update(visible=True, value="Please provide a condition image")

            if not text or not text.strip():
                return None, gr.update(visible=True, value="Please provide a text prompt")

            condition_image_encoded = process_and_encode_image(condition_image)

            text_to_image_params: dict[str, Any] = {
                "text": text.strip(),
                "controlMode": control_mode,
                "controlStrength": control_strength,
                "conditionImage": condition_image_encoded,
            }
            if negative_text and negative_text.strip():
                text_to_image_params["negativeText"] = negative_text.strip()

            body = self._build_request(
                "TEXT_IMAGE", text_to_image_params, height, width, quality, cfg_scale, seed
            )

            self.limiter.check_rate_limit(body)
            result = self.bedrock.generate_image(body)
            return self._process_response(result)

        except (ImageError, NSFWError, RateLimitError) as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Image conditioning error: {e!s}")
            return None, gr.update(
                visible=True, value="Image conditioning failed. Please try again."
            )

    @log_performance
    def color_guided_content(
        self,
        text: str,
        reference_image: Image.Image | None = None,
        negative_text: str | None = None,
        colors: str | None = None,
        height: int = 1024,
        width: int = 1024,
        quality: QualityLevel = "standard",
        cfg_scale: float = 8.0,
        seed: int = 0,
    ) -> GradioImageResult:
        """Generate color-guided content."""
        app_logger.info("Starting color-guided generation")

        try:
            if not text or not text.strip():
                return None, gr.update(visible=True, value="Please provide a text prompt")

            reference_image_encoded: str | None = None
            if reference_image is not None:
                reference_image_encoded = process_and_encode_image(reference_image)

            try:
                validated_colors = validate_hex_colors(colors) if colors else []
                if not validated_colors:
                    validated_colors = DEFAULT_COLORS
            except ValidationError as e:
                return None, gr.update(visible=True, value=str(e))

            color_guided_params: dict[str, Any] = {
                "text": text.strip(),
                "colors": validated_colors,
            }
            if reference_image_encoded:
                color_guided_params["referenceImage"] = reference_image_encoded
            if negative_text and negative_text.strip():
                color_guided_params["negativeText"] = negative_text.strip()

            body = self._build_request(
                "COLOR_GUIDED_GENERATION",
                color_guided_params,
                height,
                width,
                quality,
                cfg_scale,
                seed,
            )

            self.limiter.check_rate_limit(body)
            result = self.bedrock.generate_image(body)
            return self._process_response(result)

        except (ImageError, NSFWError, RateLimitError) as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Color-guided generation error: {e!s}")
            return None, gr.update(
                visible=True, value="Color-guided generation failed. Please try again."
            )

    @log_performance
    def background_removal(self, image: Image.Image) -> GradioImageResult:
        """Remove background from image."""
        app_logger.info("Starting background removal")

        try:
            if not image:
                return None, gr.update(visible=True, value="Please provide an input image")

            input_image_encoded = process_and_encode_image(image)

            body = json.dumps(
                {
                    "taskType": "BACKGROUND_REMOVAL",
                    "backgroundRemovalParams": {"image": input_image_encoded},
                }
            )

            result = self.bedrock.generate_image(body)
            return self._process_response(result)

        except (ImageError, NSFWError, RateLimitError) as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Background removal error: {e!s}")
            return None, gr.update(
                visible=True, value="Background removal failed. Please try again."
            )

    @log_performance
    def generate_nova_prompt(self) -> GradioTextResult:
        """Generate creative prompt using Nova Lite."""
        app_logger.info("Starting prompt generation")

        try:
            with Path("seeds.json").open() as file:
                data = json.load(file)

            if "seeds" not in data or not isinstance(data["seeds"], list):
                raise ValueError("Invalid seeds file format")

            random_concept = random.choice(data["seeds"])
            app_logger.debug(f"Selected concept: {random_concept}")

            prompt = f"""
            Generate a creative image prompt that builds upon this concept: "{random_concept}"

            Requirements:
            - Create a new, expanded prompt without mentioning or repeating the original concept
            - Focus on vivid visual details and artistic elements
            - Keep the prompt under 1000 characters
            - Do not include any meta-instructions or seed references
            - Return only the new prompt text

            Response Format:
            [Just the new prompt text, nothing else]
            """

            messages = [{"role": "user", "content": [{"text": prompt}]}]
            result = self.bedrock.generate_prompt(messages)

            app_logger.info("Prompt generation completed")
            return result

        except Exception as e:
            app_logger.error(f"Prompt generation error: {e!s}")
            return f"Error generating prompt: {e!s}"


# Create global handlers instance with injected dependencies
canvas_handlers = CanvasHandlers(bedrock_service, rate_limiter)
