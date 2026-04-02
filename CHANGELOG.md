# Changelog

All notable changes to Canvas Demo will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-03-26

### Added

- Request ID generation in `gradio_handler` decorator, threaded through all log calls for request traceability
- ETag-based optimistic locking in rate limiter with retry on `PreconditionFailed`
- Conditional write (`IfNoneMatch`) for rate limiter initialization to prevent concurrent creator races
- UUID suffix on S3 storage keys to prevent collisions under concurrent Lambda invocations
- Health request counter increment in `gradio_handler` decorator
- `KeyError` guard in `_build_request` for invalid task types
- Structured logging on rate limiter fail-open events with exception type and S3 error code
- Logger level validation with `_VALID_LEVELS` frozenset and fallback to INFO
- Commit message linting (conventional commits) in CI for pull requests
- Link checking (lychee) in CI for markdown documentation
- Markdownlint in pre-commit hooks
- Dependency version pins (`>=`) for all runtime packages
- `.env.example` documentation for fallback env vars, Lambda detection vars, and `MINISTACK_URL`

### Changed

- Config uses lazy `get_config()` factory instead of module-level `AppConfig()` instantiation
- `AppConfig.__post_init__` respects explicit constructor arguments instead of always overwriting from env
- Logger uses `os.environ.get("AWS_LAMBDA_FUNCTION_NAME")` instead of `get_config().is_lambda` to avoid triggering config validation
- Service singletons (`bedrock_service`, `rate_limiter`, `health_checker`, `canvas_handlers`) use lazy accessor functions instead of module-level instances
- `AWSClientManager._reset()` acquires both `_lock` and `_client_lock` to prevent races
- NSFW check uses synchronous `urllib.request` instead of `aiohttp`/`asyncio`
- NSFW cache uses 32x32 thumbnail hash instead of full `image.tobytes()` (reduces per-lookup memory from ~16MB to ~3KB)
- NSFW `check_nsfw` returns tri-state (`True`/`False`/`None`) so skipped/failed checks are not cached as safe
- `_process_response` returns generic error message instead of leaking exception details
- `image_variation` uses list comprehension instead of per-call `ThreadPoolExecutor`
- `seeds.json` resolved via `Path(__file__).resolve()` instead of CWD-relative path
- Dockerfile pins uv to 0.11.1, uses `uv sync --frozen` instead of `pip install`, exports `.venv/bin` on PATH
- CI installs from editable install (`-e .`) instead of `requirements.txt`
- CI `all-checks` gate includes `link-check` and `commit-lint`
- mypy runs without escape hatches in CI (strict mode via `pyproject.toml`)
- `CloudWatchLogsClient` type replaces `Any` for `_cloudwatch_client` field
- Timezone-aware `datetime.now(tz=UTC)` across all four usage sites
- Gradio callbacks use lambdas for deferred handler resolution instead of eager binding
- `uv.lock` committed for reproducible builds

### Removed

- Dead code: `process_image_for_lambda`, `create_data_url` from `lambda_helpers.py`
- Dead code: `health_endpoint()` from `app.py`
- Dead code: `increment_error()` and `error_count` from `HealthCheck`
- `aiohttp` dependency (replaced by stdlib `urllib.request`)
- `pytest-asyncio` from CI and dev dependencies
- Broad mypy `disable_error_code = ["return-value"]` override (replaced with assertions)

### Fixed

- Rate limiter race condition: concurrent Lambda invocations could exceed limit due to non-atomic GET-then-PUT
- NSFW check failure cached as "safe": transient API failures no longer persist false negatives in cache
- Color picker UI component wired to colors textbox in Color Guided tab
- CLAUDE.md drift: corrected coverage threshold (75%), removed stale `@handle_gracefully` reference, fixed capability count, added missing module descriptions
- README.md drift: fixed Gradio badge, capability count, removed non-existent `/health` endpoint reference

## [1.0.0] - 2026-03-01

### Added

- Initial release with 7 image generation capabilities
- Gradio web UI with text-to-image, inpainting, outpainting, variation, conditioning, color-guided, and background removal
- AWS Bedrock Nova Canvas integration (`amazon.nova-canvas-v1:0`)
- S3-backed distributed rate limiting
- Containerized Lambda deployment via Docker
- NSFW content detection via HuggingFace API
- Health monitoring dashboard
- CI pipeline with ruff, mypy, pytest, and MiniStack integration tests
