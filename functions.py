import json
import io
import random
import gradio as gr
from PIL import Image
from generate import *
import numpy as np
from typing import Dict, Any
from processImage import process_and_encode_image
from datetime import datetime # Import datetime

def rgba_to_hex(rgba):
    print(f"[{datetime.now()}] Running rgba_to_hex...")
    r, g, b, _ = [int(float(x)) for x in rgba[5:-1].split(',')]
    return f"#{r:02X}{g:02X}{b:02X}"

def add_color_to_list(current_colors, new_color):
    print(f"[{datetime.now()}] Running add_color_to_list...")
    new_color_hex = rgba_to_hex(new_color)
    color_list = current_colors.split(',')
    if new_color_hex not in color_list and len(color_list) < 10:
        color_list.append(new_color_hex)
    return ','.join(filter(None, color_list))

def create_padded_image(image, padding_percent=100):
    print(f"[{datetime.now()}] Running create_padded_image...")
    image = image['background']
    if image.mode != 'RGBA':
        image = image.convert('RGBA')

    width, height = image.size
    new_width = int(width * (1 + padding_percent/100))
    new_height = int(height * (1 + padding_percent/100))

    padded = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))

    x_offset = (new_width - width) // 2
    y_offset = (new_height - height) // 2

    padded.paste(image, (x_offset, y_offset))
    print(f"[{datetime.now()}] Finished create_padded_image.")
    return padded

def process_composite_to_mask(original_image, composite_image, transparent=False):
    print(f"[{datetime.now()}] Running process_composite_to_mask...")
    original_array = np.array(original_image.convert('RGBA'))
    if transparent:
        black_background = Image.new('RGBA', original_image.size, (0, 0, 0, 255))
        black_background.paste(original_image, (0, 0), original_image)
        print(f"[{datetime.now()}] Finished process_composite_to_mask (transparent mode).")
        return black_background
    if composite_image is None:
        mask = np.full(original_array.shape[:2], 0, dtype=np.uint8)
        transparent_areas = original_array[:, :, 3] == 0
        mask[transparent_areas] = 255
    else:
        composite_array = np.array(composite_image.convert('RGBA'))

        difference = np.any(original_array != composite_array, axis=2)
        mask = np.full(original_array.shape[:2], 255, dtype=np.uint8)
        mask[difference] = 0

    print(f"[{datetime.now()}] Finished process_composite_to_mask.")
    return Image.fromarray(mask, mode='L')

