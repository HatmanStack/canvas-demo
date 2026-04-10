# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AWS Bedrock Nova Canvas image generation app built with Gradio and deployed as a containerized AWS Lambda. Provides 7 image generation capabilities (text-to-image, inpainting, outpainting, variation, conditioning, color-guided, background removal) via a web UI.

## Common Commands

### Install dependencies

```bash
uv pip install --system -r requirements.txt
uv pip install --system -e ".[dev]"
```

### Lint and format

```bash
ruff check src/ tests/
ruff format --check src/ tests/    # check only
ruff format src/ tests/             # apply formatting
ruff check --fix src/ tests/        # auto-fix lint issues
```

### Type check

```bash
mypy src/
```

For local checks with relaxed settings:

```bash
mypy src/ --ignore-missing-imports --no-strict-optional --allow-untyped-defs
```

### Run tests

```bash
pytest tests/ -v --tb=short                                          # all tests
pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=75  # with coverage
pytest tests/unit/test_validation.py                                  # single file
pytest tests/unit/test_validation.py::test_function_name              # single test
```

### Run the app locally

```bash
python app.py
```

## Architecture

**Entry point**: `app.py` — Gradio UI with 7 image generation tabs + System Info tab, Lambda/local auto-detection.

**`src/` layout**:

- `models/config.py` — Dataclass-based config; optionally reads AWS creds from `AMP_AWS_ID`/`AMP_AWS_SECRET` env vars, falls back to IAM role / default boto3 credential chain when not set
- `services/aws_client.py` — Thread-safe singleton AWS client manager with connection pooling (Bedrock in us-east-1, S3 configurable)
- `services/image_processor.py` — Image validation, resizing, encoding, mask processing
- `services/rate_limiter.py` — S3-backed distributed rate limiter using ETags for optimistic locking (20 req/20min sliding window)
- `handlers/canvas_handlers.py` — Core business logic for all image generation operations; calls Bedrock `amazon.nova-canvas-v1:0`
- `handlers/health.py` — Health checks for Bedrock, S3, and system metrics
- `utils/exceptions.py` — Custom exception hierarchy (CanvasError, ImageError, NSFWError, RateLimitError, ConfigurationError, BedrockError)
- `utils/logger.py` — CloudWatch log batching (10 logs or 30s intervals, Lambda environments only), thread-safe
- `utils/lambda_helpers.py` — Lambda environment utilities (temp file cleanup)
- `utils/validation.py` — Input validation (prompt, dimensions, seed, CFG scale, hex colors) with custom ValidationError
- `types/common.py` — TypedDict definitions for Bedrock requests, rate limit data, health status, and Gradio types

**Test fixtures** in `tests/conftest.py` provide mock AWS clients, sample images (various sizes/formats), and mock Bedrock responses.

## CI

GitHub Actions on push/PR to `main`: lint (ruff), type check (mypy), test (pytest with `-m "not integration"`, 75% coverage minimum), and integration test (MiniStack) run as parallel jobs. Link checking (lychee) and commit message linting (conventional commits, PR-only) also run. The `all-checks` gate requires all jobs to pass.

## Deployment

Deployed as a containerized Lambda in **us-west-2** via AWS CodeBuild and ECR. There is no IaC — the Lambda and CodeBuild project were created manually in the AWS console.

### AWS credentials

The Lambda uses its **execution role** (`canvas-demo-role-foz3c27c`) for all AWS access — no hardcoded keys. The role has `AmazonBedrockFullAccess` and an inline S3 policy for the image bucket. Do NOT pass `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` as env vars; these are STS temp credentials set by Lambda that require a session token. Let boto3 handle them via its default credential chain.

For local development, set `AMP_AWS_ID` and `AMP_AWS_SECRET` in `.env` (these are the only credential env vars the app reads explicitly).

### Build and deploy

CodeBuild source is an S3 bucket (not a GitHub webhook), so builds are **manual**:

```bash
# 1. Zip the build artifacts (exclude tests, dev files, .git)
zip -r canvas-demo-build.zip app.py buildspec.yaml Dockerfile requirements.txt \
  seeds.json src/ static/ uv.lock pyproject.toml \
  -x "*/__pycache__/*" "*.pyc" "src/canvas_demo.egg-info/*"

# 2. Upload to CodeBuild source bucket
aws s3 cp canvas-demo-build.zip s3://nova-image-data/codebuild/canvas-demo-build.zip

# 3. Start the build (builds Docker image and pushes to ECR)
aws codebuild start-build --project-name canvas-demo --region us-west-2 \
  --source-type-override S3 \
  --source-location-override nova-image-data/codebuild/canvas-demo-build.zip

# 4. After build completes, update Lambda to pull the new image
aws lambda update-function-code --function-name canvas-demo --region us-west-2 \
  --image-uri <ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/production/canvas-demo:latest
```

The `buildspec.yaml` expects `AWS_ACCOUNT_ID` as a CodeBuild environment variable (do not hardcode it in the file).

### Lambda environment variables

Required env vars set on the Lambda (not in code):

- `NOVA_IMAGE_BUCKET` — S3 bucket for image storage and rate limiting
- `BUCKET_REGION` — region of the S3 bucket
- `RATE_LIMIT` — requests per 20-minute window
- `HF_TOKEN` — HuggingFace token for NSFW detection
- `AWS_LWA_READINESS_CHECK_PATH` — Lambda Web Adapter health check path (`/healthz`)

## Key Constraints

- **Python >=3.11**, CI runs on 3.11
- **Ruff**: line length 100, strict rule set (see `pyproject.toml [tool.ruff.lint]`)
- **Coverage**: 75% minimum (`--cov-fail-under=75`)
- **Image limits**: 256-2048px per dimension, dimensions must be multiples of 64, max aspect ratio 4:1, 4MP (4,194,304 pixels) total cap
- **Bedrock model**: `amazon.nova-canvas-v1:0` (us-east-1 only)
