---
type: repo-health
date: 2026-03-25
goal: general-health-check
---

# Codebase Health Audit: canvas-demo

## Configuration
- **Goal:** General health check — scan all 4 vectors equally
- **Scope:** Full repo, no constraints
- **Deployment Target:** Serverless (Lambda) — cold starts, execution limits, stateless constraints
- **Existing Tooling:** Full setup — linters (ruff), CI pipeline (GitHub Actions), type checking (mypy)
- **Constraints:** None

## Summary
- Overall health: FAIR
- Biggest structural risk: Module-level instantiation of all global singletons (config, AWS clients, rate limiter, handlers) at import time causes cascading failures if any env var is missing, and inflates Lambda cold start times.
- Biggest operational risk: Rate limiter uses non-atomic S3 GET-then-PUT, creating a race condition window where concurrent Lambda invocations can exceed the rate limit.
- Total findings: 3 critical, 7 high, 9 medium, 5 low

## Tech Debt Ledger

### CRITICAL

1. **[Operational Debt]** `src/services/rate_limiter.py:82-98`
   - **The Debt:** `_check_and_increment` performs a non-atomic read-modify-write cycle against S3 (GET object, check, PUT object). There is no optimistic locking (ETags), no conditional writes, and no DynamoDB-style atomic counter. The CLAUDE.md project description claims "ETags for optimistic locking" but no ETag is read or used anywhere in the code.
   - **The Risk:** Under concurrent Lambda invocations, two requests can both read the same rate data, both pass the check, and both write back, allowing the rate limit to be silently exceeded. For a public-facing demo this could lead to runaway Bedrock costs.

2. **[Architectural Debt]** `src/models/config.py:70`, `src/services/aws_client.py:355`, `src/services/rate_limiter.py:222`, `src/handlers/canvas_handlers.py:510`
   - **The Debt:** All core singletons are instantiated at module scope. `config = AppConfig()` runs at import time and raises `ConfigurationError` if env vars are missing. Every other module imports `config`, so importing *any* source file requires all AWS credentials to be present. This makes testing require env var stubs in `conftest.py` before any `src` import, and means a Lambda cold start performs all initialization (Bedrock client, S3 client, thread pool) eagerly regardless of the request path.
   - **The Risk:** Import-time side effects break test isolation, prevent partial module loading, and extend cold start latency. The `conftest.py` workaround with `os.environ.setdefault` is fragile; any new test file that imports `src` without the fixture will crash.

3. **[Operational Debt]** `src/services/aws_client.py:302-315` (async S3 storage via ThreadPoolExecutor)
   - **The Debt:** `_store_response_async` submits S3 put_object calls to a thread pool that persists across Lambda invocations (class-level `_executor`). In Lambda, the execution environment freezes after the response is returned. Background threads submitted to the executor may be silently killed when the environment freezes, or may execute during the next invocation's context, corrupting request-response pairing.
   - **The Risk:** Image/response data silently lost in Lambda. No error surfaces because the fire-and-forget pattern has no callback or future tracking.

### HIGH

4. **[Architectural Debt]** `src/handlers/canvas_handlers.py:470-506`
   - **The Debt:** `generate_nova_prompt` opens `seeds.json` via a relative path (`Path("seeds.json").open()`). The file is only guaranteed to exist in the Docker container (Dockerfile line 11 copies it to `/app`). In Lambda, the current working directory may not be `/app`; Gradio may change cwd. Locally, it depends on where you run `python app.py` from.
   - **The Risk:** `FileNotFoundError` at runtime when the cwd is not the project root, leading to prompt generation failures that surface only as a string error return (not an exception).

5. **[Operational Debt]** `src/services/image_processor.py:160-176`
   - **The Debt:** `check_nsfw_sync` calls `asyncio.run()` from within what is expected to be a synchronous Gradio handler thread. Gradio internally runs an asyncio event loop. If the handler is called from an async context (possible in newer Gradio versions), `asyncio.run()` raises `RuntimeError`. The fallback creates a new event loop (`asyncio.new_event_loop()`), but this pattern is fragile and creates an orphaned loop per call.
   - **The Risk:** NSFW check silently fails or raises unhandled exceptions depending on the Gradio runtime context. The `except RuntimeError` fallback masks the root cause.

6. **[Structural Design Debt]** `src/services/aws_client.py:30-141`
   - **The Debt:** `AWSClientManager` uses `__new__`-based singleton with double-checked locking and class-level mutable state (`_bedrock_client`, `_s3_client`, `_logs_client`, `_executor`). This pattern is notoriously hard to test and reset between test runs. The class-level clients survive across test cases because they are never cleared.
   - **The Risk:** Test pollution; mocked clients from one test leak into another. The singleton cannot be reset without monkey-patching class attributes directly.

