# Project Roadmap

Items identified during the 2026-03-25 audit that were not addressed in the remediation pipeline. Organized by priority and effort.

Audit source documents: `docs/plans/2026-03-25-audit-canvas-demo/`

## Operational Resilience

### S3 fire-and-forget in Lambda

`src/services/aws_client.py` — `_store_response_async` submits S3 uploads to a class-level `ThreadPoolExecutor`. In Lambda, the execution environment freezes after the response returns. Background threads may be killed mid-upload or execute during the next invocation's context, corrupting request-response pairing.

**Risk:** Silent data loss of stored images/responses.
**Options:** Switch to synchronous upload before returning, or accept the loss for a demo app.
**Effort:** Low
**Source:** Health audit #3 (CRITICAL)

### Unconditional S3 storage on every request

`src/services/aws_client.py` — Every image generation call uploads both the request JSON and the full image to S3. No toggle, sampling, or opt-out. The stored request body may contain large base64-encoded images, roughly doubling storage per call.

**Risk:** S3 costs grow linearly with usage. Async upload failures are silently swallowed.
**Options:** Add a config toggle (`store_responses: bool`), or switch to sampling (store 1 in N requests).
**Effort:** Low
**Source:** Health audit #8 (HIGH)

### Logger lock contention

`src/utils/logger.py` — The `log` method holds `_batch_lock` while checking flush conditions. If a CloudWatch `put_log_events` call is slow (common during cold starts), all other threads block on every log statement. The `__del__` finalizer-based flush is unreliable in Python.

**Risk:** Log contention degrades request latency under concurrent load.
**Options:** Move the flush to a separate thread with a queue, or flush outside the lock.
**Effort:** Medium
**Source:** Health audit #9 (HIGH)

### Bedrock timeout vs API Gateway timeout

`src/models/config.py` — `bedrock_timeout` defaults to 300 seconds. API Gateway integration timeout is typically 30 seconds. A Bedrock call that takes longer than 30 seconds results in a 504 to the user while the Lambda keeps running and accruing cost.

**Risk:** Wasted compute on requests the user has already abandoned.
**Options:** Lower `bedrock_timeout` to match or slightly exceed the API Gateway timeout (e.g., 35 seconds). Add a note in `.env.example`.
**Effort:** Low
**Source:** Health audit #14 (MEDIUM)

## Architecture

### `app.py` import-time side effects

`app.py` constructs the entire Gradio UI at module scope inside a `gr.Blocks` context manager. Importing the module triggers full initialization and a CloudWatch log write. This prevents lazy startup and makes `app.py` unusable as an importable module in tests or alternative entry points.

**Risk:** Inflated cold start time. No way to partially import.
**Options:** Wrap UI construction in a `create_app()` factory function. Call it from `if __name__ == "__main__"` and from the Lambda handler.
**Effort:** Medium
**Source:** Health audit #11 (MEDIUM)

### Inpainting/outpainting mask duplication

`src/handlers/canvas_handlers.py` — The `inpainting` and `outpainting` methods share nearly identical mask-processing logic (check for mask, extract background, handle mask_prompt vs composite, build params). They differ only in `outPaintingMode` and the transparent mask variant.

**Risk:** Bug fixes to mask handling must be applied in two places.
**Options:** Extract shared mask-processing into a private `_process_mask_params` method.
**Effort:** Low
**Source:** Health audit #13 (MEDIUM)

### Singleton pattern complexity

`src/services/aws_client.py` — `AWSClientManager` uses `__new__`-based singleton with double-checked locking and class-level mutable state. The `_reset()` classmethod was added during remediation for test isolation, but the underlying pattern remains harder to reason about than a simple module-level factory with caching.

**Risk:** Maintenance burden. New contributors may not understand the `__new__` pattern.
**Options:** Replace with a module-level `_instance` variable and `get_client_manager()` factory, matching the pattern used for config after remediation.
**Effort:** Medium
**Source:** Eval (Architecture pillar, 7/10)

## Code Hygiene

### Unused TYPE_CHECKING imports

`src/services/aws_client.py` — Vulture flagged `CloudWatchLogsClient` and `S3Client` as unused in this file's type annotations (they are inferred from boto3 return types). The implementer verified during Phase 1 that all 6 imports are referenced in string annotations, so this may be a false positive. Worth re-checking after future refactors.

**Risk:** Low. Minor maintenance noise.
**Effort:** Low
**Source:** Health audit #10 (HIGH)

### pygments CVE-2026-4539

`pygments 2.19.2` has a known vulnerability. It is a transitive dependency pulled in by Gradio for syntax highlighting.

**Risk:** Depends on CVE severity and attack surface. Pygments processes user-visible output, not user input, limiting exposure.
**Options:** Wait for a Gradio release that bumps pygments, or pin a patched version if available.
**Effort:** Low (once a fix is available)
**Source:** Health audit #24 (LOW)

## Testing

### Test mock coupling

`tests/unit/test_canvas_handlers.py` patches `process_and_encode_image` in nearly every test with a magic string (`"a" * 201`). If the image processor interface changes, many tests break simultaneously.

**Options:** Extract into a shared pytest fixture in `tests/unit/conftest.py`.
**Effort:** Low
**Source:** Eval (Test Value pillar, 8/10)

### Bedrock request body assertions

Handler tests verify that `generate_image` was called but not with what arguments. No tests validate the actual JSON payload structure sent to Bedrock.

**Options:** Add `assert_called_with` or snapshot tests for the request body on key operations (text-to-image, inpainting at minimum).
**Effort:** Low
**Source:** Eval (Test Value pillar, 8/10)

## Infrastructure

### Multi-stage Dockerfile

The Dockerfile is single-stage. Build tools and pip caches may inflate the image, increasing Lambda cold start time.

**Options:** Add a builder stage that installs dependencies, then copy only the installed packages and app code into the final stage.
**Effort:** Low
**Source:** Eval (Reproducibility pillar, 8/10)

### `log_performance` decorator noise

The `log_performance` decorator is applied to nearly every method, including fast synchronous ones like `_convert_color_mode`. This adds noise to logs without useful signal.

**Options:** Add a threshold parameter (only log if duration exceeds N ms), or remove from trivially fast methods.
**Effort:** Low
**Source:** Eval (Creativity pillar, 7/10)
