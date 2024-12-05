title: AWS Nova Canvas
emoji: 🖼️
colorFrom: blue
colorTo: red
sdk: gradio
sdk_version: 5.6.0
app_file: app.py
pinned: false
license: apache2.0
short_description: Generate image variations


# Amazon Nova Canvas Image Generation

This Gradio application demonstrates various image generation capabilities using the Amazon Nova Canvas model. The application provides multiple functionalities, each accessible through its own tab, allowing users to generate and manipulate images based on text prompts and other inputs.

## Features

- **Text to Image**: Generate an image from a text prompt using the Amazon Nova Canvas model.
- **Inpainting**: Modify specific areas of an image based on a text prompt.
- **Outpainting**: Extend an image beyond its original borders using a mask and text prompt.
- **Image Variation**: Create variations of an image based on a text description.
- **Image Conditioning**: Generate an image conditioned on an input image and a text prompt.
- **Color Guided Content**: Generate an image using a color palette from a reference image and a text prompt.
- **Background Removal**: Remove the background from an image.

## Usage

1. **Text to Image**: Enter a descriptive text prompt and click "Generate" to create an image.
2. **Inpainting**: Upload an image, provide a mask prompt, and click "Generate" to modify specific areas.
3. **Outpainting**: Upload an image and a mask image, provide a text prompt, and click "Generate" to extend the image.
4. **Image Variation**: Upload an image, provide a text description, and click "Generate" to create variations.
5. **Image Conditioning**: Upload an image, provide a text prompt, and click "Generate" to condition the image.
6. **Color Guided Content**: Upload an image, provide a text prompt and color palette, and click "Generate" to guide content generation.
7. **Background Removal**: Upload an image and click "Generate" to remove the background.

## Excellent Documentation

<p>For more information, visit <a href="https://docs.aws.amazon.com/nova/latest/userguide/what-is-nova.html">AWS Nova documentation</a>.</p>

