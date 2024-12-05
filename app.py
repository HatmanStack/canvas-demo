import base64
import io
import json
import logging
import boto3
from PIL import Image
from botocore.config import Config
from botocore.exceptions import ClientError
import gradio as gr
import os

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Custom exception for image errors
class ImageError(Exception):
    def __init__(self, message):
        self.message = message

model_id = 'amazon.nova-canvas-v1:0'
aws_id = os.getenv('AWS_ID')
aws_secret = os.getenv('AWS_SECRET')

def process_and_encode_image(image, min_size=320, max_size=4096, max_pixels=4194304):
    if image is None:
        raise ValueError("Input image is required.")
    if not isinstance(image, Image.Image):
        image = Image.open(image)

    # Convert to RGB mode if necessary
    if image.mode not in ('RGB', 'RGBA'):
        image = image.convert('RGB')
    elif image.mode == 'RGBA':
        # Convert RGBA to RGB by compositing on white background
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])  # Use alpha channel as mask
        image = background

    # Ensure 8-bit color depth
    if image.mode == 'RGB' and isinstance(image.getpixel((0,0)), tuple) and len(image.getpixel((0,0))) == 3:
        if not all(0 <= x <= 255 for x in image.getpixel((0,0))):
            image = image.convert('RGB')

    current_pixels = image.width * image.height
    # If image exceeds max pixels, scale it down while maintaining aspect ratio
    if current_pixels > max_pixels:
        aspect_ratio = image.width / image.height
        if aspect_ratio > 1:  # Width > Height
            new_width = int((max_pixels * aspect_ratio) ** 0.5)
            new_height = int(new_width / aspect_ratio)
        else:  # Height >= Width
            new_height = int((max_pixels / aspect_ratio) ** 0.5)
            new_width = int(new_height * aspect_ratio)
        
        image = image.resize((new_width, new_height), Image.LANCZOS)

    # Ensure dimensions are within valid range
    if image.width < min_size or image.width > max_size or image.height < min_size or image.height > max_size:
        new_width = min(max(image.width, min_size), max_size)
        new_height = min(max(image.height, min_size), max_size)
        image = image.resize((new_width, new_height), Image.LANCZOS)

    # Convert to bytes and encode to base64
    image_bytes = io.BytesIO()
    # Save as PNG with maximum compatibility
    image.save(image_bytes, format='PNG', optimize=True)
    encoded_image = base64.b64encode(image_bytes.getvalue()).decode('utf8')
    
    return encoded_image

# Function to generate an image using Amazon Nova Canvas model
def generate_image(body):
    logger.info("Generating image with Amazon Nova Canvas model %s", model_id)

    # Configure the client with a longer timeout
    bedrock = boto3.client(
        service_name='bedrock-runtime',
        aws_access_key_id=aws_id,
        aws_secret_access_key=aws_secret,
        region_name='us-east-1',
        config=Config(read_timeout=300)  # Add 5-minute timeout
    )

    print(body)

    try:
        response = bedrock.invoke_model(
            body=body,
            modelId=model_id,
            accept="application/json",
            contentType="application/json"
        )
        
        response_body = json.loads(response.get("body").read())

        # Check for error before processing the image
        if "error" in response_body:
            raise ImageError(f"Image generation error. Error is {response_body['error']}")

        base64_image = response_body.get("images")[0]
        base64_bytes = base64_image.encode('ascii')
        image_bytes = base64.b64decode(base64_bytes)

        logger.info("Successfully generated image with Amazon Nova Canvas model %s", model_id)
        return image_bytes

    except ClientError as err:
        message = err.response["Error"]["Message"]
        logger.error("A client error occurred: %s", message)
        raise ImageError(f"Client error during image generation: {message}")

# Function to display image from bytes
def display_image(image_bytes):
    image = Image.open(io.BytesIO(image_bytes))
    return image

