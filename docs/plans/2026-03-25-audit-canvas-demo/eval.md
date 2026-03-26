---
type: repo-eval
target: 9
role_level: senior
date: 2026-03-25
pillar_overrides:
  # None — require 9/10 on all 12 pillars
---

# Repo Evaluation: canvas-demo

## Configuration
- **Role Level:** Senior Developer
- **Focus Areas:** Balanced evaluation across all pillars
- **Exclusions:** Standard exclusions (vendor, generated, node_modules, __pycache__)

## Combined Scorecard

| # | Lens | Pillar | Score | Target | Status |
|---|------|--------|-------|--------|--------|
| 1 | Hire | Problem-Solution Fit | 8/10 | 9 | NEEDS WORK |
| 2 | Hire | Architecture | 7/10 | 9 | NEEDS WORK |
| 3 | Hire | Code Quality | 8/10 | 9 | NEEDS WORK |
| 4 | Hire | Creativity | 7/10 | 9 | NEEDS WORK |
| 5 | Stress | Pragmatism | 7/10 | 9 | NEEDS WORK |
| 6 | Stress | Defensiveness | 6/10 | 9 | NEEDS WORK |
| 7 | Stress | Performance | 5/10 | 9 | NEEDS WORK |
| 8 | Stress | Type Rigor | 7/10 | 9 | NEEDS WORK |
| 9 | Day 2 | Test Value | 8/10 | 9 | NEEDS WORK |
| 10 | Day 2 | Reproducibility | 8/10 | 9 | NEEDS WORK |
| 11 | Day 2 | Git Hygiene | 7/10 | 9 | NEEDS WORK |
| 12 | Day 2 | Onboarding | 9/10 | 9 | PASS |

**Pillars at target (>=9):** 1/12
**Pillars needing work (<9):** 11/12

---

## Hire Evaluation -- The Pragmatist

### VERDICT
- **Decision:** HIRE
- **Overall Grade:** B+
- **One-Line:** Properly scoped solution for a demo app, with thoughtful defensive patterns and genuine architectural structure.

### SCORECARD
| Pillar | Score | Evidence |
|--------|-------|----------|
| Problem-Solution Fit | 8/10 | `pyproject.toml:6-14` -- 7 runtime deps for a Gradio + Bedrock wrapper is proportional; `Dockerfile:1-18` -- simple, correct containerization for Lambda |
| Architecture | 7/10 | `src/handlers/canvas_handlers.py:77-80` -- DI constructor enables testable handlers; `src/services/aws_client.py:30-57` -- singleton with double-checked locking is well-structured but couples class-level state |
| Code Quality | 8/10 | `src/utils/validation.py:1-192` -- thorough, standalone validators with clear error messages; `src/handlers/canvas_handlers.py:50-74` -- `gradio_handler` decorator cleanly maps domain exceptions to UI responses |
| Creativity | 7/10 | `src/services/image_processor.py:23-41` -- SHA-256 NSFW cache with FIFO eviction is a nice touch; `src/services/rate_limiter.py:67-68` -- fail-open rate limiter is the right tradeoff for a demo |

### HIGHLIGHTS
- **Brilliance:**
  - `src/handlers/canvas_handlers.py:50-74`: The `gradio_handler` decorator is a clean error-boundary pattern. It maps specific exception types (ImageError, NSFWError, RateLimitError, ValidationError) to structured Gradio UI responses and catches generic exceptions with logging. Handler methods stay focused on business logic without try/except noise.
  - `src/types/common.py:1-170`: Comprehensive TypedDict definitions for every Bedrock request type, health status, rate limit data, and Gradio image mask structure. These replace scattered `dict[str, Any]` with precise structural types.
  - `src/services/image_processor.py:178-228`: Method chaining pattern (`_convert_color_mode()._resize_for_pixels()._ensure_dimensions()`) with careful dimension/aspect-ratio math that aligns to 16px grid. The 4:1 aspect ratio guard prevents silent Bedrock API failures.
  - `tests/unit/test_canvas_handlers.py:1-375`: 30+ handler tests covering success paths, error boundaries, validation edge cases, and dependency injection. The test fixtures use constructor injection rather than patching globals.
  - `src/services/rate_limiter.py:67-68`: Fail-open on rate limiter errors is a pragmatic production decision for a demo app.

