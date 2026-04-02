# Feedback: 2026-03-25-audit-canvas-demo

## Post-Remediation Verification (2026-03-25)

**Test Suite:** 163 passed, 0 failed, 81.72% coverage (threshold: 75%). No regressions.

### eval.md Remediation Targets

#### Priority 1: Performance (was 5/10)

| Finding | Status | Evidence |
|---------|--------|----------|
| Rate limiter GET-check-PUT race (`rate_limiter.py:82-98`) | VERIFIED | `_get_rate_data` returns ETag (line 140), `_put_rate_data` uses `IfMatch` (line 160), retry loop on `PreconditionFailed` (lines 103-109). Tests confirm ETag locking behavior. |
| Double `.tobytes()` in NSFW cache (`image_processor.py:34-40`) | VERIFIED | `_compute_key` now thumbnails to 32x32 before hashing (line 42-44). Docstring documents reduction from ~16MB to ~3KB. Test `test_large_image_does_not_allocate_full_tobytes` validates. |
| `datetime.now(tz=timezone.utc)` across codebase | VERIFIED | `aws_client.py:9` imports `UTC`, line 339 uses `datetime.now(tz=UTC)`. `logger.py:8` imports `UTC`, line 81 uses `datetime.now(tz=UTC)`. `health.py:3` imports `UTC`, lines 35, 185 use `datetime.now(tz=UTC)`. |

#### Priority 2: Defensiveness (was 6/10)

| Finding | Status | Evidence |
|---------|--------|----------|
| Request ID generation at `gradio_handler` level | VERIFIED | `canvas_handlers.py:62` generates `request_id = uuid.uuid4().hex[:12]`, threaded through `app_logger.info/warning/error` calls (lines 63, 66, 69, 72, 75). Logger `log` method accepts `request_id` kwarg (line 76). |
| Structured alerting when rate limiter fails open | VERIFIED | `rate_limiter.py:115-119` logs warning with error code on ClientError fail-open. Line 67-68 logs explicit "fail-open" message with exception type/message. |
| `seeds.json` absolute path | VERIFIED | `canvas_handlers.py:486` uses `Path(__file__).resolve().parent.parent.parent / "seeds.json"` instead of relative `Path("seeds.json")`. |

#### Priority 3: Architecture (was 7/10), Pragmatism, Type Rigor, Creativity, Git Hygiene

| Finding | Status | Evidence |
|---------|--------|----------|
| Config factory instead of import-time `os.getenv` | VERIFIED | `config.py` uses `get_config()` factory (line 95) with lazy singleton. `__post_init__` reads env vars at instantiation (line 46 comment). No module-level `config = AppConfig()`. `reset_config()` available for tests. |
| Singleton test reset (`aws_client.py`) | VERIFIED | `AWSClientManager._reset()` method (line 74) clears all class-level state. `tests/unit/conftest.py` calls `_reset()` after each test via autouse fixture. |
| NSFW async/sync dance removed | VERIFIED | `image_processor.py` uses synchronous `urllib.request` (lines 116-130) instead of `aiohttp`. No `asyncio.run()` or `asyncio.new_event_loop()` anywhere in the file. |
| `_cloudwatch_client: Any` replaced with proper type | VERIFIED | `logger.py:31` declares `_cloudwatch_client: CloudWatchLogsClient \| None` with `CloudWatchLogsClient` imported under `TYPE_CHECKING` (line 13). |
| mypy without escape hatches in CI | VERIFIED | `ci.yml:57` runs `mypy src/` without `--ignore-missing-imports`, `--no-strict-optional`, or `--allow-untyped-defs`. `pyproject.toml` strict settings apply. Per-package overrides for gradio/PIL/numpy/psutil handle missing stubs. |
| Commit-message lint in CI | VERIFIED | `ci.yml:145-157` adds `commit-lint` job using `webiny/action-conventional-commits@v1.3.0`, runs on PRs only. |
| Logger `level` validation | VERIFIED | `logger.py:74` defines `_VALID_LEVELS` frozenset. Line 78 falls back to `"INFO"` if level not in set. Test `test_invalid_level_falls_back_to_info` confirms. |
| `_build_request` KeyError guard | VERIFIED | `canvas_handlers.py:110-111` checks `if task_type not in param_dict` and raises `ValueError`. Test `test_build_request_invalid_task_type_raises_value_error` confirms. |
| `_process_response` error message sanitization | VERIFIED | `canvas_handlers.py:138-141` returns generic "Failed to process the generated image. Please try again." instead of leaking raw exception message. Test `test_process_response_invalid_bytes_returns_generic_error` confirms. |

#### Priority 4: Problem-Solution Fit, Code Quality, Test Value, Reproducibility