7. **[Operational Debt]** `src/services/image_processor.py:34-40`
   - **The Debt:** `_NSFWCache` calls `image.tobytes()` to compute SHA-256 hashes. For a 2048x2048 RGBA image, `tobytes()` materializes ~16MB of pixel data in memory just for hashing. The cache stores up to 128 entries, and each `put` and `get` call re-computes the hash (two `tobytes()` + `sha256` calls per cached check).
   - **The Risk:** In Lambda with limited memory (typically 512MB-3GB), processing large images doubles memory pressure. Two concurrent image operations could push memory past the Lambda limit.

8. **[Structural Design Debt]** `src/services/aws_client.py:317-351`
   - **The Debt:** Every single image generation call triggers an S3 upload of both the request JSON and the full image bytes (`_store_response_sync`). This happens unconditionally on every invocation, adding latency and S3 costs. There is no toggle, no sampling, and no opt-out mechanism.
   - **The Risk:** S3 storage costs grow linearly with usage. In the async path, failures are silently swallowed (line 351: `app_logger.warning`). The stored request body may contain large base64-encoded images, doubling storage.

9. **[Operational Debt]** `src/utils/logger.py:71-93`
   - **The Debt:** The `log` method acquires `_batch_lock` on every log call in Lambda. The flush check (`len >= batch_size or time elapsed`) is inside the lock. If a CloudWatch `put_log_events` call takes seconds (common under cold start), all other threads block on every log statement.
   - **The Risk:** Log lock contention under concurrent requests degrades request latency. The `__del__` finalizer-based flush (line 134-137) is unreliable in Python; the GC may never call it.

10. **[Code Hygiene Debt]** `src/services/aws_client.py:19-27`
    - **The Debt:** Six TYPE_CHECKING-only imports (`BedrockRuntimeClient`, `ConverseResponseTypeDef`, `InvokeModelResponseTypeDef`, `MessageTypeDef`, `CloudWatchLogsClient`, `S3Client`) are flagged as unused by vulture at 90% confidence. `CloudWatchLogsClient` and `S3Client` are never referenced in type annotations in this file.
    - **The Risk:** Dead imports obscure which type stubs are actually needed, increasing maintenance burden when updating `boto3-stubs`.

### MEDIUM

11. **[Architectural Debt]** `app.py:11` (module-level side effect)
    - **The Debt:** `app_logger.info("Starting Canvas Demo application")` runs at import time. Combined with the Gradio `gr.Blocks` context manager at module scope (line 67), importing `app.py` constructs the entire UI and logs to CloudWatch. This prevents any form of lazy initialization.
    - **The Risk:** Import-time side effects prevent using `app.py` as a module in tests or alternative entry points without triggering full initialization.

12. **[Operational Debt]** `src/handlers/canvas_handlers.py:127-129`
    - **The Debt:** `_process_response` catches `Exception` and returns an error string that includes the raw exception message (`f"Failed to process image: {e!s}"`). This leaks internal error details to the end user.
    - **The Risk:** Information disclosure; internal stack details or file paths could be exposed in the Gradio UI.

13. **[Structural Design Debt]** `src/handlers/canvas_handlers.py:177-229`, `232-293`
    - **The Debt:** The `inpainting` and `outpainting` methods share nearly identical mask-processing logic: check for `mask_image`, extract `background`, handle `mask_prompt` vs `composite`, call `process_composite_to_mask`, build params dict. The two methods differ only in the addition of `outPaintingMode` and the transparent mask variant.
    - **The Risk:** Any bug fix to mask handling must be applied in two places. Divergence risk increases with future maintenance.

14. **[Operational Debt]** `src/models/config.py:26` (`bedrock_timeout: int = 300`)
    - **The Debt:** The Bedrock read timeout is set to 300 seconds (5 minutes). Lambda has a maximum execution time (typically 15 minutes for container images, but API Gateway integration limits to 30 seconds). A 300-second timeout on a Bedrock call behind API Gateway will always hit the gateway timeout first, resulting in a 504 to the user while the Lambda continues running and accruing cost.
    - **The Risk:** Wasted Lambda compute time on requests that have already timed out at the gateway level.

15. **[Code Hygiene Debt]** `src/services/aws_client.py:326`
    - **The Debt:** `datetime.now()` is called without a timezone. All four usages in the codebase (`aws_client.py:326`, `logger.py:73`, `health.py:41`, `health.py:193`) use naive datetimes. In Lambda, the system timezone is UTC, but this is an implicit dependency.
    - **The Risk:** Timestamp inconsistencies if the code ever runs in a non-UTC environment. S3 object keys using local time make log correlation harder.

16. **[Operational Debt]** `src/handlers/canvas_handlers.py:328-329`
    - **The Debt:** `image_variation` creates a new `ThreadPoolExecutor` per call for parallel image encoding (`with ThreadPoolExecutor(max_workers=min(len(images), 5))`). Each call spins up threads that are torn down after the `with` block exits.
    - **The Risk:** Thread churn on every image variation request. In Lambda's constrained environment, creating/destroying thread pools adds latency.