- **Concerns:**
  - `src/services/aws_client.py:326`: `_store_response_sync` uses `datetime.now()` for S3 key generation. Concurrent requests could produce key collisions.
  - `src/models/config.py:13-14`: Dataclass field defaults evaluated at class definition time via `os.getenv`. Config frozen at import time, not instantiation.
  - `src/services/rate_limiter.py:82-97`: GET-then-PUT TOCTOU race. Comment references "ETags for optimistic locking" which was removed.
  - `src/handlers/canvas_handlers.py:474-506`: `generate_nova_prompt` opens `seeds.json` relative to CWD, breaks if invoked from a different working directory.
  - `src/utils/logger.py:73-76`: `getattr(self.logger, level.lower())(message)` trusts the caller's `level` string. A typo throws AttributeError at runtime.
  - CI runs mypy with `--ignore-missing-imports --no-strict-optional --allow-untyped-defs` (`.github/workflows/ci.yml:57`), effectively disabling most strictness configured in `pyproject.toml:60-72`.

### REMEDIATION TARGETS

- **Problem-Solution Fit (current: 8/10, target: 9/10)**
  - Stale CLAUDE.md description of rate limiter mentions "ETags for optimistic locking" which no longer exists
  - `requirements.txt` pins only Pillow; boto3, gradio, etc. are unpinned. `uv.lock` exists but is untracked
  - Files: `CLAUDE.md`, `requirements.txt`, `uv.lock`
  - Estimated complexity: LOW

- **Architecture (current: 7/10, target: 9/10)**
  - `src/models/config.py:10-70`: Replace dataclass-with-getenv-defaults with factory function or `__init__` that reads env vars at call time
  - `src/services/aws_client.py:30-57`: Singleton stores clients at class level, impossible to cleanly reset between tests. Consider module-level factory with caching or pass client manager as constructor arg
  - `src/handlers/canvas_handlers.py:475`: Fix relative path `seeds.json` to use absolute path relative to module
  - Estimated complexity: MEDIUM

- **Code Quality (current: 8/10, target: 9/10)**
  - `.github/workflows/ci.yml:57`: Run mypy without escape hatches, or adjust `pyproject.toml` to match what CI enforces
  - `src/services/aws_client.py:326`: Use `datetime.now(tz=timezone.utc)` and append UUID suffix
  - `src/utils/logger.py:71-76`: Validate the `level` parameter against a known set
  - `src/handlers/canvas_handlers.py:102`: `_build_request` uses `param_dict[task_type]` without KeyError guard
  - Estimated complexity: LOW

- **Creativity (current: 7/10, target: 9/10)**
  - `_NSFWCache` hashes full `image.tobytes()` (~16MB for large images). Use lighter key (e.g., hash of downsampled thumbnail)
  - Rate limiter could use S3 conditional writes (If-None-Match) instead of racy GET/PUT
  - `log_performance` decorator applied to nearly every method including fast synchronous ones. Use threshold-based approach
  - Estimated complexity: MEDIUM

---

## Stress Evaluation -- The Oncall Engineer

### VERDICT
- **Decision:** MID-LEVEL (strong end)
- **Seniority Alignment:** Solid mid-level with some senior patterns (dependency injection, TypedDefs, thread-safe singletons). Falls short of senior on observability and distributed system rigor.
- **One-Line:** Good structure and defensive error boundaries, but the rate limiter is a race condition waiting to happen, NSFW cache will OOM on large images, and zero request traceability means debugging prod incidents blind.

