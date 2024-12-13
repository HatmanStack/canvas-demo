import json
import io
import random
import gradio as gr
from PIL import Image
from generate import *
from typing import Dict, Any
from processImage import process_and_encode_image

def display_image(image_bytes):
    if isinstance(image_bytes, str):
        # If we received a string (error message), return it to be displayed
        return None, gr.update(visible=True, value=image_bytes)
    elif image_bytes:
        # If we received image bytes, process and display the image
        return Image.open(io.BytesIO(image_bytes)), gr.update(visible=False)
    else:
        # Handle None case
        return None, gr.update(visible=False)

def process_optional_params(**kwargs) -> Dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}

def process_images(primary=None, secondary=None, validate=True) -> Dict[str, str]:
    if validate and primary is None:
        raise ValueError("Primary image is required.")
    result = {}
    if primary:
        result["image"] = process_and_encode_image(primary)
    if secondary:
        result["maskImage"] = process_and_encode_image(secondary)
    return result

def create_image_generation_config(height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    return {
        "numberOfImages": 1,
        "height": height,
        "width": width,
        "quality": quality,
        "cfgScale": cfg_scale,
        "seed": seed
    }

def build_request(task_type, params, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    param_dict = {"TEXT_IMAGE": "textToImageParams", "INPAINTING": "inPaintingParams", 
                  "OUTPAINTING":"outPaintingParams","IMAGE_VARIATION":"imageVariationParams",
                  "COLOR_GUIDED_GENERATION":"colorGuidedGenerationParams","BACKGROUND_REMOVAL":"backgroundRemovalParams"}
    return json.dumps({
        "taskType": task_type,
        param_dict[task_type]: params,
        "imageGenerationConfig": create_image_generation_config(
            height=height,
            width=width,
            quality=quality,
            cfg_scale=cfg_scale,
            seed=seed
        )
    })

def check_return(result):
    if not isinstance(result, bytes):
        return None, gr.update(visible=True, value=result)
        
    return Image.open(io.BytesIO(result)), gr.update(visible=False)


def text_to_image(prompt, negative_text=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    text_to_image_params = {"text": prompt,
                            **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
                            }
    
    body = build_request("TEXT_IMAGE", text_to_image_params, height, width, quality, cfg_scale, seed)
    result = generate_image(body)
    return check_return(result)
    

def inpainting(image, mask_prompt=None, mask_image=None, text=None, negative_text=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    images = process_images(primary=image, secondary=None)
    
    for value in images.values():
        if len(value) < 200:
            return None, gr.update(visible=True, value=value)
    # Prepare the inPaintingParams dictionary
    if mask_prompt and mask_image:
        raise ValueError("You must specify either maskPrompt or maskImage, but not both.")
    if not mask_prompt and not mask_image:
        raise ValueError("You must specify either maskPrompt or maskImage.")

    # Prepare the inPaintingParams dictionary with the appropriate mask parameter
    in_painting_params = {
        **images,  # Unpacks image and maskImage if present
        **({"maskPrompt": mask_prompt} if mask_prompt not in [None, ""] else {}),
        **({"text": text} if text not in [None, ""] else {}),
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }

    body = build_request("INPAINTING", in_painting_params, height, width, quality, cfg_scale, seed)
    result = generate_image(body)
    
    return check_return(result)

def outpainting(image, mask_prompt=None, mask_image=None, text=None, negative_text=None, outpainting_mode="DEFAULT", height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    images = process_images(primary=image, secondary=None)
    for value in images.values():
        if len(value) < 200:
            return None, gr.update(visible=True, value=value)

    if mask_prompt and mask_image:
        raise ValueError("You must specify either maskPrompt or maskImage, but not both.")
    if not mask_prompt and not mask_image:
        raise ValueError("You must specify either maskPrompt or maskImage.")

    # Prepare the outPaintingParams dictionary
    out_painting_params = {
        **images,  # Unpacks image and maskImage if present
        **process_optional_params(
            **({"maskPrompt": mask_prompt} if mask_prompt  not in [None, ""] else {}),
            **({"text": text} if text  not in [None, ""] else {}),
            **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
        )
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
        **({"text": text} if text not in [None, ""] else {}),
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }

    body = build_request("IMAGE_VARIATION", image_variation_params, height, width, quality, cfg_scale, seed)
    result = generate_image(body)
    
    return check_return(result)

def image_conditioning(condition_image, text, negative_text=None, control_mode="CANNY_EDGE", control_strength=0.7, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    condition_image_encoded = process_images(primary=condition_image)
    for value in condition_image_encoded.values():
        if len(value) < 200:
            return None, gr.update(visible=True, value=value)
    # Prepare the textToImageParams dictionary
    text_to_image_params = {
        "text": text,
        "controlMode": control_mode,
        "controlStrength": control_strength,
        "conditionImage": condition_image_encoded.get('image'),
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }
    body = build_request("TEXT_IMAGE", text_to_image_params, height, width, quality, cfg_scale, seed)
    result = generate_image(body)
    
    return check_return(result)

def color_guided_content(text=None, reference_image=None, negative_text=None, colors=None, height=1024, width=1024, quality="standard", cfg_scale=8.0, seed=0):
    reference_image_str = None

    if reference_image is not None and not isinstance(reference_image, type(None)):
       
        reference_image_encoded = process_images(primary=reference_image)
        for value in reference_image_encoded.values():
            if len(value) < 200:
                return None, gr.update(visible=True, value=value)
            reference_image_str = reference_image_encoded.get('image')
    if not colors:
        colors = "#FF5733,#33FF57,#3357FF,#FF33A1,#33FFF5,#FF8C33,#8C33FF,#33FF8C,#FF3333,#33A1FF"
    
    color_guided_generation_params = {
        "text": text,
        "colors": colors.split(','),
        **({"referenceImage": reference_image_str} if reference_image_str is not None else {}),    
        **({"negativeText": negative_text} if negative_text not in [None, ""] else {})
    }

    body = build_request("COLOR_GUIDED_GENERATION", color_guided_generation_params, height, width, quality, cfg_scale, seed)
    result = generate_image(body)
    
    return check_return(result)

def background_removal(image):
    input_image = process_images(primary=image)
    for value in input_image.values():
        if len(value) < 200:
            return None, gr.update(visible=True, value=value)
        
    body = json.dumps({
        "taskType": "BACKGROUND_REMOVAL",
        "backgroundRemovalParams": {
            "image": input_image.get('image')  
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
