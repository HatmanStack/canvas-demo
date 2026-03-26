# Phase 3: [IMPLEMENTER] Defensiveness, Error Handling, and Observability

## Phase Goal

Improve defensiveness (currently 6/10) by adding request tracing, fixing error information leaks, hardening the logger, and fixing naive datetime usage across the codebase.

**Success criteria:**
- Request IDs generated at handler level and threaded through log calls
- `_process_response` no longer leaks internal error details
- Logger validates level parameter
- All `datetime.now()` calls use `timezone.utc`
- `_build_request` has KeyError guard for invalid task types
- Rate limiter logs structured warning on fail-open
- All tests pass with 75%+ coverage

**Estimated tokens:** ~18,000

## Prerequisites

- Phase 2 complete (lazy config, singleton reset, ETag rate limiter)
- Tests passing: `pytest tests/unit/ -v --tb=short`

## Tasks

### Task 1: Add Request ID Generation and Propagation

**Goal:** Add request traceability (eval finding: zero correlation IDs). Generate a request ID in the `gradio_handler` decorator and pass it through log calls.

**Files to Modify:**
- `src/handlers/canvas_handlers.py` -- generate request ID in `gradio_handler`
- `src/utils/logger.py` -- accept optional `request_id` in log methods

**Implementation Steps:**

1. In `src/utils/logger.py`, update the `log` method to accept an optional `request_id` parameter:

```python
def log(self, message: str, level: str = "INFO", request_id: str = "") -> None:
    prefix = f"[{request_id}] " if request_id else ""
    getattr(self.logger, level.lower())(f"{prefix}{message}")
    # ... rest of CloudWatch batching with prefix ...
```

Also update convenience methods (`debug`, `info`, `warning`, `error`) to accept and pass through `request_id`.

2. In `src/handlers/canvas_handlers.py`, modify `gradio_handler` to generate a request ID:

```python
import uuid

def gradio_handler(operation: str) -> Callable[..., Any]:
    def decorator(func: Callable[..., GradioImageResult]) -> Callable[..., GradioImageResult]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> GradioImageResult:
            request_id = uuid.uuid4().hex[:12]
            app_logger.info(f"Starting {operation}", request_id=request_id)
            try:
                result = func(*args, **kwargs)
                app_logger.info(f"Completed {operation}", request_id=request_id)
                return result
            except (ImageError, NSFWError, RateLimitError) as e:
                app_logger.warning(f"{operation}: {e.message}", request_id=request_id)
                return None, gr.update(visible=True, value=e.message)
            except ValidationError as e:
                app_logger.warning(f"{operation}: {e}", request_id=request_id)
                return None, gr.update(visible=True, value=str(e))
            except Exception as e:
                app_logger.error(f"{operation} error: {e!s}", request_id=request_id)
                return None, gr.update(visible=True, value=f"{operation} failed. Please try again.")
        return wrapper
    return decorator
```

3. This approach threads request IDs through the error boundary without requiring changes to every handler method's signature. Internal service calls (Bedrock, rate limiter) will not have request IDs in this phase, which is acceptable as a first step.

**Verification Checklist:**
- [x] `gradio_handler` generates a unique ID per request
- [x] Log messages from handler calls include `[request_id]` prefix
- [x] `ruff check src/handlers/canvas_handlers.py src/utils/logger.py` passes
- [x] `pytest tests/unit/ -v --tb=short` passes

**Testing Instructions:**
- Add a test that invokes a handler and verifies the logger was called with a non-empty request_id
- Verify request ID appears in log output by capturing log messages

**Commit Message Template:**
```
feat(handlers): add request ID generation in gradio_handler

- Each handler call gets a unique 12-char hex request ID
- Request ID prefixed to log messages for traceability
- Logger accepts optional request_id parameter
```

---

### Task 2: Fix Error Information Leak in _process_response

**Goal:** Fix finding #12. `_process_response` returns raw exception messages to users via `f"Failed to process image: {e!s}"`. Replace with generic message.

