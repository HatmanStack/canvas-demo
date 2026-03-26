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

- `models/config.py` — Dataclass-based config; reads AWS creds from `AMP_AWS_ID`/`AMP_AWS_SECRET` env vars (non-reserved Lambda names)
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

GitHub Actions on push/PR to `github-branch`: lint (ruff), type check (mypy), test (pytest with `-m "not integration"`, 75% coverage minimum), and integration test (LocalStack) run as parallel jobs. Link checking (lychee) and commit message linting (conventional commits, PR-only) also run. The `all-checks` gate requires all jobs to pass.

## Key Constraints

- **Python >=3.11**, CI runs on 3.11
- **Ruff**: line length 100, strict rule set (see `pyproject.toml [tool.ruff.lint]`)
- **Coverage**: 75% minimum (`--cov-fail-under=75`)
- **Image limits**: 256-2048px per dimension, dimensions must be multiples of 64, max aspect ratio 4:1, 4MP (4,194,304 pixels) total cap
- **Bedrock model**: `amazon.nova-canvas-v1:0` (us-east-1 only)
