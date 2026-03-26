# Phase 2: [IMPLEMENTER] Architecture and Performance Fixes

## Phase Goal

Fix the critical and high-severity architectural issues: module-level singleton instantiation, rate limiter race condition, NSFW cache memory issue, and the async/sync NSFW dance. These are the changes with the highest risk and impact.

**Success criteria:**
- Config no longer raises at import time; uses factory function
- AWSClientManager singleton can be reset between tests
- Rate limiter uses S3 conditional writes (ETags) to prevent race conditions
- NSFW cache uses lightweight hashing (not `image.tobytes()`)
- `aiohttp` dependency removed; NSFW check uses synchronous HTTP
- All existing tests pass; new tests cover changed behavior
- Coverage stays at or above 75%

**Estimated tokens:** ~25,000

## Prerequisites

- Phase 1 complete (dead code removed)
- Tests passing: `pytest tests/unit/ -v --tb=short`

## Tasks

### Task 1: Convert AppConfig to Factory Function

**Goal:** Replace the module-level `config = AppConfig()` instantiation with a lazy factory function. Config should be created on first access, not at import time. This fixes critical finding #2 (import-time side effects) and eval Architecture remediation target.

**Files to Modify:**
- `src/models/config.py` -- convert to factory pattern
- `tests/conftest.py` -- update config fixture

**Implementation Steps:**

1. In `src/models/config.py`, keep the `AppConfig` dataclass but change how env vars are read. Move `os.getenv` calls from field defaults into `__init__` (or `__post_init__`):

```python
@dataclass
class AppConfig:
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    # ... all fields with plain defaults ...

    def __post_init__(self):
        # Read env vars at instantiation time, not class definition time
        if not self.aws_access_key_id:
            self.aws_access_key_id = os.getenv(
                "AMP_AWS_ID", os.getenv("AWS_ID", os.getenv("AWS_ACCESS_KEY_ID", ""))
            )
        # ... same pattern for all env-var-backed fields ...
```

2. Replace the global `config = AppConfig()` with a lazy accessor:

```python
_config: AppConfig | None = None

def get_config() -> AppConfig:
    global _config
    if _config is None:
        load_dotenv()
        _config = AppConfig()
    return _config

def reset_config() -> None:
    """Reset config for testing. Not for production use."""
    global _config
    _config = None
```

3. Update every file that imports `config` from `src.models.config` to import and call `get_config()` instead. The affected files are:
   - `src/services/aws_client.py`
   - `src/services/rate_limiter.py`
   - `src/services/image_processor.py`
   - `src/handlers/canvas_handlers.py` (indirectly, via other modules)
   - `src/handlers/health.py`
   - `src/utils/logger.py`
   - `src/utils/lambda_helpers.py`
   - `app.py`

   In each file, replace `from src.models.config import config` with `from src.models.config import get_config` and replace `config.xxx` with `get_config().xxx`.

4. Remove the module-level `logging.basicConfig(...)` and `logger.info("Configuration loaded successfully")` from `config.py`. These are import-time side effects.

5. Update `tests/conftest.py`: call `reset_config()` in a session-scoped fixture or in the existing env var setup. The `os.environ.setdefault` calls at the top of `conftest.py` should still work, but add a fixture that calls `reset_config()` before tests if needed.

**Verification Checklist:**
- [x] `from src.models.config import config` no longer exists anywhere (replaced with `get_config()`)
- [x] Importing any `src` module does NOT trigger `AppConfig.__init__` or `__post_init__`
- [x] `ruff check src/ tests/` passes
- [x] `pytest tests/unit/ -v --tb=short` passes
- [x] Config validation still raises `ConfigurationError` when `get_config()` is first called without required env vars

**Testing Instructions:**
- Add a test in `tests/unit/` that imports a `src` module without env vars set and confirms no exception at import time
- Add a test that calls `get_config()` without required env vars and confirms `ConfigurationError` is raised
- Add a test that calls `reset_config()` and then `get_config()` with different env vars to confirm config is re-read