| Finding | Status | Evidence |
|---------|--------|----------|
| CLAUDE.md stale ETags description | PARTIALLY VERIFIED | `CLAUDE.md:57` still says "S3-backed distributed rate limiter using ETags for optimistic locking". The code now does use ETags, so this description is now accurate rather than stale. However, this was fixed by changing the code to match the docs rather than updating the docs, which is a valid approach. |
| `uv.lock` committed | VERIFIED | `git ls-files uv.lock` returns the file. Dockerfile line 9 copies it. |
| Dockerfile uses `uv` instead of `pip` | VERIFIED | `Dockerfile:6` copies uv binary, line 10 runs `uv sync --frozen --no-dev --no-editable`. No `pip install` anywhere. |
| `requirements.txt` dependency pinning | VERIFIED | `requirements.txt` now pins all deps with `>=` lower bounds: `Pillow>=12.1.0`, `boto3>=1.35.0`, `gradio>=5.0.0`, etc. `uv.lock` provides exact reproducibility. |
| CLAUDE.md coverage threshold corrected | VERIFIED | `CLAUDE.md:76` says "75% minimum (`--cov-fail-under=75`)", matching `pyproject.toml:123`, `Makefile`, and `ci.yml:82`. |
| CLAUDE.md `@handle_gracefully` reference removed | VERIFIED | `CLAUDE.md:60` now describes `utils/exceptions.py` as "Custom exception hierarchy" with class names listed. No mention of `@handle_gracefully`. |
| CLAUDE.md missing module descriptions added | VERIFIED | `CLAUDE.md:62-64` documents `lambda_helpers.py`, `validation.py`, and `types/common.py`. |

### health-audit.md Findings

#### CRITICAL

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| 1 | Rate limiter non-atomic S3 race | VERIFIED | ETag-based optimistic locking implemented with retry loop. See Priority 1 above. |
| 2 | Module-level singleton instantiation | VERIFIED | All four singletons (`config`, `bedrock_service`, `rate_limiter`, `canvas_handlers`) use lazy factory functions (`get_config()`, `get_bedrock_service()`, `get_rate_limiter()`, `get_canvas_handlers()`). No import-time instantiation. |
| 3 | Async S3 storage thread safety in Lambda | NOT REMEDIATED | `aws_client.py:315-328` still uses `executor.submit()` fire-and-forget pattern. This was not listed as a remediation target in the plan, so it was likely a conscious decision to defer. |

#### HIGH

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| 4 | `seeds.json` relative path | VERIFIED | See Priority 2 above. |
| 5 | NSFW async/sync dance | VERIFIED | Replaced with synchronous `urllib.request`. See Priority 3 above. |
| 6 | Singleton test reset | VERIFIED | `_reset()` method + autouse fixture in `tests/unit/conftest.py`. |
| 7 | NSFW cache memory bomb | VERIFIED | Thumbnail-based hashing. See Priority 1 above. |
| 8 | Unconditional S3 storage on every call | NOT REMEDIATED | `aws_client.py:315` still stores every request/response unconditionally. Not listed as remediation target. |
| 9 | Logger lock contention | NOT REMEDIATED | Lock-per-log-call pattern unchanged in `logger.py:88`. Not listed as remediation target. |
| 10 | Unused TYPE_CHECKING imports | NOT REMEDIATED | `aws_client.py:20-28` still has all six TYPE_CHECKING imports. Some may now be used by the properly typed CloudWatch client. Not listed as remediation target. |

### doc-audit.md Findings

#### DRIFT

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| 1 | Gradio badge version | VERIFIED | `README.md:17` no longer shows a version-specific Gradio badge. Line 17 just says "Gradio". |
| 2 | Coverage threshold inconsistency | VERIFIED | CLAUDE.md, README, CONTRIBUTING all say 75%. |
| 3 | CLAUDE.md ETags description | VERIFIED | Description now matches code (ETags are implemented). |
| 4 | CLAUDE.md `@handle_gracefully` | VERIFIED | Reference removed. |
| 5 | Logger Lambda-only detail | VERIFIED | `CLAUDE.md:61` now says "Lambda environments only". |
| 6 | "8 image manipulation capabilities" count | VERIFIED | `CLAUDE.md:7` says "7 image generation capabilities". `README.md:31-38` lists exactly 7 items (no Health Monitoring). |
| 7 | `/health` endpoint claim | VERIFIED | `README.md:104` now says 'Use the "System Info" tab in the UI' instead of claiming a `/health` endpoint. |

#### GAPS

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| 1 | `lambda_helpers.py` undocumented | VERIFIED | `CLAUDE.md:62` documents it. |
| 2 | `types/common.py` undocumented | VERIFIED | `CLAUDE.md:64` documents it. |
| 3 | `validation.py` undocumented | VERIFIED | `CLAUDE.md:63` documents it. |

#### STALE

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| 1 | `@handle_gracefully` in CLAUDE.md | VERIFIED | Removed. |

#### CONFIG DRIFT

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| 1 | Undocumented fallback env vars (AWS_ID, AWS_SECRET) | VERIFIED | `.env.example:1` documents the fallback chain: "checked in this order: AMP_AWS_ID > AWS_ID > AWS_ACCESS_KEY_ID". |
| 2 | Undocumented Lambda env vars | VERIFIED | `.env.example:22-24` documents `AWS_LAMBDA_FUNCTION_NAME` and `AWS_LAMBDA_HTTP_PORT`. |
| 3 | Undocumented MINISTACK_URL | VERIFIED | `.env.example:27` documents `MINISTACK_URL`. |

