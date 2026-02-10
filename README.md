<div align="center">
<h1>
AWS Nova Canvas Image Generation
</h1>
<h1>
  <img width="300" height="300" src="sloth.jpg" alt="canvas-demo icon">
</h1>
<div style="display: flex; justify-content: center; align-items: center;">
  <h4 style="margin: 0; display: flex;">
    <a href="https://www.apache.org/licenses/LICENSE-2.0.html">
      <img src="https://img.shields.io/badge/license-Apache2.0-blue" alt="Apache 2.0 license" />
    </a>
    <a href="https://docs.aws.amazon.com/nova/latest/userguide/what-is-nova.html">
      <img src="https://img.shields.io/badge/AWS%20Nova%20Canvas-violet" alt="AWS Nova Canvas" />
    </a>
    <a href="https://gradio.app/">
      <img src="https://img.shields.io/badge/Gradio%205.6.0-yellow" alt="Gradio" />
    </a>
    <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python->=3.11-blue">
    </a>
  </h4>
</div>
<br>
  <p><b>From Thought - To Concept <br> <a href="https://t7bmxtdc6ojbkd3zgknxe32xdm0oqxkw.lambda-url.us-west-2.on.aws/"> Nova Canvas » </a> </b> </p>
</div>

An optimized, high-performance Gradio application for advanced image generation using AWS Nova Canvas. This refactored version provides comprehensive image manipulation capabilities with improved error handling, performance optimizations, and better monitoring.


## Capabilities

- **Text to Image**: Generate images from text prompts
- **Inpainting**: Modify specific image areas
- **Outpainting**: Extend image boundaries
- **Image Variation**: Create image variations
- **Image Conditioning**: Generate images based on input image and text
- **Color Guided Content**: Create images using reference color palettes
- **Background Removal**: Remove image backgrounds
- **Health Monitoring**: Real-time system health and performance metrics

## Prerequisites

- AWS credentials configured (AmazonBedrockFullAccess)
- HF Token for NSFW content checking (optional)
- Python >= 3.11
- Docker (for containerized deployment)

## Quick Start

```bash
git clone <repository-url>
cd canvas-demo
make install-dev
cp .env.example .env  # Edit with your credentials
make run
```

## Installation

```bash
uv pip install --system -r requirements.txt
uv pip install --system -e ".[dev]"  # For development
```

## Configuration

Copy `.env.example` to `.env` and fill in your values. See `.env.example` for all available options.

## Running the Application

### Local Development
```bash
make run
# or
python app.py
```

### Docker Deployment
```bash
docker build -t canvas-demo .
docker run -p 8080:8080 --env-file .env canvas-demo
```

### AWS Lambda Deployment
The application automatically detects Lambda environment and configures accordingly.

## Development

```bash
make lint         # Run linter and format check
make format       # Auto-fix formatting
make typecheck    # Run mypy
make test         # Run tests
make test-cov     # Run tests with coverage (75% minimum)
make clean        # Remove build artifacts
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full development workflow.

## Monitoring & Health Checks

### Health Check Endpoint
Access `/health` for health status or use the "System Info" tab in the UI.

## Architecture

```
src/
├── models/          # Configuration and data models
├── services/        # Business logic and AWS integrations
├── handlers/        # Request handlers and business operations
└── utils/           # Utilities (logging, exceptions, etc.)
```

### Key Components

- **Config Management**: `src/models/config.py` - Centralized configuration
- **AWS Services**: `src/services/aws_client.py` - Optimized AWS client management
- **Image Processing**: `src/services/image_processor.py` - Image operations with NSFW checking
- **Rate Limiting**: `src/services/rate_limiter.py` - S3-backed distributed rate limiting
- **Health Monitoring**: `src/handlers/health.py` - System health checks
- **Canvas Operations**: `src/handlers/canvas_handlers.py` - Main business logic

## Technical Details

- **Model**: Amazon Nova Canvas (amazon.nova-canvas-v1:0)
- **Prompt Model**: Amazon Nova Lite (us.amazon.nova-lite-v1:0)
- **Default Resolution**: 1024x1024
- **Supported Formats**: PNG, JPG
- **Max Image Size**: 4MP (4194304 pixels)
- **Rate Limiting**: Configurable (default: 20 requests/20min)

## License

Apache 2.0 License

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