### SCORECARD
| Pillar | Score | Evidence |
|--------|-------|----------|
| Pragmatism | 7/10 | `src/handlers/canvas_handlers.py:80` -- DI via constructor is clean; `src/services/image_processor.py:23-41` -- NSFW cache is over-engineered for a demo app that calls `.tobytes()` on every cache lookup |
| Defensiveness | 6/10 | `src/handlers/canvas_handlers.py:50-74` -- `gradio_handler` decorator is well-structured error boundary; `src/services/rate_limiter.py:66-68` -- fail-open on rate limit errors silently passes malformed requests through |
| Performance | 5/10 | `src/services/image_processor.py:35,40` -- `image.tobytes()` + SHA-256 runs twice per cache check on multi-megapixel images; `src/services/rate_limiter.py:83-96` -- GET-check-PUT race on S3 with no conditional writes |
| Type Rigor | 7/10 | `src/types/common.py:12-22` -- Literal types for enums enforce valid values at type-check time; `src/utils/logger.py:28` -- `_cloudwatch_client: Any | None` escapes the type system entirely |

### CRITICAL FAILURE POINTS

1. **Rate limiter race condition** (`src/services/rate_limiter.py:83-96`): The GET-check-PUT pattern on S3 has no conditional write (no ETag/If-Match). Two concurrent requests can both read the same counter, both pass, and both write back independently. Under concurrent load, rate limiting is effectively broken.

2. **NSFW cache memory bomb** (`src/services/image_processor.py:35,40`): `image.tobytes()` materializes full raw pixel array into memory to compute a hash. A 2048x2048 RGBA image is ~16MB per call. Cache miss does two 16MB allocations for hashing alone. In a Lambda with 512MB, this is a realistic OOM trigger.

3. **No request traceability** (entire `src/` directory): Zero `request_id`, correlation ID, or trace ID anywhere. Every log message is context-free. No way to correlate a user's request across Bedrock call, S3 storage, and rate limiter check.

4. **`datetime.now()` without timezone** (`src/services/aws_client.py:326`, `src/handlers/health.py:41`, `src/utils/logger.py:73`): Using naive datetimes. S3 key collisions possible under concurrent invocations.

5. **`seeds.json` relative path** (`src/handlers/canvas_handlers.py:475`): `Path("seeds.json").open()` uses CWD-relative path. Fails silently in any execution context other than Docker WORKDIR.

### HIGHLIGHTS

**Brilliance:**
- `src/handlers/canvas_handlers.py:50-74`: Clean error boundary pattern mapping domain exceptions to UI-safe responses.
- `src/services/aws_client.py:30-57`: Thread-safe singleton with double-checked locking, connection pooling, retry config, and lazy initialization.
- `src/types/common.py`: Comprehensive TypedDict definitions. `Literal` types catch invalid values at type-check time.
- `src/handlers/canvas_handlers.py:77-80`: Constructor dependency injection makes testing straightforward.

**Concerns:**
- `src/services/aws_client.py:312`: `executor.submit()` fire-and-forget for S3 storage. No metrics, no dead-letter queue, no retry. Silent data loss.
- `src/services/rate_limiter.py:104`: `return True` on any ClientError except NoSuchKey. Misconfigured bucket or permissions issue silently disables rate limiting.
- `src/services/image_processor.py:160-176`: `check_nsfw_sync` tries `asyncio.run()` then falls back to `new_event_loop()`. Creates and destroys an event loop per NSFW check.
- `src/models/config.py:13-17`: AWS credentials read from env vars at class definition time, not instantiation time. Config frozen at import.

### REMEDIATION TARGETS

- **Pragmatism (current: 7/10, target: 9/10)**
  - Replace `_NSFWCache.tobytes()` hashing with image size + mode + fast sample hash. Files: `src/services/image_processor.py:34-40`. Estimated complexity: LOW.
  - Remove NSFW async/sync dance entirely. Use `requests` instead of `aiohttp`. Files: `src/services/image_processor.py:89-176`. Estimated complexity: MEDIUM.

- **Defensiveness (current: 6/10, target: 9/10)**
  - Add request ID generation at `gradio_handler` level and thread through all log calls. Files: `src/handlers/canvas_handlers.py:50-74`, `src/utils/logger.py:71-86`. Estimated complexity: MEDIUM.
  - Add structured alerting when rate limiter fails open. Files: `src/services/rate_limiter.py:66-68, 104`. Estimated complexity: LOW.
  - Resolve `seeds.json` to absolute path relative to module file. Files: `src/handlers/canvas_handlers.py:475`. Estimated complexity: LOW.