# Gradio functions for each task
def text_to_image(prompt, negative_text=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    # Prepare the textToImageParams dictionary
    text_to_image_params = {
        "text": prompt
    }

    # Conditionally add negativeText if it is not None and not empty
    if negative_text:
        text_to_image_params["negativeText"] = negative_text

    body = json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": text_to_image_params,
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": height,
            "width": width,
            "quality": quality,
            "cfgScale": cfg_scale,
            "seed": seed
        }
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

def inpainting(image, mask_prompt=None, mask_image=None, text=None, negative_text=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    if image is not None:
        input_image = process_and_encode_image(image)
    else:
        raise ValueError("Input image is required.")

    if mask_image is not None:
        mask_image_encoded = process_and_encode_image(image)
    else:
        mask_image_encoded = None

    if not mask_prompt and not mask_image:
        raise ValueError("You must specify either maskPrompt or maskImage.")

    # Prepare the inPaintingParams dictionary
    if mask_prompt and mask_image_encoded:
        raise ValueError("You must specify either maskPrompt or maskImage, but not both.")
    if not mask_prompt and not mask_image_encoded:
        raise ValueError("You must specify either maskPrompt or maskImage.")

    # Prepare the inPaintingParams dictionary with the appropriate mask parameter
    in_painting_params = {
        "image": input_image
    }

    if mask_prompt:
        in_painting_params["maskPrompt"] = mask_prompt
    elif mask_image_encoded:
        in_painting_params["maskImage"] = mask_image_encoded
    if text:
        in_painting_params["text"] = text
    if negative_text:
        in_painting_params["negativeText"] = negative_text

    body = json.dumps({
        "taskType": "INPAINTING",
        "inPaintingParams": in_painting_params,
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": height,
            "width": width,
            "quality": quality,
            "cfgScale": cfg_scale,
            "seed": seed
        }
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

def outpainting(image, mask_prompt=None, mask_image=None, text=None, negative_text=None, outpainting_mode="DEFAULT", height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    if image is not None:
        input_image = process_and_encode_image(image)
    else:
        raise ValueError("Input image is required.")

    if mask_image is not None:
        mask_bytes = io.BytesIO()
        mask_image.save(mask_bytes, format='PNG')
        mask_image_encoded = base64.b64encode(mask_bytes.getvalue()).decode('utf8')
    else:
        mask_image_encoded = None

    if not mask_prompt and not mask_image:
        raise ValueError("You must specify either maskPrompt or maskImage.")

    # Prepare the outPaintingParams dictionary
    out_painting_params = {
        "image": input_image,
        "outPaintingMode": outpainting_mode,
        "maskPrompt": mask_prompt or ""  # Ensure maskPrompt is always included
    }

    # Conditionally add parameters if they are not None
    if mask_image_encoded:
        out_painting_params["maskImage"] = mask_image_encoded
    if text:
        out_painting_params["text"] = text
    if negative_text:
        out_painting_params["negativeText"] = negative_text

    body = json.dumps({
        "taskType": "OUTPAINTING",
        "outPaintingParams": out_painting_params,
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": height,
            "width": width,
            "quality": quality,
            "cfgScale": cfg_scale,
            "seed": seed
        }
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

def image_variation(images, text=None, negative_text=None, similarity_strength=0.5, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    encoded_images = []
    for image_path in images:
        with open(image_path, "rb") as image_file:
            encoded_images.append(process_and_encode_image(image_file))

    # Prepare the imageVariationParams dictionary
    image_variation_params = {
        "images": encoded_images,
        "similarityStrength": similarity_strength
    }

    # Conditionally add parameters if they are not None
    if text:
        image_variation_params["text"] = text
    if negative_text:
        image_variation_params["negativeText"] = negative_text

    body = json.dumps({
        "taskType": "IMAGE_VARIATION",
        "imageVariationParams": image_variation_params,
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": height,
            "width": width,
            "quality": quality,
            "cfgScale": cfg_scale,
            "seed": seed
        }
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

def image_conditioning(condition_image, text, negative_text=None, control_mode="CANNY_EDGE", control_strength=0.7, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    if condition_image is not None:
        condition_image_encoded = process_and_encode_image(condition_image)
    else:
        raise ValueError("Input image is required.")

    # Prepare the textToImageParams dictionary
    text_to_image_params = {
        "text": text,
        "conditionImage": condition_image_encoded,
        "controlMode": control_mode,
        "controlStrength": control_strength
    }

    # Conditionally add negativeText if it is not None
    if negative_text:
        text_to_image_params["negativeText"] = negative_text

    body = json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": text_to_image_params,
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": height,
            "width": width,
            "quality": quality,
            "cfgScale": cfg_scale,
            "seed": seed
        }
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

def color_guided_content(text=None, reference_image=None, negative_text=None, colors=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    # Encode the reference image if provided
    if reference_image is not None:
        reference_image_encoded = process_and_encode_image(reference_image)
    else:
        reference_image_encoded = None
    if not colors:
        colors = "#FF5733,#33FF57,#3357FF,#FF33A1,#33FFF5,#FF8C33,#8C33FF,#33FF8C,#FF3333,#33A1FF"
    # Prepare the colorGuidedGenerationParams dictionary
    color_guided_generation_params = {
        "text": text,
        "colors": colors.split(',')
    }

    # Conditionally add parameters if they are not None
    if negative_text:
        color_guided_generation_params["negativeText"] = negative_text
    if reference_image_encoded:
        color_guided_generation_params["referenceImage"] = reference_image_encoded

    body = json.dumps({
        "taskType": "COLOR_GUIDED_GENERATION",
        "colorGuidedGenerationParams": color_guided_generation_params,
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": height,
            "width": width,
            "quality": quality,
            "cfgScale": cfg_scale,
            "seed": seed
        }
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

def background_removal(image):
    input_image = process_and_encode_image(image)
    body = json.dumps({
        "taskType": "BACKGROUND_REMOVAL",
        "backgroundRemovalParams": {"image": input_image}
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

# Gradio Interface
with gr.Blocks() as demo:
    gr.HTML("""
    <style>
        #component-0 {
            max-width: 800px;
            margin: 0 auto; 
        }
    </style>
    """)
    gr.Markdown("# Amazon Nova Canvas Image Generation")

    with gr.Tab("Text to Image"):
        with gr.Column():
            gr.Markdown("Generate an image from a text prompt using the Amazon Nova Canvas model.")
            prompt = gr.Textbox(label="Prompt", placeholder="Enter a text prompt (1-1024 characters)", max_lines=1)
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                negative_text = gr.Textbox(label="Negative Prompt", placeholder="Enter text to exclude (1-1024 characters)", max_lines=1)
                height = gr.Slider(minimum=256, maximum=2048, step=64, value=1024, label="Height")
                width = gr.Slider(minimum=256, maximum=2048, step=64, value=1024, label="Width")
                quality = gr.Radio(choices=["standard", "premium"], value="standard", label="Quality")
                cfg_scale = gr.Slider(minimum=1.0, maximum=20.0, step=0.1, value=8.0, label="CFG Scale")
                seed = gr.Slider(minimum=1, maximum=2000, step=1, value=8, label="Seed")
            
            gr.Button("Generate").click(text_to_image, inputs=[prompt, negative_text, height, width, quality, cfg_scale, seed], outputs=output)

    with gr.Tab("Inpainting"):
        with gr.Column():
            gr.Markdown("""
            <div style="text-align: center;">
                Modify specific areas of your image using inpainting. Upload your image and choose one of two ways to specify the areas you want to edit: 
                You can use a photo editing tool to draw masks (using pure black for areas to edit and pure white for areas to preserve) or use the Mask Prompt field to allow the model to infer the mask.
            </div>
            """)
            image = gr.Image(type='pil', label="Input Image")
            mask_prompt = gr.Textbox(label="Mask Prompt", placeholder="Describe regions to edit", max_lines=1)
            with gr.Accordion("Mask Image", open=False):
                text = gr.Textbox(label="Text", placeholder="Describe what to generate (1-1024 characters)", max_lines=1)
                mask_image = gr.Image(type='pil', label="Mask Image")
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                negative_text = gr.Textbox(label="Negative Prompt", placeholder="Describe what not to include (1-1024 characters)", max_lines=1)
                width = gr.Slider(minimum=256, maximum=2048, step=64, value=1024, label="Width")
                height = gr.Slider(minimum=256, maximum=2048, step=64, value=1024, label="Height")
                quality = gr.Radio(choices=["standard", "premium"], value="standard", label="Quality")
                cfg_scale = gr.Slider(minimum=1.0, maximum=20.0, step=0.1, value=8.0, label="CFG Scale")
                seed = gr.Slider(minimum=1, maximum=2000, step=1, value=8, label="Seed")
            
            gr.Button("Generate").click(inpainting, inputs=[image, mask_prompt, mask_image, text, negative_text, height, width, quality, cfg_scale, seed], outputs=output)

    with gr.Tab("Outpainting"):
        with gr.Column():
            gr.Markdown("Extend an image beyond its original borders using a mask and text prompt.")
            gr.Markdown("""
            <div style="text-align: center;">
                Modify areas outside of your image using outpainting. Upload your image and choose one of two ways to specify the areas you want to edit: 
                You can use a photo editing tool to draw masks extended outside of an images original borders (using pure black for areas to edit and pure 
                white for areas to preserve) or use the Mask Prompt field to allow the model to infer the mask.
            </div>
            """)
            image = gr.Image(type='pil', label="Input Image")
            mask_prompt = gr.Textbox(label="Mask Prompt", placeholder="Describe regions to edit", max_lines=1)
            with gr.Accordion("Mask Image", open=False):
                text = gr.Textbox(label="Text", placeholder="Describe what to generate (1-1024 characters)", max_lines=1)
                mask_image = gr.Image(type='pil', label="Mask Image")
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                negative_text = gr.Textbox(label="Negative Prompt", placeholder="Describe what not to include (1-1024 characters)", max_lines=1)
                outpainting_mode = gr.Radio(choices=["DEFAULT", "PRECISE"], value="DEFAULT", label="Outpainting Mode")
                width = gr.Slider(minimum=256, maximum=2048, step=64, value=1024, label="Width")
                height = gr.Slider(minimum=256, maximum=2048, step=64, value=1024, label="Height")
                quality = gr.Radio(choices=["standard", "premium"], value="standard", label="Quality")
                cfg_scale = gr.Slider(minimum=1.0, maximum=20.0, step=0.1, value=8.0, label="CFG Scale")
                seed = gr.Slider(minimum=1, maximum=2000, step=1, value=8, label="Seed")
            
            gr.Button("Generate").click(outpainting, inputs=[image, mask_prompt, mask_image, text, negative_text, outpainting_mode, height, width, quality, cfg_scale, seed], outputs=output)

    with gr.Tab("Image Variation"):
        with gr.Column():
            gr.Markdown("""
            <div style="text-align: center;">
                Create a variation image based on up to 5 other images and a text description (optional).
                </div>
            """)
            images = gr.File(type='filepath', label="Input Images", file_count="multiple", file_types=["image"])
            text = gr.Textbox(label="Text", placeholder="Enter a text prompt (1-1024 characters)", max_lines=1)
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                negative_text = gr.Textbox(label="Negative Prompt", placeholder="Enter text to exclude (1-1024 characters)", max_lines=1)
                similarity_strength = gr.Slider(minimum=0.2, maximum=1.0, step=0.1, value=0.7, label="Similarity Strength")
                width = gr.Slider(minimum=256, maximum=2048, step=64, value=1024, label="Width")
                height = gr.Slider(minimum=256, maximum=2048, step=64, value=1024, label="Height")
                quality = gr.Radio(choices=["standard", "premium"], value="standard", label="Quality")
                cfg_scale = gr.Slider(minimum=1.0, maximum=20.0, step=0.1, value=8.0, label="CFG Scale")
                seed = gr.Slider(minimum=1, maximum=2000, step=1, value=8, label="Seed")
            
            gr.Button("Generate").click(image_variation, inputs=[images, text, negative_text, similarity_strength, height, width, quality, cfg_scale, seed], outputs=output)

    with gr.Tab("Image Conditioning"):
        with gr.Column():
            gr.Markdown("""
            <div style="text-align: center;">
                Generate an image conditioned on an input image and a text prompt (required).
                </div>
            """)
            condition_image = gr.Image(type='pil', label="Condition Image")
            text = gr.Textbox(label="Text", placeholder="Enter a text prompt (1-1024 characters)", max_lines=1)
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                negative_text = gr.Textbox(label="Negative Prompt", placeholder="Describe what not to include (1-1024 characters)", max_lines=1)
                control_mode = gr.Radio(choices=["CANNY_EDGE", "SEGMENTATION"], value="CANNY_EDGE", label="Control Mode")
                control_strength = gr.Slider(minimum=0.0, maximum=1.0, step=0.1, value=0.7, label="Control Strength")
                width = gr.Slider(minimum=256, maximum=2048, step=64, value=1024, label="Width")
                height = gr.Slider(minimum=256, maximum=2048, step=64, value=1024, label="Height")
                quality = gr.Radio(choices=["standard", "premium"], value="standard", label="Quality")
                cfg_scale = gr.Slider(minimum=1.0, maximum=20.0, step=0.1, value=8.0, label="CFG Scale")
                seed = gr.Slider(minimum=1, maximum=2000, step=1, value=8, label="Seed")
            
            gr.Button("Generate").click(image_conditioning, inputs=[condition_image, text, negative_text, control_mode, control_strength, height, width, quality, cfg_scale, seed], outputs=output)

    with gr.Tab("Color Guided Content"):
        with gr.Column():
            gr.Markdown("""
            <div style="text-align: center;">
                Generate an image using a color palette from a reference image or a text prompt. Starter colors are provided.
                </div>
            """)
            reference_image = gr.Image(type='pil', label="Reference Image")     
            colors = gr.Textbox(label="Colors", placeholder="Enter up to 10 colors as hex values, e.g., #00FF00,#FCF2AB", max_lines=1)
            text = gr.Textbox(label="Text", placeholder="Enter a text prompt (1-1024 characters)", max_lines=1)
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                negative_text = gr.Textbox(label="Negative Prompt", placeholder="Enter text to exclude (1-1024 characters)", max_lines=1)
                width = gr.Slider(minimum=256, maximum=2048, step=64, value=1024, label="Width")
                height = gr.Slider(minimum=256, maximum=2048, step=64, value=1024, label="Height")
                quality = gr.Radio(choices=["standard", "premium"], value="standard", label="Quality")
                cfg_scale = gr.Slider(minimum=1.0, maximum=20.0, step=0.1, value=8.0, label="CFG Scale")
                seed = gr.Slider(minimum=1, maximum=2000, step=1, value=8, label="Seed")
            
            gr.Button("Generate").click(color_guided_content, inputs=[text, reference_image, negative_text, colors, height, width, quality, cfg_scale, seed], outputs=output)

    with gr.Tab("Background Removal"):
        with gr.Column():
            gr.Markdown("""
            <div style="text-align: center;">
                Remove the background from an image.
                </div>
            """)
            image = gr.Image(type='pil', label="Input Image")
            output = gr.Image()
            gr.Button("Generate").click(background_removal, inputs=image, outputs=output)

if __name__ == "__main__":
    demo.launch()