def build_request(task_type, params, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    print(f"[{datetime.now()}] Building request for task type: {task_type}")
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
    print(f"[{datetime.now()}] Finished building request.")
    return json.dumps(request_body)

def check_return(result):
    print(f"[{datetime.now()}] Checking return value...")
    if not isinstance(result, bytes):
        print(f"[{datetime.now()}] Result is not bytes (likely error message): {result}")
        return None, gr.update(visible=True, value=result)

    print(f"[{datetime.now()}] Result is bytes, opening image...")
    return Image.open(io.BytesIO(result)), gr.update(value=None,visible=False)


def text_to_image(prompt, negative_text=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    print(f"[{datetime.now()}] --- text_to_image START ---")
    text_to_image_params = {"text": prompt,
                            **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
                            }

    body = build_request("TEXT_IMAGE", text_to_image_params, height, width, quality, cfg_scale, seed)
    print(f"[{datetime.now()}] Calling generate_image for TEXT_IMAGE...")
    result = generate_image(body)
    print(f"[{datetime.now()}] generate_image call finished.")
    output = check_return(result)
    print(f"[{datetime.now()}] --- text_to_image END ---")
    return output


def inpainting(mask_image, mask_prompt=None, text=None, negative_text=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    print(f"[{datetime.now()}] --- inpainting START ---")
    print(f"[{datetime.now()}] Processing background image...")
    image = process_and_encode_image(mask_image['background'])
    if len(image) < 200:
        print(f"[{datetime.now()}] Error processing background image: {image}")
        print(f"[{datetime.now()}] --- inpainting END (Error) ---")
        return None, gr.update(visible=True, value=image)

    if mask_prompt and mask_image and 'composite' in mask_image: # Check if mask_image is dict
        print(f"[{datetime.now()}] Error: Both maskPrompt and maskImage provided.")
        print(f"[{datetime.now()}] --- inpainting END (Error) ---")
        raise ValueError("You must specify either maskPrompt or maskImage, but not both.")
    if not mask_prompt and (not mask_image or 'composite' not in mask_image): # Check if mask_image is dict and has composite
        print(f"[{datetime.now()}] Error: Neither maskPrompt nor maskImage provided.")
        print(f"[{datetime.now()}] --- inpainting END (Error) ---")
        raise ValueError("You must specify either maskPrompt or maskImage.")

    mask_image_encoded = None
    if mask_image and 'composite' in mask_image:
        print(f"[{datetime.now()}] Processing composite mask...")
        mask = process_composite_to_mask(mask_image['background'], mask_image['composite'])
        mask_image_encoded = process_and_encode_image(mask)
        print(f"[{datetime.now()}] Finished processing composite mask.")

    in_painting_params = {
        "image": image,
        **({"maskImage": mask_image_encoded} if mask_image_encoded not in [None, ""] else {}),
        **({"maskPrompt": mask_prompt} if mask_prompt not in [None, ""] else {}),
        **({"text": text} if text not in [None, ""] else {}),
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }

    body = build_request("INPAINTING", in_painting_params, height, width, quality, cfg_scale, seed)
    print(f"[{datetime.now()}] Calling generate_image for INPAINTING...")
    result = generate_image(body)
    print(f"[{datetime.now()}] generate_image call finished.")
    output = check_return(result)
    print(f"[{datetime.now()}] --- inpainting END ---")
    return output

def outpainting(mask_image, mask_prompt=None, text=None, negative_text=None, outpainting_mode="DEFAULT", height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    print(f"[{datetime.now()}] --- outpainting START ---")
    print(f"[{datetime.now()}] Processing background image...")
    image = process_and_encode_image(mask_image['background'])
    if len(image) < 200:
        print(f"[{datetime.now()}] Error processing background image: {image}")
        print(f"[{datetime.now()}] --- outpainting END (Error) ---")
        return None, gr.update(visible=True, value=image)

    if mask_prompt and mask_image and 'composite' in mask_image: # Check if mask_image is dict
        print(f"[{datetime.now()}] Error: Both maskPrompt and maskImage provided.")
        print(f"[{datetime.now()}] --- outpainting END (Error) ---")
        raise ValueError("You must specify either maskPrompt or maskImage, but not both.")
    if not mask_prompt and (not mask_image or 'composite' not in mask_image): # Check if mask_image is dict and has composite
        print(f"[{datetime.now()}] Error: Neither maskPrompt nor maskImage provided.")
        print(f"[{datetime.now()}] --- outpainting END (Error) ---")
        raise ValueError("You must specify either maskPrompt or maskImage.")

    mask_image_encoded = None
    if mask_image and 'composite' in mask_image:
        print(f"[{datetime.now()}] Processing composite mask for outpainting...")
        # For outpainting, the mask identifies the *original* image area
        mask = process_composite_to_mask(mask_image['background'], None) # Mask is original area
        # The image needs alpha channel for transparency where padding was
        image_with_alpha = process_composite_to_mask(mask_image['background'], None, True) # Image has alpha
        image = process_and_encode_image(image_with_alpha)
        mask_image_encoded = process_and_encode_image(mask)
        print(f"[{datetime.now()}] Finished processing composite mask for outpainting.")

    out_painting_params = {
        "image": image,
        "outPaintingMode": outpainting_mode,
        **({"maskImage": mask_image_encoded} if mask_image_encoded not in [None, ""] else {}),
        **({"maskPrompt": mask_prompt} if mask_prompt not in [None, ""] else {}),
        **({"text": text} if text not in [None, ""] else {"text": " "}), # Ensure text is present
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }


    body = build_request("OUTPAINTING", out_painting_params, height, width, quality, cfg_scale, seed)
    print(f"[{datetime.now()}] Calling generate_image for OUTPAINTING...")
    result = generate_image(body)
    print(f"[{datetime.now()}] generate_image call finished.")
    output = check_return(result)
    print(f"[{datetime.now()}] --- outpainting END ---")
    return output

def image_variation(images, text=None, negative_text=None, similarity_strength=0.5, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    print(f"[{datetime.now()}] --- image_variation START ---")
    encoded_images = []
    print(f"[{datetime.now()}] Processing input images...")
    for image_path in images:
        # Assuming image_path is the path string from Gradio File component
        value = process_and_encode_image(image_path) # Pass path directly

        if len(value) < 200:
            print(f"[{datetime.now()}] Error processing image {image_path}: {value}")
            print(f"[{datetime.now()}] --- image_variation END (Error) ---")
            return None, gr.update(visible=True, value=value)
        encoded_images.append(value)
    print(f"[{datetime.now()}] Finished processing input images.")

    image_variation_params = {
        "images": encoded_images,
        **({"similarityStrength": similarity_strength} if similarity_strength not in [None, ""] else {}),
        **({"text": text} if text not in [None, ""] else {}),
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }

    body = build_request("IMAGE_VARIATION", image_variation_params, height, width, quality, cfg_scale, seed)
    print(f"[{datetime.now()}] Calling generate_image for IMAGE_VARIATION...")
    result = generate_image(body)
    print(f"[{datetime.now()}] generate_image call finished.")
    output = check_return(result)
    print(f"[{datetime.now()}] --- image_variation END ---")
    return output

def image_conditioning(condition_image, text, negative_text=None, control_mode="CANNY_EDGE", control_strength=0.7, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    print(f"[{datetime.now()}] --- image_conditioning START ---")
    print(f"[{datetime.now()}] Processing condition image...")
    condition_image_encoded = process_and_encode_image(condition_image)

    if len(condition_image_encoded) < 200:
        print(f"[{datetime.now()}] Error processing condition image: {condition_image_encoded}")
        print(f"[{datetime.now()}] --- image_conditioning END (Error) ---")
        return None, gr.update(visible=True, value=condition_image_encoded)
    print(f"[{datetime.now()}] Finished processing condition image.")

    text_to_image_params = {
        "text": text,
        "controlMode": control_mode,
        "controlStrength": control_strength,
        "conditionImage": condition_image_encoded,
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }
    # Note: Image Conditioning uses TEXT_IMAGE task type
    body = build_request("TEXT_IMAGE", text_to_image_params, height, width, quality, cfg_scale, seed)
    print(f"[{datetime.now()}] Calling generate_image for IMAGE_CONDITIONING (using TEXT_IMAGE task)...")
    result = generate_image(body)
    print(f"[{datetime.now()}] generate_image call finished.")
    output = check_return(result)
    print(f"[{datetime.now()}] --- image_conditioning END ---")
    return output

def color_guided_content(text=None, reference_image=None, negative_text=None, colors=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    print(f"[{datetime.now()}] --- color_guided_content START ---")
    reference_image_encoded = None # Initialize to None

    if reference_image is not None: # Check if it's actually provided
        print(f"[{datetime.now()}] Processing reference image...")
        reference_image_encoded = process_and_encode_image(reference_image)

        if len(reference_image_encoded) < 200:
            print(f"[{datetime.now()}] Error processing reference image: {reference_image_encoded}")
            print(f"[{datetime.now()}] --- color_guided_content END (Error) ---")
            return None, gr.update(visible=True, value=reference_image_encoded)
        print(f"[{datetime.now()}] Finished processing reference image.")

    if not colors:
        print(f"[{datetime.now()}] No colors provided, using default.")
        colors = "#FF5733,#33FF57,#3357FF,#FF33A1,#33FFF5,#FF8C33,#8C33FF,#33FF8C,#FF3333,#33A1FF"

    color_guided_generation_params = {
        "text": text,
        "colors": [color.strip() for color in colors.split(',')],
         # Use the encoded string if it exists
        **({"referenceImage": reference_image_encoded} if reference_image_encoded is not None else {}),
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }

    body = build_request("COLOR_GUIDED_GENERATION", color_guided_generation_params, height, width, quality, cfg_scale, seed)
    print(f"[{datetime.now()}] Calling generate_image for COLOR_GUIDED_GENERATION...")
    result = generate_image(body)
    print(f"[{datetime.now()}] generate_image call finished.")
    output = check_return(result)
    print(f"[{datetime.now()}] --- color_guided_content END ---")
    return output

def background_removal(image):
    print(f"[{datetime.now()}] --- background_removal START ---")
    print(f"[{datetime.now()}] Processing input image...")
    input_image = process_and_encode_image(image)

    if len(input_image) < 200:
        print(f"[{datetime.now()}] Error processing input image: {input_image}")
        print(f"[{datetime.now()}] --- background_removal END (Error) ---")
        return None, gr.update(visible=True, value=input_image)
    print(f"[{datetime.now()}] Finished processing input image.")

    body = json.dumps({
        "taskType": "BACKGROUND_REMOVAL",
        "backgroundRemovalParams": {
            "image": input_image
        }
    })
    print(f"[{datetime.now()}] Calling generate_image for BACKGROUND_REMOVAL...")
    result = generate_image(body)
    print(f"[{datetime.now()}] generate_image call finished.")
    output = check_return(result)
    print(f"[{datetime.now()}] --- background_removal END ---")
    return output

def generate_nova_prompt():
    print(f"[{datetime.now()}] --- generate_nova_prompt START ---")
    try:
        print(f"[{datetime.now()}] Reading seeds file...")
        with open('seeds.json', 'r') as file:
            data = json.load(file)
        if 'seeds' not in data or not isinstance(data['seeds'], list):
            print(f"[{datetime.now()}] Invalid seeds file format.")
            raise ValueError("The JSON file must contain a 'seeds' key with a list of strings.")
        print(f"[{datetime.now()}] Seeds file read successfully.")

        random_string = random.choice(data['seeds'])
        print(f"[{datetime.now()}] Selected random seed concept: {random_string}")
        prompt = f"""
            Generate a creative image prompt that builds upon this concept: "{random_string}"

            Requirements:
            - Create a new, expanded prompt without mentioning or repeating the original concept
            - Focus on vivid visual details and artistic elements
            - Keep the prompt under 1000 characters
            - Do not include any meta-instructions or seed references
            - Return only the new prompt text

            Response Format:
            [Just the new prompt text, nothing else]
            """
        messages = [
            {"role": "user", "content": [{"text": prompt}]}
        ]

        print(f"[{datetime.now()}] Calling generate_prompt (Bedrock converse)...")
        result = generate_prompt(messages) # Assuming generate_prompt handles the list of messages
        print(f"[{datetime.now()}] generate_prompt call finished.")
        print(f"[{datetime.now()}] --- generate_nova_prompt END ---")
        return result
    except Exception as e:
        print(f"[{datetime.now()}] Error in generate_nova_prompt: {e}")
        print(f"[{datetime.now()}] --- generate_nova_prompt END (Error) ---")
        # Return an error message suitable for Gradio Textbox output
        return f"Error generating prompt: {str(e)}"