---
title: AWS Nova Canvas
emoji: 🚀
colorFrom: blue
colorTo: red
sdk: gradio
sdk_version: 5.6.0
app_file: app.py
pinned: false
license: apache-2.0
short_description: Generate image variations
---


# AWS Nova Canvas Image Generation

A Gradio application for advanced image generation using Amazon Nova Canvas, offering comprehensive image manipulation capabilities.

## Capabilities

- **Text to Image**: Generate images from text prompts
- **Inpainting**: Modify specific image areas 
- **Outpainting**: Extend image boundaries 
- **Image Variation**: Create image variations
- **Image Conditioning**: Generate images based on input image and text
- **Color Guided Content**: Create images using reference color palettes
- **Background Removal**: Remove image backgrounds

## Prerequisites

- AWS credentials configured
- Boto3 Python library
- Gradio 5.6.0

## Technical Details

- Model: Amazon Nova Canvas (amazon.nova-canvas-v1:0)
- Image Generation Parameters:
  - Default resolution: 1024x1024
  - Quality: Standard
  - CFG Scale: 8.0
  - Configurable seed

## Documentation

For detailed usage, visit [AWS Nova documentation](https://docs.aws.amazon.com/nova/latest/userguide/what-is-nova.html).