17. **[Code Hygiene Debt]** `src/utils/lambda_helpers.py:18-71`, `73-120`
    - **The Debt:** Vulture flags `process_image_for_lambda` and `create_data_url` as unused (60% confidence). Neither method is called anywhere in the codebase outside the class definition. The `lambda_image_handler` global is imported in `app.py` but only `cleanup_temp_files` is called.
    - **The Risk:** Dead code increases maintenance surface. The unused methods suggest an incomplete refactor where image handling was moved elsewhere.

18. **[Structural Design Debt]** `pyproject.toml:8` and `requirements.txt`
    - **The Debt:** `boto3` has no version pin in either `requirements.txt` or `pyproject.toml`. Other critical dependencies (`gradio`, `aiohttp`, `psutil`, `numpy`) are also unpinned. Only `Pillow` has a pin (`==12.1.1`). The `uv.lock` file exists but is untracked.
    - **The Risk:** Builds are non-reproducible. A new `boto3` release with breaking API changes could break production without any code change. The Dockerfile uses `pip install` with `requirements.txt`, so there is no lock file protection in production builds.

19. **[Operational Debt]** `Dockerfile:8`
    - **The Debt:** The Dockerfile uses `pip install` directly instead of `uv`, contradicting the project's stated Python package management policy. There is also no `--require-hashes` or lock file usage, and no multi-stage build to reduce the final image size.
    - **The Risk:** Container image includes build tools and caches. Without hash verification, supply chain attacks via dependency confusion are possible.

### LOW

20. **[Code Hygiene Debt]** `app.py:293`
    - **The Debt:** The `color_picker` Gradio component is created but never wired to any handler's inputs. It displays in the UI but its value is discarded.
    - **The Risk:** Users may expect the color picker to influence generation, but it has no effect. Misleading UX.

21. **[Code Hygiene Debt]** `app.py:362-365`
    - **The Debt:** `health_endpoint()` function is defined but never registered as an endpoint. Gradio does not automatically expose it; it would need to be mounted as an API route.
    - **The Risk:** Dead code. The health check is only accessible through the "System Info" Gradio tab, not as a proper HTTP endpoint for load balancers or monitoring.

22. **[Code Hygiene Debt]** `src/handlers/health.py:27` — **RESOLVED**
    - **The Debt:** `increment_error()` was defined on `HealthCheck` but never called. The `error_count` and `error_rate` metrics were always 0.
    - **Resolution:** `increment_error()` and `error_count` were removed in Phase 1. The `error_rate` field was removed from `MetricsInfo` TypedDict.

23. **[Operational Debt]** `src/services/aws_client.py:326`
    - **The Debt:** S3 object keys use `datetime.now().strftime("%Y%m%d_%H%M%S_%f")` as the sole identifier. Under concurrent Lambda invocations, two requests processed in the same microsecond would overwrite each other's S3 objects.
    - **The Risk:** Silent data loss of stored request/image pairs under concurrent load.

24. **[Code Hygiene Debt]** Vulnerability: `pygments 2.19.2` has CVE-2026-4539
    - **The Debt:** `pip-audit` reports a known vulnerability in `pygments`, a transitive dependency.
    - **The Risk:** Depends on the CVE severity. Pygments is likely pulled in by Gradio and used only for syntax highlighting, limiting exposure.

## Quick Wins

1. `src/handlers/canvas_handlers.py:475` -- Change `Path("seeds.json")` to `Path(__file__).parent.parent.parent / "seeds.json"` or accept a configurable path. Estimated effort: < 15 minutes.
2. `src/handlers/health.py:27` -- Either wire `increment_error()` into the `gradio_handler` decorator's exception paths, or delete the method and the `error_count` field. Estimated effort: < 30 minutes.
3. `app.py:293` -- Either wire the `color_picker` value into `color_guided_content` inputs, or remove the component. Estimated effort: < 15 minutes.
4. `src/services/aws_client.py:326` -- Add a UUID suffix to S3 keys to prevent overwrites. Estimated effort: < 15 minutes.
5. `src/utils/lambda_helpers.py:18-120` -- Delete `process_image_for_lambda` and `create_data_url` (confirmed unused). Estimated effort: < 15 minutes.

## Automated Scan Results

**Dead code (vulture):**
- 2 unused methods in `lambda_helpers.py` (90% likely dead)
- 6 unused TYPE_CHECKING imports in `aws_client.py` (90% confidence; 2-4 are genuinely unused)
- `health_endpoint` function in `app.py` (unreachable)
- `increment_error` method in `health.py` (never called)
- ~40 TypedDict field warnings in `types/common.py` (false positives; TypedDict fields are accessed via dict syntax)

**Vulnerability scan (pip-audit):**
- 1 known vulnerability: `pygments 2.19.2` (CVE-2026-4539)

**Secrets scan:**
- `.env` is properly gitignored
- `.env.example` exists with placeholder values (no real credentials)
- Config reads from env vars with empty string defaults (safe)

**Git hygiene:**
- `uv.lock` is untracked (should either be committed for reproducibility or explicitly gitignored)
- `.venv` has a broken Python symlink (local dev issue, not shipped)
- No committed build artifacts or secrets detected