**Files to Modify:**
- `src/handlers/canvas_handlers.py` -- sanitize error in `_process_response`

**Implementation Steps:**

1. In `_process_response`, change the exception handler:

```python
def _process_response(self, result: bytes) -> GradioImageResult:
    app_logger.info(f"Processing image bytes: {len(result)} bytes")
    try:
        image = Image.open(io.BytesIO(result))
        app_logger.info(f"Created PIL Image: {image.size}, mode: {image.mode}")
        return image, gr.update(value=None, visible=False)
    except Exception as e:
        app_logger.error(f"Failed to process image bytes: {e!s}")
        return None, gr.update(
            visible=True,
            value="Failed to process the generated image. Please try again.",
        )
```

2. The internal error details are still logged (for debugging) but not returned to the user.

**Verification Checklist:**
- [x] User-facing error message does not contain `{e!s}` or exception details
- [x] Error details are still logged via `app_logger.error`
- [x] `pytest tests/unit/test_canvas_handlers.py -v` passes

**Testing Instructions:**
- Update any test that asserts on the old error message format
- Add a test that triggers `_process_response` with invalid bytes and confirms the generic error message is returned

**Commit Message Template:**
```
fix(handlers): sanitize error messages in _process_response

- User-facing errors no longer contain internal exception details
- Full error still logged for debugging
```

---

### Task 3: Validate Logger Level Parameter

**Goal:** Fix eval concern. `logger.log()` uses `getattr(self.logger, level.lower())` which throws `AttributeError` if `level` is not a valid log level.

**Files to Modify:**
- `src/utils/logger.py` -- validate `level` parameter

**Implementation Steps:**

1. Add a set of valid levels and validate in the `log` method:

```python
_VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

def log(self, message: str, level: str = "INFO", request_id: str = "") -> None:
    if level.upper() not in self._VALID_LEVELS:
        level = "INFO"
    prefix = f"[{request_id}] " if request_id else ""
    getattr(self.logger, level.lower())(f"{prefix}{message}")
    # ... rest unchanged ...
```

**Verification Checklist:**
- [x] Invalid log level falls back to INFO instead of raising AttributeError
- [x] `ruff check src/utils/logger.py` passes
- [x] `pytest tests/unit/ -v --tb=short` passes

**Testing Instructions:**
- Add a test that calls `app_logger.log("test", level="INVALID")` and confirms no exception is raised

**Commit Message Template:**
```
fix(logger): validate log level parameter against known set

- Invalid levels fall back to INFO instead of raising AttributeError
```

---

### Task 4: Fix Naive datetime.now() Across Codebase