**Commit Message Template:**
```
refactor(config): convert module-level config to lazy factory function

- AppConfig reads env vars at instantiation, not class definition
- get_config() creates config on first access
- reset_config() enables clean test isolation
- Eliminates import-time side effects that broke test isolation
```

---

### Task 2: Add Reset Capability to AWSClientManager Singleton

**Goal:** Make the `AWSClientManager` singleton resettable for test isolation. Fix finding #6 (singleton stores clients at class level, impossible to reset between tests).

**Files to Modify:**
- `src/services/aws_client.py` -- add `_reset` classmethod
- `tests/unit/conftest.py` -- add fixture that resets between tests

**Implementation Steps:**

1. Add a `_reset` classmethod to `AWSClientManager`:

```python
@classmethod
def _reset(cls) -> None:
    """Reset singleton state for testing. Not for production use."""
    with cls._lock:
        if cls._executor is not None:
            cls._executor.shutdown(wait=False)
        cls._instance = None
        cls._bedrock_client = None
        cls._s3_client = None
        cls._logs_client = None
        cls._executor = None
```

2. In `tests/unit/conftest.py`, add an autouse fixture:

```python
@pytest.fixture(autouse=True)
def reset_aws_clients():
    """Reset AWS singleton between tests to prevent state leakage."""
    yield
    from src.services.aws_client import AWSClientManager
    AWSClientManager._reset()
```

3. Also remove the module-level `bedrock_service = BedrockService()` at the bottom of `aws_client.py`. Replace with a lazy accessor following the same pattern as config:

```python
_bedrock_service: BedrockService | None = None

def get_bedrock_service() -> BedrockService:
    global _bedrock_service
    if _bedrock_service is None:
        _bedrock_service = BedrockService()
    return _bedrock_service
```

4. Update imports in `canvas_handlers.py` to use `get_bedrock_service()` instead of `bedrock_service`.

5. Similarly, convert the module-level `rate_limiter = OptimizedRateLimiter()` in `rate_limiter.py` and `health_checker = HealthCheck()` in `health.py` to lazy accessors. Update their import sites in `app.py` and `canvas_handlers.py`.

6. Convert the module-level `canvas_handlers = CanvasHandlers(bedrock_service, rate_limiter)` in `canvas_handlers.py` to a lazy accessor. Update `app.py` accordingly.

**Verification Checklist:**
- [x] `AWSClientManager._reset()` method exists
- [x] No module-level singleton instantiation for `bedrock_service`, `rate_limiter`, `health_checker`, or `canvas_handlers` (converted to lazy `get_*()` accessors)
- [x] The converted globals use lazy accessor functions (`get_bedrock_service()`, `get_rate_limiter()`, `get_health_checker()`, `get_canvas_handlers()`)
- [x] Note: `app_logger`, `_nsfw_cache`, and `lambda_image_handler` remain as module-level instances (low-risk, addressed separately or acceptable as-is)
- [x] `ruff check src/ tests/` passes
- [x] `pytest tests/unit/ -v --tb=short` passes with no test pollution warnings

**Testing Instructions:**
- Verify that running the same test twice in a row produces identical results (no state leakage)
- Add a test that calls `_reset()` and confirms clients are `None` afterward
- Existing handler tests should still work via constructor injection

**Commit Message Template:**
```
refactor(aws-client): add singleton reset and convert globals to lazy accessors

- AWSClientManager._reset() enables test isolation
- Service singletons (bedrock, rate_limiter, health, handlers) replaced with lazy get_*() functions
- Eliminates import-time instantiation for core services
```

---

### Task 3: Fix Rate Limiter Race Condition with ETags

**Goal:** Replace the non-atomic GET-check-PUT in the rate limiter with ETag-based conditional writes. This fixes critical finding #1.

**Files to Modify:**
- `src/services/rate_limiter.py` -- add ETag handling to `_check_and_increment`

**Implementation Steps:**

1. Modify `_get_rate_data` to return the ETag along with the data:

