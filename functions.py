import json
import io
import random
import gradio as gr
from PIL import Image
from generate import *
import numpy as np
from typing import Dict, Any
from processImage import process_and_encode_image

def rgba_to_hex(rgba):
    r, g, b, _ = [int(float(x)) for x in rgba[5:-1].split(',')]
    return f"#{r:02X}{g:02X}{b:02X}"

def add_color_to_list(current_colors, new_color):
    new_color_hex = rgba_to_hex(new_color)
    color_list = current_colors.split(',')
    if new_color_hex not in color_list and len(color_list) < 10:
        color_list.append(new_color_hex)
    return ','.join(filter(None, color_list))

def create_padded_image(image, padding_percent=100):
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
    return padded

def process_composite_to_mask(original_image, composite_image, transparent=False):
    original_array = np.array(original_image.convert('RGBA'))
    if transparent:
        white_background = Image.new('RGBA', original_image.size, (255, 255, 255, 255))
        white_background.paste(original_image, (0, 0), original_image)
        return white_background
    if composite_image is None:
        mask = np.full(original_array.shape[:2], 255, dtype=np.uint8)  # Start with white
        transparent_areas = original_array[:, :, 3] == 0  # Alpha channel is 0 for transparent pixels
        mask[transparent_areas] = 0
    else:
        composite_array = np.array(composite_image.convert('RGBA'))
    
        difference = np.any(original_array != composite_array, axis=2)
        mask = np.full(original_array.shape[:2], 255, dtype=np.uint8)
        mask[difference] = 0
        
        
        
    
    return Image.fromarray(mask, mode='L')