### Remaining Items (Not Targeted for Remediation)

These findings from the health audit were not included in remediation targets and remain as-is:

- Health-audit #3: Async S3 storage fire-and-forget in Lambda (class-level executor)
- Health-audit #8: Unconditional S3 storage on every invocation
- Health-audit #9: Logger lock contention under concurrent requests
- Health-audit #10: Potentially unused TYPE_CHECKING imports
- Health-audit #11: `app.py` import-time side effects (Gradio UI construction)
- Health-audit #14: 300s Bedrock timeout behind API Gateway
- Health-audit #24: pygments CVE (dependency-level, not directly addressable)

Resolved during remediation (no longer outstanding):
- Health-audit #16: Per-call ThreadPoolExecutor in `image_variation` (removed in Phase 2)
- Health-audit #17: Unused methods in `lambda_helpers.py` (removed in Phase 1)
- Health-audit #20: `color_picker` not wired to handler (wired in Phase 1)
- Health-audit #21: `health_endpoint()` dead code (removed in Phase 1)
- Health-audit #22: `increment_error()` never called (removed in Phase 1)
- Health-audit #23: S3 key collision (fixed with UUID suffix in Phase 1)

### Verdict

All remediation targets from the consolidated plan are verified. Tests pass with no regressions (163/163, 81.72% coverage). Items not targeted for remediation are documented above as known technical debt.

**VERIFIED**

## Active Feedback

(No open items.)

## Resolved Feedback

### FB-6: Phase 4 Task 3 verification checklist contradicts implementation (leftover from FB-2 fix)

- **Source:** PLAN_REVIEW
- **Phase:** 4
- **Resolution:** Updated the Phase 4 Task 3 verification checklist to say "Dockerfile uses `uv sync --frozen --no-dev --no-editable` instead of `pip install`", matching the actual implementation in the Dockerfile template.

### FB-7: Phase 2 Task 2 verification checklist overclaims scope

- **Source:** PLAN_REVIEW
- **Phase:** 2
- **Resolution:** Chose option (a): scoped the checklist to match the actual task. The verification checklist now explicitly names the four singletons being converted (`bedrock_service`, `rate_limiter`, `health_checker`, `canvas_handlers`) and notes that `app_logger`, `_nsfw_cache`, and `lambda_image_handler` remain as module-level instances. Also updated the Phase Verification section and the commit message template to avoid overclaiming scope.

### FB-1: Phase-0 ADR-4 contradicts Phase-2 Task 5 implementation

- **Source:** PLAN_REVIEW
- **Phase:** 0, 2
- **Resolution:** Updated ADR-4 title and body to say "urllib.request" instead of "requests". Updated ADR-5 to remove the incorrect claim about requests being a transitive dependency. Rewrote Phase-2 Task 5 title and opening steps to remove the deliberation (requests vs urllib) and present only the final approach (urllib.request from stdlib).

### FB-2: Dockerfile uv.lock claim is incorrect (Phase 4 Task 3)

- **Source:** PLAN_REVIEW
- **Phase:** 4
- **Resolution:** Replaced `uv pip install --system -r requirements.txt` with `uv sync --frozen --no-dev --no-editable` in the Dockerfile template. Removed the incorrect claim about uv.lock being consulted by `uv pip install`. Added an explanatory note that `uv sync --frozen` is what actually reads the lock file. Removed `requirements.txt` from the COPY line since `uv sync` reads `pyproject.toml` + `uv.lock`.

### FB-3: Adding commit-lint to all-checks needs will break push CI (Phase 4 Task 4)

- **Source:** PLAN_REVIEW
- **Phase:** 4
- **Resolution:** Replaced the instruction to add `commit-lint` to `all-checks` needs with an explicit instruction NOT to add it. Added explanation that `commit-lint` runs independently as an advisory check because its `skipped` status on push events would fail the `!= "success"` check in `all-checks`. Updated the verification checklist accordingly.

### FB-4: Phase 2 Task 5 should remove pytest-asyncio from CI install

- **Source:** PLAN_REVIEW
- **Phase:** 4
- **Resolution:** Added step 7 to Phase 4 Task 1 (which already modifies ci.yml) instructing the implementer to remove `pytest-asyncio` from both CI install lines (lines 76 and 114) and from pyproject.toml dev dependencies. Added a verification checklist item for this.

### FB-5: Phase 5 Task 4 lists .markdownlint.yaml under "Files to Modify" but it is a new file

- **Source:** PLAN_REVIEW
- **Phase:** 5
- **Resolution:** Split Phase 5 Task 4 into separate "Files to Modify" (`.pre-commit-config.yaml`) and "Files to Create" (`.markdownlint.yaml`) sections. Added a "Files to Create" section to Phase 5 Task 5 for `.lychee.toml`.