```python
def _get_rate_data(self) -> tuple[RateLimitData, str]:
    """Get rate data and ETag from S3."""
    response = self.client_manager.s3_client.get_object(
        Bucket=get_config().nova_image_bucket,
        Key=self.S3_KEY,
    )
    etag = response.get("ETag", "")
    body = response["Body"].read().decode("utf-8")
    rate_data: RateLimitData = json.loads(body)
    # ... existing validation ...
    return rate_data, etag
```

2. Modify `_put_rate_data` to accept and use the ETag for conditional write:

```python
def _put_rate_data(self, rate_data: RateLimitData, etag: str) -> None:
    """Write rate data to S3 with optimistic locking."""
    kwargs: dict[str, Any] = {
        "Bucket": get_config().nova_image_bucket,
        "Key": self.S3_KEY,
        "Body": json.dumps(rate_data),
        "ContentType": "application/json",
    }
    if etag:
        kwargs["IfMatch"] = etag
    self.client_manager.s3_client.put_object(**kwargs)
```

3. Modify `_check_and_increment` to handle the conditional write failure:

```python
def _check_and_increment(self, quality: str) -> bool:
    cost = 2 if quality == "premium" else 1
    max_retries = 3

    for attempt in range(max_retries):
        try:
            rate_data, etag = self._get_rate_data()
            current_time = time.time()
            self._clean_old_entries(rate_data, current_time)
            total = self._calculate_total(rate_data)

            if total + cost > get_config().rate_limit:
                return False

            if quality == "premium":
                rate_data["premium"].append(current_time)
            else:
                rate_data["standard"].append(current_time)

            try:
                self._put_rate_data(rate_data, etag)
                return True
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "PreconditionFailed" and attempt < max_retries - 1:
                    app_logger.debug(f"Rate limit ETag conflict, retrying (attempt {attempt + 1})")
                    continue
                raise

        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                return self._initialize_rate_data(quality)
            app_logger.warning(f"Rate limit check failed: {e!s}")
            return True  # Fail open

    app_logger.warning("Rate limit check exhausted retries, allowing request")
    return True  # Fail open after max retries
```

4. Update `_initialize_rate_data` to not pass an ETag (first write).

5. Update `get_current_usage` to handle the new tuple return from `_get_rate_data` (just ignore the ETag).

**Verification Checklist:**
- [x] `_get_rate_data` returns `(data, etag)` tuple
- [x] `_put_rate_data` sends `IfMatch` header when ETag is available
- [x] `_check_and_increment` retries on `PreconditionFailed`
- [x] `ruff check src/services/rate_limiter.py` passes
- [x] `pytest tests/unit/test_rate_limiter.py -v` passes

**Testing Instructions:**
- Update existing rate limiter tests to account for tuple return from `_get_rate_data`
- Add a test that simulates `PreconditionFailed` on first attempt and success on retry
- Add a test that simulates `PreconditionFailed` exhausting all retries (should fail open)
- Add a test confirming `IfMatch` is passed in the `put_object` call

**Commit Message Template:**
```
fix(rate-limiter): add ETag-based optimistic locking to prevent race condition

- GET returns ETag, PUT uses IfMatch for conditional write
- Retries up to 3 times on PreconditionFailed
- Fails open after exhausting retries (demo app behavior preserved)
```

---

### Task 4: Fix NSFW Cache Memory Issue

**Goal:** Replace `image.tobytes()` SHA-256 hashing with a lightweight key based on image dimensions, mode, and a sample of pixel data. This fixes finding #7 (16MB allocation per hash).

**Files to Modify:**
- `src/services/image_processor.py` -- rewrite `_NSFWCache` hash method

**Implementation Steps:**

1. Replace the hash computation in `_NSFWCache`. Instead of `image.tobytes()`, use a composite key:

```python
def _compute_key(self, image: Image.Image) -> str:
    """Compute a lightweight cache key from image metadata and pixel sample."""
    # Include dimensions and mode for uniqueness
    header = f"{image.size[0]}x{image.size[1]}:{image.mode}"

    # Sample a small number of pixels for content fingerprinting
    # Resize to 32x32 thumbnail for consistent, small hash input
    thumb = image.copy()
    thumb.thumbnail((32, 32))
    pixel_data = thumb.tobytes()

    return hashlib.sha256(f"{header}:{pixel_data.hex()}".encode()).hexdigest()
```

