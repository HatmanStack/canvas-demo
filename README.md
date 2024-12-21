<div align="center" style="display: block;margin-left: auto;margin-right: auto;width: 50%;">
<h1>AWS Nova Canvas Image Generation</h1>
<h1 >
  <img width="300" height="300" src="sloth.jpg" alt="float-app icon">
</h1>
<div style="display: flex; justify-content: center; align-items: center;">
  <h4 style="margin: 0; display: flex;">
    <a href="https://www.apache.org/licenses/LICENSE-2.0.html">
      <img src="https://img.shields.io/badge/license-Apache2.0-blue" alt="float is under the Apache 2.0 liscense" />
    </a>
    <a href="https://docs.aws.amazon.com/nova/latest/userguide/what-is-nova.html">
      <img src="https://img.shields.io/badge/AWS%20Nova%20Canvas-violet" alt="Expo Version" />
    </a>
    <a href="https://cloud.google.com/text-to-speech/docs/basics">
      <img src="https://img.shields.io/badge/Gradio%205.6.0-yellow" alt="Google Text-To-Speech" />
    </a>
    <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python->=3.12.8-blue">
    </a>
  </h4>
</div>

  <p><b>From Thought - To Concept <br> <a href="https://hatman-aws-nova-canvas.hf.space"> Nova Canvas » </a> </b> </p>
</div>

A Gradio application for advanced image generation using AWS Nova Canvas, offering comprehensive image manipulation capabilities.

## Capabilities

- **Text to Image**: Generate images from text prompts
- **Inpainting**: Modify specific image areas 
- **Outpainting**: Extend image boundaries 
- **Image Variation**: Create image variations
- **Image Conditioning**: Generate images based on input image and text
- **Color Guided Content**: Create images using reference color palettes
- **Background Removal**: Remove image backgrounds

## Prerequisites

- AWS credentials configured (AmazonBedrockFullAccess)
- HF Token for Input Image Check
- Boto3 Python library
- Gradio 5.6.0

## Install

```script
git clone https://github.com/hatmanstack/canvas-demo.git
cd canvas-demo
python -r requirements.txt
```

- Create a .env in the root directory with AWS and HuggingFace credentials 
  - grant access in us-east-1 to Nova Family of Models
  - grant full Bedrock Access
  - grant access to s3 bucket in region of your choice

.env 
```script
AWS_ID=<aws>
AWS_SECRET=<aws>
NOVA_IMAGE_BUCKET=<bucket name>
BUCKET_REGION=<bucket region>
HF_TOKEN=<hugging face token with either read or write capabilities for content moderation>
RATE_LIMIT=<Around .04 per image for Stanard quality and .08 for Premium, each rate_limit unit counts as 1 Standard, Refreshes every 20 minutes>
```

## Technical Details

- Model: Amazon Nova Canvas (amazon.nova-canvas-v1:0)
- Model: Amazon Nova Lite (us.amazon.nova-lite-v1:0)
- Image Generation Parameters:
  - Default resolution: 1024x1024
  - Quality: Standard
  - CFG Scale: 8.0
  - Configurable seed