- **Performance (current: 5/10, target: 9/10)**
  - Replace S3 GET-check-PUT rate limiter with conditional PUTs using `If-Match` on ETag, or switch to DynamoDB atomic counters. Files: `src/services/rate_limiter.py:70-98`. Estimated complexity: HIGH.
  - Eliminate double `.tobytes()` call in NSFW cache. Files: `src/services/image_processor.py:34-40`. Estimated complexity: LOW.
  - Add `datetime.now(tz=timezone.utc)` across all timestamp usage. Files: `src/services/aws_client.py:326`, `src/handlers/health.py:41,193`, `src/utils/logger.py:73`. Estimated complexity: LOW.

- **Type Rigor (current: 7/10, target: 9/10)**
  - Replace `_cloudwatch_client: Any | None` with proper `CloudWatchLogsClient` type. Files: `src/utils/logger.py:28`. Estimated complexity: LOW.
  - Use TypedDict types from `src/types/common.py` in `_build_request` instead of `dict[str, Any]`. Files: `src/handlers/canvas_handlers.py:84-117`. Estimated complexity: MEDIUM.
  - Tighten handler methods accepting `dict[str, Any]` where `GradioImageMask` TypedDict is the actual type. Estimated complexity: LOW.

---

## Day 2 Evaluation -- The Team Lead

### VERDICT
- **Decision:** TEAM LEAD MATERIAL
- **Collaboration Score:** High
- **One-Line:** Writes code for the next person: well-tested, well-documented, and reproducible from clone to first PR.

### SCORECARD
| Pillar | Score | Evidence |
|--------|-------|----------|
| Test Value | 8/10 | `tests/unit/test_canvas_handlers.py` -- 30+ behavior-oriented tests covering success paths, error paths, edge cases. `tests/unit/test_rate_limiter.py` -- tests rate limit math, fail-open behavior, S3 initialization. Tests verify *behavior* not implementation. |
| Reproducibility | 8/10 | `.github/workflows/ci.yml` -- lint, typecheck, unit test, integration test (with LocalStack). `Dockerfile`, `.dockerignore`, `.pre-commit-config.yaml`, `Makefile` all present. `uv.lock` exists but is untracked. |
| Git Hygiene | 7/10 | Recent commits use conventional prefixes (`fix:`, `refactor:`, `test:`, `ci:`, `docs:`). Pre-commit hook enforces this. Older history has bare messages ("README", "Race Condition", "ruff formating"). |
| Onboarding | 9/10 | `README.md` -- Quick Start in 4 lines, Makefile targets documented, architecture tree. `CONTRIBUTING.md` -- PR process, commit conventions, branch strategy. `.env.example` -- all vars documented. `CLAUDE.md` -- deep architectural reference. |

### RED FLAGS
- **`uv.lock` not committed.** Status shows `?? uv.lock`. A new developer running `uv pip install --system -r requirements.txt` gets whatever versions resolve at that moment. Single biggest reproducibility gap.
- **Dockerfile uses `pip` instead of `uv`.** Project standardizes on `uv` everywhere else (Makefile, CI, README), but Dockerfile runs `pip install --no-cache-dir -r requirements.txt`.
- **Dockerfile is single-stage.** No multi-stage build means build tools and caches inflate the image.
- **Some older commits lack conventional prefixes.** Commits like "README", "Race Condition", "ruff formating" (misspelled) predate the pre-commit hook.

### HIGHLIGHTS
- **Process Win: Test architecture.** Clear separation between unit (`tests/unit/`) and integration (`tests/integration/`) directories. Integration tests use LocalStack with session-scoped fixtures. `pytestmark = pytest.mark.integration` marker keeps unit tests fast.
- **Process Win: Pre-commit pipeline.** `.pre-commit-config.yaml` enforces trailing whitespace, YAML validity, large file checks, branch protection, ruff linting, ruff formatting, and conventional commit messages.
- **Process Win: Makefile as task runner.** Single-command targets for every common task. A junior can be productive immediately.
- **Process Win: Error handling hierarchy.** `tests/unit/test_exceptions.py` documents a clean custom exception hierarchy. Tests verify error codes and default messages, serving as living documentation.
- **Maintenance Drag: Mock density in handler tests.** `tests/unit/test_canvas_handlers.py` patches `process_and_encode_image` in nearly every test with a magic string. A shared fixture would reduce coupling.

