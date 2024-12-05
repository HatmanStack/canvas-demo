import base64
import io
import json
import logging
import boto3
from PIL import Image
import gradio as gr

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Custom exception for image errors
class ImageError(Exception):
    def __init__(self, message):
        self.message = message

model_id = 'amazon.nova-canvas-v1:0'
# Function to generate an image using Amazon Nova Canvas model
def generate_image(body):
    logger.info("Generating image with Amazon Nova Canvas model %s", model_id)
    session = boto3.Session(aws_access_key_id=aws_id, aws_secret_access_key=aws_secret, region_name='us-east-1')
    bedrock = session.client('bedrock-runtime')
    accept = "application/json"
    content_type = "application/json"

    response = bedrock.invoke_model(body=body, modelId=model_id, accept=accept, contentType=content_type)
    response_body = json.loads(response.get("body").read())

    base64_image = response_body.get("images")[0]
    base64_bytes = base64_image.encode('ascii')
    image_bytes = base64.b64decode(base64_bytes)

    finish_reason = response_body.get("error")
    if finish_reason is not None:
        raise ImageError(f"Image generation error. Error is {finish_reason}")

    logger.info("Successfully generated image with Amazon Nova Canvas model %s", model_id)
    return image_bytes

# Function to display image from bytes
def display_image(image_bytes):
    image = Image.open(io.BytesIO(image_bytes))
    return image

# Gradio functions for each task
def text_to_image(prompt):
    body = json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {"text": prompt},
        "imageGenerationConfig": {"numberOfImages": 1, "height": 1024, "width": 1024, "cfgScale": 8.0, "seed": 0}
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

def inpainting(image, mask_prompt):
    input_image = base64.b64encode(image.read()).decode('utf8')
    body = json.dumps({
        "taskType": "INPAINTING",
        "inPaintingParams": {"text": mask_prompt, "image": input_image, "maskPrompt": "windows"},
        "imageGenerationConfig": {"numberOfImages": 1, "height": 512, "width": 512, "cfgScale": 8.0}
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

def outpainting(image, mask_image, text):
    input_image = base64.b64encode(image.read()).decode('utf8')
    input_mask_image = base64.b64encode(mask_image.read()).decode('utf8')
    body = json.dumps({
        "taskType": "OUTPAINTING",
        "outPaintingParams": {"text": text, "image": input_image, "maskImage": input_mask_image, "outPaintingMode": "DEFAULT"},
        "imageGenerationConfig": {"numberOfImages": 1, "height": 512, "width": 512, "cfgScale": 8.0}
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

def image_variation(image, text):
    input_image = base64.b64encode(image.read()).decode('utf8')
    body = json.dumps({
        "taskType": "IMAGE_VARIATION",
        "imageVariationParams": {"text": text, "images": [input_image], "similarityStrength": 0.7},
        "imageGenerationConfig": {"numberOfImages": 1, "height": 512, "width": 512, "cfgScale": 8.0}
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

def image_conditioning(image, text):
    input_image = base64.b64encode(image.read()).decode('utf8')
    body = json.dumps({
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {"text": text, "conditionImage": input_image, "controlMode": "CANNY_EDGE"},
        "imageGenerationConfig": {"numberOfImages": 1, "height": 512, "width": 512, "cfgScale": 8.0}
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

def color_guided_content(image, text, colors):
    input_image = base64.b64encode(image.read()).decode('utf8')
    body = json.dumps({
        "taskType": "COLOR_GUIDED_GENERATION",
        "colorGuidedGenerationParams": {"text": text, "referenceImage": input_image, "colors": colors},
        "imageGenerationConfig": {"numberOfImages": 1, "height": 512, "width": 512, "cfgScale": 8.0}
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

def background_removal(image):
    input_image = base64.b64encode(image.read()).decode('utf8')
    body = json.dumps({
        "taskType": "BACKGROUND_REMOVAL",
        "backgroundRemovalParams": {"image": input_image}
    })
    image_bytes = generate_image(body)
    return display_image(image_bytes)

# Gradio Interface
with gr.Blocks() as demo:
    gr.Markdown("# Amazon Nova Canvas Image Generation")

    with gr.Tab("Text to Image"):
        with gr.Column():
            gr.Markdown("Generate an image from a text prompt using the Amazon Nova Canvas model.")
            prompt = gr.Textbox(label="Prompt")
            output = gr.Image()
            gr.Button("Generate").click(text_to_image, inputs=prompt, outputs=output)

    with gr.Tab("Inpainting"):
        with gr.Column():
            gr.Markdown("Use inpainting to modify specific areas of an image based on a text prompt.")
            image = gr.Image(type='pil', label="Input Image")
            mask_prompt = gr.Textbox(label="Mask Prompt")
            output = gr.Image()
            gr.Button("Generate").click(inpainting, inputs=[image, mask_prompt], outputs=output)

    with gr.Tab("Outpainting"):
        with gr.Column():
            gr.Markdown("Extend an image beyond its original borders using a mask and text prompt.")
            image = gr.Image(type='pil', label="Input Image")
            mask_image = gr.Image(type='pil', label="Mask Image")
            text = gr.Textbox(label="Text")
            output = gr.Image()
            gr.Button("Generate").click(outpainting, inputs=[image, mask_image, text], outputs=output)

    with gr.Tab("Image Variation"):
        with gr.Column():
            gr.Markdown("Create variations of an image based on a text description.")
            image = gr.Image(type='pil', label="Input Image")
            text = gr.Textbox(label="Text")
            output = gr.Image()
            gr.Button("Generate").click(image_variation, inputs=[image, text], outputs=output)

    with gr.Tab("Image Conditioning"):
        with gr.Column():
            gr.Markdown("Generate an image conditioned on an input image and a text prompt.")
            image = gr.Image(type='pil', label="Input Image")
            text = gr.Textbox(label="Text")
            output = gr.Image()
            gr.Button("Generate").click(image_conditioning, inputs=[image, text], outputs=output)

    with gr.Tab("Color Guided Content"):
        with gr.Column():
            gr.Markdown("Generate an image using a color palette from a reference image and a text prompt.")
            image = gr.Image(type='pil', label="Input Image")
            text = gr.Textbox(label="Text")
            colors = gr.Textbox(label="Colors (comma-separated hex values)")
            output = gr.Image()
            gr.Button("Generate").click(color_guided_content, inputs=[image, text, colors], outputs=output)

    with gr.Tab("Background Removal"):
        with gr.Column():
            gr.Markdown("Remove the background from an image.")
            image = gr.Image(type='pil', label="Input Image")
            output = gr.Image()
            gr.Button("Generate").click(background_removal, inputs=image, outputs=output)

if __name__ == "__main__":
    demo.launch()