2. Update `get` and `put` to use `_compute_key`:

```python
def get(self, image: Image.Image) -> bool | None:
    return self._cache.get(self._compute_key(image))

def put(self, image: Image.Image, is_nsfw: bool) -> None:
    if len(self._cache) >= self._max_size:
        del self._cache[next(iter(self._cache))]
    self._cache[self._compute_key(image)] = is_nsfw
```

3. The thumbnail approach uses ~3KB instead of ~16MB for a 2048x2048 image. The collision risk is negligible for a 128-entry cache on a demo app.

**Verification Checklist:**
- [x] `image.tobytes()` no longer called on full-size images in `_NSFWCache`
- [x] Cache still produces consistent keys for the same image
- [x] `ruff check src/services/image_processor.py` passes
- [x] `pytest tests/unit/test_image_processor.py -v` passes

**Testing Instructions:**
- Add a test that verifies cache hit: process same image twice, confirm second call returns cached value
- Add a test with a large image (2048x2048) to verify no excessive memory allocation
- Existing NSFW tests should pass

**Commit Message Template:**
```
fix(image-processor): use thumbnail-based hashing for NSFW cache

- Replaces image.tobytes() (16MB for 2048x2048) with 32x32 thumbnail hash
- Reduces per-lookup memory from ~16MB to ~3KB
- Cache key includes dimensions, mode, and pixel sample
```

---

### Task 5: Replace aiohttp NSFW Check with Synchronous urllib.request

**Goal:** Remove the fragile `asyncio.run()` / `new_event_loop()` pattern and replace `aiohttp` with synchronous `urllib.request` (stdlib) for the NSFW check. This fixes finding #5 and simplifies the dependency tree. See ADR-4 in Phase-0.

**Files to Modify:**
- `src/services/image_processor.py` -- rewrite NSFW check methods
- `pyproject.toml` -- remove `aiohttp` from dependencies
- `requirements.txt` -- remove `aiohttp`

**Implementation Steps:**

1. Replace `check_nsfw_async` and `check_nsfw_sync` with a single synchronous method using `urllib.request` from the standard library (no new dependency needed):

```python
import urllib.request
import urllib.error

def check_nsfw(self) -> bool:
    """Check image for NSFW content via HuggingFace API."""
    if not get_config().enable_nsfw_check or not get_config().hf_token:
        app_logger.debug("NSFW check skipped (disabled or no token)")
        return False

    timeout = get_config().nsfw_timeout
    max_retries = get_config().nsfw_max_retries

    temp_buffer = io.BytesIO()
    self.image.save(temp_buffer, format="PNG")
    image_data = temp_buffer.getvalue()

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                get_config().nsfw_api_url,
                data=image_data,
                headers={
                    "Authorization": f"Bearer {get_config().hf_token}",
                    "Content-Type": "application/octet-stream",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read())
                nsfw_score = next(
                    (item["score"] for item in result if item["label"] == "nsfw"), 0
                )
                app_logger.debug(f"NSFW Score: {nsfw_score}")
                return nsfw_score > 0.5

        except urllib.error.HTTPError as e:
            if e.code == 503 and attempt < max_retries - 1:
                retry_after = int(e.headers.get("Retry-After", 5))
                app_logger.warning(f"NSFW API unavailable, retry in {retry_after}s")
                time.sleep(retry_after)
                continue
            app_logger.warning(f"NSFW API error: {e}")
        except Exception as e:
            app_logger.warning(f"NSFW check error (attempt {attempt + 1}/{max_retries}): {e!s}")

        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    app_logger.warning("NSFW check failed after all retries, continuing without check")
    return False
```

3. Update `process()` method to call `self.check_nsfw()` instead of `self.check_nsfw_sync()`.