### REMEDIATION TARGETS

- **Test Value (current: 8/10, target: 9/10)**
  - Extract repeated `patch("src.handlers.canvas_handlers.process_and_encode_image", return_value="a" * 201)` into a shared pytest fixture
  - Add tests verifying actual Bedrock request body structure
  - Files: `tests/unit/conftest.py`, `tests/unit/test_canvas_handlers.py`
  - Estimated complexity: LOW

- **Reproducibility (current: 8/10, target: 9/10)**
  - Commit `uv.lock` to the repository
  - Change Dockerfile to use `uv` for installation instead of `pip`
  - Consider multi-stage Dockerfile
  - Files: `Dockerfile`, `.gitignore`, `uv.lock`
  - Estimated complexity: LOW

- **Git Hygiene (current: 7/10, target: 9/10)**
  - Pre-commit hook already enforces conventions going forward
  - Add commit-message lint step to CI to catch PRs from contributors without pre-commit hooks
  - Files: `.github/workflows/ci.yml`
  - Estimated complexity: LOW

---

## Consolidated Remediation Targets

Merged and deduplicated targets from all 3 evaluators, prioritized by lowest score first:

### Priority 1: Performance (5/10)
- Replace S3 GET-check-PUT rate limiter with conditional PUTs or DynamoDB atomic counters (`src/services/rate_limiter.py:70-98`). Complexity: HIGH.
- Eliminate double `.tobytes()` in NSFW cache (`src/services/image_processor.py:34-40`). Complexity: LOW.
- Add `datetime.now(tz=timezone.utc)` across all timestamp usage. Complexity: LOW.

### Priority 2: Defensiveness (6/10)
- Add request ID generation at `gradio_handler` level and thread through all log calls (`src/handlers/canvas_handlers.py:50-74`, `src/utils/logger.py:71-86`). Complexity: MEDIUM.
- Add structured alerting when rate limiter fails open (`src/services/rate_limiter.py:66-68, 104`). Complexity: LOW.
- Resolve `seeds.json` to absolute path (`src/handlers/canvas_handlers.py:475`). Complexity: LOW.

### Priority 3: Architecture (7/10) + Pragmatism (7/10) + Type Rigor (7/10) + Creativity (7/10) + Git Hygiene (7/10)
- Replace config dataclass-with-getenv-defaults with factory function (`src/models/config.py`). Complexity: MEDIUM.
- Refactor singleton to support clean test reset (`src/services/aws_client.py:30-57`). Complexity: MEDIUM.
- Remove NSFW async/sync dance; use synchronous HTTP (`src/services/image_processor.py:89-176`). Complexity: MEDIUM.
- Replace `_cloudwatch_client: Any | None` with proper type (`src/utils/logger.py:28`). Complexity: LOW.
- Use TypedDict types in `_build_request` (`src/handlers/canvas_handlers.py:84-117`). Complexity: MEDIUM.
- Run mypy without escape hatches in CI (`.github/workflows/ci.yml:57`). Complexity: LOW.
- Add commit-message lint to CI (`.github/workflows/ci.yml`). Complexity: LOW.

### Priority 4: Problem-Solution Fit (8/10) + Code Quality (8/10) + Test Value (8/10) + Reproducibility (8/10)
- Update stale CLAUDE.md descriptions (ETags, handle_gracefully). Complexity: LOW.
- Commit `uv.lock`, switch Dockerfile to `uv`. Complexity: LOW.
- Extract repeated test mock into shared fixture (`tests/unit/conftest.py`). Complexity: LOW.
- Add tests verifying Bedrock request body structure. Complexity: LOW.
- Validate logger `level` parameter. Complexity: LOW.
