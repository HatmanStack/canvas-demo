import json
import os
import gradio as gr
from typing import Tuple, Optional, Any, List
from PIL import Image
from src.models.config import config
from src.services.aws_client import bedrock_service
from src.services.rate_limiter import rate_limiter
from src.services.image_processor import (
    process_and_encode_image, 
    create_padded_image, 
    process_composite_to_mask
)
from src.utils.logger import app_logger, log_performance
from src.utils.exceptions import CanvasError, RateLimitError, NSFWError, handle_gracefully
from src.utils.lambda_helpers import lambda_image_handler

class CanvasHandlers:
    """Optimized handlers for all Canvas operations with improved error handling"""
    
    @staticmethod
    def _build_request(task_type: str, params: dict, height: int = 1024, width: int = 1024, 
                      quality: str = "standard", cfg_scale: float = 8.0, seed: int = 0) -> str:
        """Build standardized request for Bedrock"""
        param_dict = {
            "TEXT_IMAGE": "textToImageParams",
            "INPAINTING": "inPaintingParams", 
            "OUTPAINTING": "outPaintingParams",
            "IMAGE_VARIATION": "imageVariationParams",
            "COLOR_GUIDED_GENERATION": "colorGuidedGenerationParams",
            "BACKGROUND_REMOVAL": "backgroundRemovalParams"
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
                "seed": seed
            }
        }
        
        return json.dumps(request_body)
    
    @staticmethod
    def _process_response(result: Any) -> Tuple[Optional[Image.Image], dict]:
        """Process response and return appropriate Gradio outputs"""
        app_logger.debug(f"Processing response type: {type(result)}")
        
        if isinstance(result, bytes):
            # Success - return image
            import io
            app_logger.info(f"Processing image bytes: {len(result)} bytes")
            
            try:
                # Create PIL Image from bytes
                image = Image.open(io.BytesIO(result))
                app_logger.info(f"Created PIL Image: {image.size}, mode: {image.mode}")
                
                # Simple approach that works in Lambda - just return PIL Image directly
                app_logger.info(f"Returning PIL Image directly: {image.size}, mode: {image.mode}")
                return image, gr.update(value=None, visible=False)
                
            except Exception as e:
                app_logger.error(f"Failed to process image bytes: {str(e)}")
                return None, gr.update(visible=True, value=f"Failed to process image: {str(e)}")
        else:
            # Error - return error message
            error_msg = str(result) if result else "Unknown error occurred"
            app_logger.error(f"Operation failed: {error_msg}")
            return None, gr.update(visible=True, value=error_msg)
    
    @staticmethod
    @log_performance
    @handle_gracefully(default_return=(None, gr.update(visible=True, value="Service temporarily unavailable")))
    def text_to_image(prompt: str, negative_text: Optional[str] = None, height: int = 1024, 
                     width: int = 1024, quality: str = "standard", cfg_scale: float = 8.0, 
                     seed: int = 0) -> Tuple[Optional[Image.Image], dict]:
        """Generate image from text prompt"""
        app_logger.info("Starting text-to-image generation")
        
        if not prompt or not prompt.strip():
            return None, gr.update(visible=True, value="Please provide a text prompt")
        
        try:
            text_to_image_params = {
                "text": prompt.strip(),
                **({"negativeText": negative_text.strip()} if negative_text and negative_text.strip() else {})
            }
            
            body = CanvasHandlers._build_request("TEXT_IMAGE", text_to_image_params, 
                                               height, width, quality, cfg_scale, seed)
            
            # Check rate limit
            rate_limiter.check_rate_limit(body)
            
            # Generate image
            result = bedrock_service.generate_image(body)
            return CanvasHandlers._process_response(result)
            
        except RateLimitError as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Text-to-image error: {str(e)}")
            return None, gr.update(visible=True, value="Image generation failed. Please try again.")
    
    @staticmethod
    @log_performance  
    @handle_gracefully(default_return=(None, gr.update(visible=True, value="Service temporarily unavailable")))
    def inpainting(mask_image: dict, mask_prompt: Optional[str] = None, text: Optional[str] = None,
                  negative_text: Optional[str] = None, height: int = 1024, width: int = 1024,
                  quality: str = "standard", cfg_scale: float = 8.0, seed: int = 0) -> Tuple[Optional[Image.Image], dict]:
        """Perform inpainting on masked areas"""
        app_logger.info("Starting inpainting operation")
        
        try:
            # Validate inputs
            if not mask_image or 'background' not in mask_image:
                return None, gr.update(visible=True, value="Please provide a base image")
            
            # Process background image
            image_encoded = process_and_encode_image(mask_image['background'])
            if len(image_encoded) < 200:  # Error message check
                return None, gr.update(visible=True, value=image_encoded)
            
            mask_image_encoded = None
            
            # Handle mask input - prioritize mask_prompt
            if mask_prompt and mask_prompt.strip():
                app_logger.debug("Using mask prompt for inpainting")
                # mask_image_encoded remains None when using mask_prompt
            elif mask_image and isinstance(mask_image, dict) and 'composite' in mask_image:
                app_logger.debug("Processing composite mask for inpainting")
                mask = process_composite_to_mask(mask_image['background'], mask_image['composite'])
                mask_image_encoded = process_and_encode_image(mask)
                
                if not mask_image_encoded or len(mask_image_encoded) < 200:
                    return None, gr.update(visible=True, value="Error processing mask image")
            else:
                return None, gr.update(visible=True, value="Please provide either a mask prompt or draw a mask on the image")
            
            # Build parameters
            in_painting_params = {
                "image": image_encoded,
                **({"maskImage": mask_image_encoded} if mask_image_encoded else {}),
                **({"maskPrompt": mask_prompt.strip()} if mask_prompt and mask_prompt.strip() else {}),
                **({"text": text.strip()} if text and text.strip() else {}),
                **({"negativeText": negative_text.strip()} if negative_text and negative_text.strip() else {})
            }
            
            body = CanvasHandlers._build_request("INPAINTING", in_painting_params,
                                               height, width, quality, cfg_scale, seed)
            
            # Check rate limit and generate
            rate_limiter.check_rate_limit(body)
            result = bedrock_service.generate_image(body)
            return CanvasHandlers._process_response(result)
            
        except (NSFWError, RateLimitError) as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Inpainting error: {str(e)}")
            return None, gr.update(visible=True, value="Inpainting failed. Please try again.")
    
    @staticmethod
    @log_performance
    @handle_gracefully(default_return=(None, gr.update(visible=True, value="Service temporarily unavailable")))
    def outpainting(mask_image: dict, mask_prompt: Optional[str] = None, text: Optional[str] = None,
                   negative_text: Optional[str] = None, outpainting_mode: str = "DEFAULT",
                   height: int = 1024, width: int = 1024, quality: str = "standard", 
                   cfg_scale: float = 8.0, seed: int = 0) -> Tuple[Optional[Image.Image], dict]:
        """Perform outpainting to extend image boundaries"""
        app_logger.info("Starting outpainting operation")
        
        try:
            if not mask_image or 'background' not in mask_image:
                return None, gr.update(visible=True, value="Please provide a base image")
            
            # Process background image
            image_encoded = process_and_encode_image(mask_image['background'])
            if len(image_encoded) < 200:
                return None, gr.update(visible=True, value=image_encoded)
            
            mask_image_encoded = None
            
            # Handle outpainting mask
            if mask_prompt and mask_prompt.strip():
                app_logger.debug("Using mask prompt for outpainting")
            elif mask_image and isinstance(mask_image, dict) and 'composite' in mask_image:
                app_logger.debug("Processing composite mask for outpainting")
                # For outpainting, create mask from original area
                mask = process_composite_to_mask(mask_image['background'], None)
                image_with_alpha = process_composite_to_mask(mask_image['background'], None, True)
                
                image_encoded = process_and_encode_image(image_with_alpha)
                mask_image_encoded = process_and_encode_image(mask)
                
                if not mask_image_encoded or len(mask_image_encoded) < 200:
                    return None, gr.update(visible=True, value="Error processing mask image")
            else:
                return None, gr.update(visible=True, value="Please provide either a mask prompt or draw a mask on the image")
            
            # Build parameters
            out_painting_params = {
                "image": image_encoded,
                "outPaintingMode": outpainting_mode,
                **({"maskImage": mask_image_encoded} if mask_image_encoded else {}),
                **({"maskPrompt": mask_prompt.strip()} if mask_prompt and mask_prompt.strip() else {}),
                **({"text": text.strip()} if text and text.strip() else {"text": " "}),
                **({"negativeText": negative_text.strip()} if negative_text and negative_text.strip() else {})
            }
            
            body = CanvasHandlers._build_request("OUTPAINTING", out_painting_params,
                                               height, width, quality, cfg_scale, seed)
            
            rate_limiter.check_rate_limit(body)
            result = bedrock_service.generate_image(body)
            return CanvasHandlers._process_response(result)
            
        except (NSFWError, RateLimitError) as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Outpainting error: {str(e)}")
            return None, gr.update(visible=True, value="Outpainting failed. Please try again.")
    
    @staticmethod
    @log_performance
    def update_mask_editor(img: dict) -> Optional[Image.Image]:
        """Create padded image for mask editor"""
        try:
            if not img or 'background' not in img or img['background'] is None:
                return None
            return create_padded_image(img)
        except Exception as e:
            app_logger.error(f"Error creating padded image: {str(e)}")
            return None
    
    @staticmethod
    @log_performance
    @handle_gracefully(default_return=(None, gr.update(visible=True, value="Service temporarily unavailable")))
    def image_variation(images: List[str], text: Optional[str] = None, negative_text: Optional[str] = None,
                       similarity_strength: float = 0.5, height: int = 1024, width: int = 1024,
                       quality: str = "standard", cfg_scale: float = 8.0, seed: int = 0) -> Tuple[Optional[Image.Image], dict]:
        """Generate image variations"""
        app_logger.info("Starting image variation generation")
        
        try:
            if not images:
                return None, gr.update(visible=True, value="Please provide at least one input image")
            
            # Process input images
            encoded_images = []
            for image_path in images:
                encoded_image = process_and_encode_image(image_path)
                if len(encoded_image) < 200:
                    return None, gr.update(visible=True, value=f"Error processing image: {encoded_image}")
                encoded_images.append(encoded_image)
            
            image_variation_params = {
                "images": encoded_images,
                **({"similarityStrength": similarity_strength} if similarity_strength is not None else {}),
                **({"text": text.strip()} if text and text.strip() else {}),
                **({"negativeText": negative_text.strip()} if negative_text and negative_text.strip() else {})
            }
            
            body = CanvasHandlers._build_request("IMAGE_VARIATION", image_variation_params,
                                               height, width, quality, cfg_scale, seed)
            
            rate_limiter.check_rate_limit(body)
            result = bedrock_service.generate_image(body)
            return CanvasHandlers._process_response(result)
            
        except (NSFWError, RateLimitError) as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Image variation error: {str(e)}")
            return None, gr.update(visible=True, value="Image variation failed. Please try again.")
    
    @staticmethod
    @log_performance
    @handle_gracefully(default_return=(None, gr.update(visible=True, value="Service temporarily unavailable")))
    def image_conditioning(condition_image: Image.Image, text: str, negative_text: Optional[str] = None,
                          control_mode: str = "CANNY_EDGE", control_strength: float = 0.7,
                          height: int = 1024, width: int = 1024, quality: str = "standard", 
                          cfg_scale: float = 8.0, seed: int = 0) -> Tuple[Optional[Image.Image], dict]:
        """Generate image with conditioning"""
        app_logger.info("Starting image conditioning generation")
        
        try:
            if not condition_image:
                return None, gr.update(visible=True, value="Please provide a condition image")
            
            if not text or not text.strip():
                return None, gr.update(visible=True, value="Please provide a text prompt")
            
            condition_image_encoded = process_and_encode_image(condition_image)
            if len(condition_image_encoded) < 200:
                return None, gr.update(visible=True, value=condition_image_encoded)
            
            text_to_image_params = {
                "text": text.strip(),
                "controlMode": control_mode,
                "controlStrength": control_strength,
                "conditionImage": condition_image_encoded,
                **({"negativeText": negative_text.strip()} if negative_text and negative_text.strip() else {})
            }
            
            body = CanvasHandlers._build_request("TEXT_IMAGE", text_to_image_params,
                                               height, width, quality, cfg_scale, seed)
            
            rate_limiter.check_rate_limit(body)
            result = bedrock_service.generate_image(body)
            return CanvasHandlers._process_response(result)
            
        except (NSFWError, RateLimitError) as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Image conditioning error: {str(e)}")
            return None, gr.update(visible=True, value="Image conditioning failed. Please try again.")
    
    @staticmethod
    @log_performance
    @handle_gracefully(default_return=(None, gr.update(visible=True, value="Service temporarily unavailable")))
    def color_guided_content(text: str, reference_image: Optional[Image.Image] = None,
                           negative_text: Optional[str] = None, colors: Optional[str] = None,
                           height: int = 1024, width: int = 1024, quality: str = "standard",
                           cfg_scale: float = 8.0, seed: int = 0) -> Tuple[Optional[Image.Image], dict]:
        """Generate color-guided content"""
        app_logger.info("Starting color-guided generation")
        
        try:
            if not text or not text.strip():
                return None, gr.update(visible=True, value="Please provide a text prompt")
            
            reference_image_encoded = None
            if reference_image is not None:
                reference_image_encoded = process_and_encode_image(reference_image)
                if len(reference_image_encoded) < 200:
                    return None, gr.update(visible=True, value=reference_image_encoded)
            
            # Use default colors if none provided
            if not colors or not colors.strip():
                colors = "#FF5733,#33FF57,#3357FF,#FF33A1,#33FFF5,#FF8C33,#8C33FF,#33FF8C,#FF3333,#33A1FF"
            
            color_guided_generation_params = {
                "text": text.strip(),
                "colors": [color.strip() for color in colors.split(',') if color.strip()],
                **({"referenceImage": reference_image_encoded} if reference_image_encoded else {}),
                **({"negativeText": negative_text.strip()} if negative_text and negative_text.strip() else {})
            }
            
            body = CanvasHandlers._build_request("COLOR_GUIDED_GENERATION", color_guided_generation_params,
                                               height, width, quality, cfg_scale, seed)
            
            rate_limiter.check_rate_limit(body)
            result = bedrock_service.generate_image(body)
            return CanvasHandlers._process_response(result)
            
        except (NSFWError, RateLimitError) as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Color-guided generation error: {str(e)}")
            return None, gr.update(visible=True, value="Color-guided generation failed. Please try again.")
    
    @staticmethod
    @log_performance
    @handle_gracefully(default_return=(None, gr.update(visible=True, value="Service temporarily unavailable")))
    def background_removal(image: Image.Image) -> Tuple[Optional[Image.Image], dict]:
        """Remove background from image"""
        app_logger.info("Starting background removal")
        
        try:
            if not image:
                return None, gr.update(visible=True, value="Please provide an input image")
            
            input_image_encoded = process_and_encode_image(image)
            if len(input_image_encoded) < 200:
                return None, gr.update(visible=True, value=input_image_encoded)
            
            body = json.dumps({
                "taskType": "BACKGROUND_REMOVAL",
                "backgroundRemovalParams": {
                    "image": input_image_encoded
                }
            })
            
            result = bedrock_service.generate_image(body)
            return CanvasHandlers._process_response(result)
            
        except (NSFWError, RateLimitError) as e:
            return None, gr.update(visible=True, value=e.message)
        except Exception as e:
            app_logger.error(f"Background removal error: {str(e)}")
            return None, gr.update(visible=True, value="Background removal failed. Please try again.")
    
    @staticmethod
    @log_performance
    @handle_gracefully(default_return="Error generating prompt")
    def generate_nova_prompt() -> str:
        """Generate creative prompt using Nova Lite"""
        app_logger.info("Starting prompt generation")
        
        try:
            # Load seeds
            import random
            with open('seeds.json', 'r') as file:
                data = json.load(file)
            
            if 'seeds' not in data or not isinstance(data['seeds'], list):
                raise ValueError("Invalid seeds file format")
            
            random_concept = random.choice(data['seeds'])
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
            result = bedrock_service.generate_prompt(messages)
            
            app_logger.info("Prompt generation completed")
            return result
            
        except Exception as e:
            app_logger.error(f"Prompt generation error: {str(e)}")
            return f"Error generating prompt: {str(e)}"

# Create global handlers instance
canvas_handlers = CanvasHandlers()