def build_request(task_type, params, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    param_dict = {
        "TEXT_IMAGE": "textToImageParams",
        "INPAINTING": "inPaintingParams", 
        "OUTPAINTING": "outPaintingParams",
        "IMAGE_VARIATION": "imageVariationParams",
        "COLOR_GUIDED_GENERATION": "colorGuidedGenerationParams",
        "BACKGROUND_REMOVAL": "backgroundRemovalParams"
    }
    
    return json.dumps({
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
    })

def check_return(result):
    if not isinstance(result, bytes):
        return None, gr.update(visible=True, value=result)
    
    return Image.open(io.BytesIO(result)), gr.update(value=None,visible=False)


def text_to_image(prompt, negative_text=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    text_to_image_params = {"text": prompt,
                            **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
                            }
    
    body = build_request("TEXT_IMAGE", text_to_image_params, height, width, quality, cfg_scale, seed)
    result = generate_image(body)
    return check_return(result)
    

def inpainting(mask_image, mask_prompt=None, text=None, negative_text=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    image = process_and_encode_image(mask_image['background'])
    if len(image) < 200:
        return None, gr.update(visible=True, value=image)
    
    if mask_prompt and mask_image:
        raise ValueError("You must specify either maskPrompt or maskImage, but not both.")
    if not mask_prompt and not mask_image:
        raise ValueError("You must specify either maskPrompt or maskImage.")
    
    if mask_image and 'composite' in mask_image:
        mask = process_composite_to_mask(mask_image['background'], mask_image['composite'])
        mask_image = process_and_encode_image(mask)
    
    in_painting_params = {
        "image": image,  
        **({"maskImage": mask_image} if mask_image not in [None, ""] else {}),
        **({"maskPrompt": mask_prompt} if mask_prompt not in [None, ""] else {}),
        **({"text": text} if text not in [None, ""] else {}),
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }

    body = build_request("INPAINTING", in_painting_params, height, width, quality, cfg_scale, seed)
    result = generate_image(body)
    
    return check_return(result)

def outpainting(mask_image, mask_prompt=None, text=None, negative_text=None, outpainting_mode="DEFAULT", height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    image = process_and_encode_image(mask_image['background'])
    if len(value) < 200:
        return None, gr.update(visible=True, value=value)

    if mask_prompt and mask_image:
        raise ValueError("You must specify either maskPrompt or maskImage, but not both.")
    if not mask_prompt and not mask_image:
        raise ValueError("You must specify either maskPrompt or maskImage.")
    
    if mask_image and 'composite' in mask_image:
        mask = process_composite_to_mask(mask_image['background'], None)
        image = process_composite_to_mask(mask_image['background'], None, True)
        image = process_and_encode_image(image)
        mask_image = process_and_encode_image(mask)

    # Prepare the outPaintingParams dictionary
    out_painting_params = {
        "image": image,
        **({"maskImage": mask_image} if mask_image not in [None, ""] else {}),
        **({"maskPrompt": mask_prompt} if mask_prompt not in [None, ""] else {}),
        **({"text": text} if text not in [None, ""] else {"text": " "}),
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }

    body = build_request("OUTPAINTING", out_painting_params, height, width, quality, cfg_scale, seed)
    result = generate_image(body)
    
    return check_return(result)

def image_variation(images, text=None, negative_text=None, similarity_strength=0.5, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    encoded_images = []
    for image_path in images:
        with open(image_path, "rb") as image_file:
            value = process_and_encode_image(image_file)
            
            if len(value) < 200:
                return None, gr.update(visible=True, value=value)
            encoded_images.append(value)

    # Prepare the imageVariationParams dictionary
    image_variation_params = {
        "images": encoded_images,
        **({"similarityStrength": similarity_strength} if similarity_strength not in [None, ""] else {}),
        **({"text": text} if text not in [None, ""] else {}),
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }

    body = build_request("IMAGE_VARIATION", image_variation_params, height, width, quality, cfg_scale, seed)
    result = generate_image(body)
    
    return check_return(result)

def image_conditioning(condition_image, text, negative_text=None, control_mode="CANNY_EDGE", control_strength=0.7, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    condition_image_encoded = process_and_encode_image(condition_image)
    
    if len(condition_image_encoded) < 200:
        return None, gr.update(visible=True, value=condition_image_encoded)
    # Prepare the textToImageParams dictionary
    text_to_image_params = {
        "text": text,
        "controlMode": control_mode,
        "controlStrength": control_strength,
        "conditionImage": condition_image_encoded,
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }
    body = build_request("TEXT_IMAGE", text_to_image_params, height, width, quality, cfg_scale, seed)
    result = generate_image(body)
    
    return check_return(result)

def color_guided_content(text=None, reference_image=None, negative_text=None, colors=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    reference_image_str = None

    if reference_image is not None and not isinstance(reference_image, type(None)):
        reference_image_encoded = process_and_encode_image(reference_image)
        
        if len(reference_image_encoded) < 200:
            return None, gr.update(visible=True, value=reference_image_encoded)
            
    if not colors:
        colors = "#FF5733,#33FF57,#3357FF,#FF33A1,#33FFF5,#FF8C33,#8C33FF,#33FF8C,#FF3333,#33A1FF"
    
    color_guided_generation_params = {
        "text": text,
        "colors": [color.strip() for color in colors.split(',')],
        **({"referenceImage": reference_image_encoded} if reference_image_str is not None else {}),    
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }

    body = build_request("COLOR_GUIDED_GENERATION", color_guided_generation_params, height, width, quality, cfg_scale, seed)
    result = generate_image(body)
    
    return check_return(result)

def background_removal(image):
    input_image = process_and_encode_image(image)
    
    if len(input_image) < 200:
        return None, gr.update(visible=True, value=input_image)
        
    body = json.dumps({
        "taskType": "BACKGROUND_REMOVAL",
        "backgroundRemovalParams": {
            "image": input_image
        }
    })
    result = generate_image(body)
    
    return check_return(result)

def generate_nova_prompt():
    
    with open('seeds.json', 'r') as file:
        data = json.load(file)
    if 'seeds' not in data or not isinstance(data['seeds'], list):
        raise ValueError("The JSON file must contain a 'seeds' key with a list of strings.")
    
    random_string = random.choice(data['seeds'])
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
    
    return generate_prompt(messages)