**Goal:** Fix all `datetime.now()` calls to use `datetime.now(tz=timezone.utc)`. Affects `aws_client.py`, `health.py`, and `logger.py` (finding #15, eval Performance remediation).

**Files to Modify:**
- `src/services/aws_client.py` -- `_store_response_sync`
- `src/handlers/health.py` -- `get_health_status`, `get_simple_status`
- `src/utils/logger.py` -- `log` method

**Implementation Steps:**

1. In each file, add `from datetime import timezone` (or use `datetime.UTC` on Python 3.11+, which is `datetime.timezone.utc`).

2. Replace every `datetime.now()` with `datetime.now(tz=timezone.utc)`:
   - `aws_client.py` line 326: `datetime.now(tz=timezone.utc).strftime(...)`
   - `health.py` line 41: `datetime.now(tz=timezone.utc).isoformat()`
   - `health.py` line 193: `datetime.now(tz=timezone.utc).isoformat()`
   - `logger.py` line 73: `datetime.now(tz=timezone.utc)`

**Verification Checklist:**
- [x] No `datetime.now()` without `tz=` in `src/`
- [x] Search for `datetime.now()` returns zero results in `src/`
- [x] `ruff check src/` passes
- [x] `pytest tests/unit/ -v --tb=short` passes

**Testing Instructions:**
- No new tests needed (existing tests use mocks that don't depend on timezone)
- Optionally: add a test that verifies timestamps in health status have timezone info

**Commit Message Template:**
```
fix: use timezone-aware datetime.now(tz=timezone.utc) across codebase

- Eliminates implicit UTC dependency
- Prevents timestamp inconsistency in non-UTC environments
- Affects aws_client.py, health.py, logger.py
```

---

### Task 5: Add KeyError Guard to _build_request

**Goal:** Fix eval Code Quality finding. `_build_request` uses `param_dict[task_type]` without handling invalid task types.

**Files to Modify:**
- `src/handlers/canvas_handlers.py` -- add validation in `_build_request`

**Implementation Steps:**

1. Add a guard at the start of `_build_request`:

```python
def _build_request(self, task_type: TaskType, params: dict[str, Any], ...) -> str:
    param_dict = { ... }

    if task_type not in param_dict:
        raise ValueError(f"Unknown task type: {task_type}")

    request_body = { ... }
```

2. Since `task_type` is already typed as `TaskType` (a `Literal`), this guard catches runtime misuse from untyped callers.

**Verification Checklist:**
- [x] Invalid task type raises `ValueError` with descriptive message
- [x] `ruff check src/handlers/canvas_handlers.py` passes
- [x] `pytest tests/unit/test_canvas_handlers.py -v` passes

**Testing Instructions:**
- Add a test that calls `_build_request` with an invalid task type and confirms `ValueError` is raised

**Commit Message Template:**
```
fix(handlers): add KeyError guard to _build_request for invalid task types

- Raises ValueError with descriptive message instead of KeyError
```

---

### Task 6: Add Structured Logging on Rate Limiter Fail-Open

**Goal:** Fix eval Defensiveness finding. When rate limiter fails open, log a structured warning with context (not just a generic message).

**Files to Modify:**
- `src/services/rate_limiter.py` -- improve fail-open logging

**Implementation Steps:**

1. In `check_rate_limit`, the generic fail-open path (lines 66-68):

```python
except Exception as e:
    app_logger.error(f"Rate limiting error: {e!s}")
    app_logger.warning("Rate limit check failed, allowing request (fail-open)")
```

Change to include the exception type and whether it was a transient or persistent error:

```python
except Exception as e:
    app_logger.error(
        f"Rate limiter fail-open: {type(e).__name__}: {e!s}. "
        "Request allowed despite rate limit check failure."
    )
```

2. Similarly in `_check_and_increment` line 104:

```python
app_logger.warning(
    f"Rate limit S3 error (fail-open): {e.response.get('Error', {}).get('Code', 'unknown')}. "
    "Request allowed."
)
```

**Verification Checklist:**
- [x] Fail-open log messages include exception type and context
- [x] `ruff check src/services/rate_limiter.py` passes
- [x] `pytest tests/unit/test_rate_limiter.py -v` passes

**Testing Instructions:**
- Existing fail-open tests should pass (just log message content changes)

**Commit Message Template:**
```
fix(rate-limiter): add structured logging on fail-open events

- Log messages include exception type and error code
- Improves operational visibility when rate limiting degrades
```

## Phase Verification

After completing all tasks:

1. `ruff check src/ tests/ && ruff format --check src/ tests/`
2. `pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=75 -m "not integration"`
3. `mypy src/ --ignore-missing-imports --no-strict-optional --allow-untyped-defs`
4. Verify: `grep -r "datetime.now()" src/` returns zero results (all should use `tz=`)
5. Verify: log messages from handler calls include request IDs

**Known limitations:**
- Request IDs are not propagated into service-layer calls (Bedrock, S3 storage). Full distributed tracing would require passing context through method parameters, which is a larger refactor.
- The `__del__` finalizer in `OptimizedLogger` is still unreliable (Python GC limitation). This is a known issue that does not warrant a fix for a demo app.