4. Remove the `import asyncio` and `import aiohttp` lines.

5. Add `import json`, `import time`, `import urllib.request`, `import urllib.error` if not already imported.

6. Remove `aiohttp` from `pyproject.toml` dependencies list and from `requirements.txt`.

7. Remove `pytest-asyncio` from dev dependencies if no other async tests exist. Check first.

**Verification Checklist:**
- [x] `asyncio` not imported in `image_processor.py`
- [x] `aiohttp` not imported anywhere in `src/`
- [x] `aiohttp` removed from `pyproject.toml` and `requirements.txt`
- [x] `ruff check src/services/image_processor.py` passes
- [x] `pytest tests/unit/test_image_processor.py -v` passes

**Testing Instructions:**
- Update NSFW-related tests to mock `urllib.request.urlopen` instead of `aiohttp`
- Add a test that verifies NSFW check skips when `enable_nsfw_check` is False
- Add a test that simulates 503 retry behavior
- Remove any `@pytest.mark.asyncio` markers from NSFW tests

**Commit Message Template:**
```
refactor(image-processor): replace aiohttp NSFW check with synchronous urllib

- Eliminates fragile asyncio.run() / new_event_loop() pattern
- Uses urllib.request from stdlib (no new dependency)
- Removes aiohttp runtime dependency
```

---

### Task 6: Remove Per-Call ThreadPoolExecutor in image_variation

**Goal:** Fix finding #16 (thread churn). The `image_variation` handler creates a new `ThreadPoolExecutor` per call. Reuse the executor from `AWSClientManager` or use a module-level pool.

**Files to Modify:**
- `src/handlers/canvas_handlers.py` -- remove per-call ThreadPoolExecutor

**Implementation Steps:**

1. In `image_variation`, replace:
```python
with ThreadPoolExecutor(max_workers=min(len(images), 5)) as pool:
    encoded_images = list(pool.map(process_and_encode_image, images))
```
with a simple list comprehension (the image encoding is CPU-bound, not I/O-bound, so threading provides minimal benefit and adds overhead):
```python
encoded_images = [process_and_encode_image(img) for img in images]
```

2. If there is concern about latency with multiple images (up to 5), the existing `AWSClientManager` executor could be used, but given that image encoding is CPU-bound and Python's GIL limits threading benefit for CPU work, a simple loop is more appropriate.

3. Remove the `ThreadPoolExecutor` import from `canvas_handlers.py` if no longer used.
4. Remove the `concurrent.futures` import if unused.

**Verification Checklist:**
- [x] No `ThreadPoolExecutor` created per call in `image_variation`
- [x] `ruff check src/handlers/canvas_handlers.py` passes
- [x] `pytest tests/unit/test_canvas_handlers.py -v` passes

**Testing Instructions:**
- Existing image variation tests should pass unchanged
- No new tests needed

**Commit Message Template:**
```
refactor(handlers): remove per-call ThreadPoolExecutor from image_variation

- Image encoding is CPU-bound, threading adds overhead without benefit
- Simple list comprehension replaces thread pool
```

## Phase Verification

After completing all tasks:

1. `ruff check src/ tests/ && ruff format --check src/ tests/`
2. `pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=75 -m "not integration"`
3. `mypy src/ --ignore-missing-imports --no-strict-optional --allow-untyped-defs`
4. Verify `bedrock_service`, `rate_limiter`, `health_checker`, and `canvas_handlers` are no longer instantiated at module level in `src/`
5. Verify `aiohttp` is not in dependencies

**Known limitations:**
- The `app.py` module-level Gradio UI construction (finding #11) is not addressed. Moving the `gr.Blocks` context into a function would require significant refactoring of how Gradio components are wired. This is acceptable for a demo app.
- The `log_performance` decorator is applied broadly (finding from eval). Threshold-based logging is deferred as low priority.
- The fire-and-forget S3 storage pattern (finding #3) is not addressed. Proper fix requires architectural decisions about whether to make storage synchronous or add dead-letter handling, which is out of scope for a demo app.
