# Phase 1: [HYGIENIST] Dead Code Removal and Quick Wins

## Phase Goal

Remove dead code, unused imports, and fix trivial bugs that require no architectural changes. This is purely subtractive work with minor wiring fixes.

**Success criteria:**
- All vulture-flagged dead code removed or justified
- Quick wins from health audit resolved
- All existing tests still pass
- No new functionality added

**Estimated tokens:** ~12,000

## Prerequisites

- Phase 0 read and understood
- Dev environment set up: `uv pip install --system -r requirements.txt && uv pip install --system -e ".[dev]"`
- Tests pass before starting: `pytest tests/unit/ -v --tb=short`

## Tasks

### Task 1: Delete Unused Methods in lambda_helpers.py

**Goal:** Remove `process_image_for_lambda` and `create_data_url` from `LambdaImageHandler`. Both are confirmed unused by vulture at 90% confidence. Only `cleanup_temp_files` is called (from `app.py`).

**Files to Modify:**
- `src/utils/lambda_helpers.py` -- delete `process_image_for_lambda` and `create_data_url` methods
- `tests/unit/test_lambda_helpers.py` -- remove any tests for deleted methods

**Implementation Steps:**
1. Read `src/utils/lambda_helpers.py` and confirm the two methods are not referenced anywhere else. Search for `process_image_for_lambda` and `create_data_url` across the entire `src/` and `tests/` directories.
2. Delete the `process_image_for_lambda` method (lines 18-71).
3. Delete the `create_data_url` method (lines 73-120).
4. Remove unused imports that were only needed by deleted methods (`base64`, `io`, `uuid`). Keep `time` and `Path` (needed by `cleanup_temp_files`).
5. Remove the `Image` import from PIL if it is no longer used after the deletions.
6. Update `tests/unit/test_lambda_helpers.py` to remove tests for deleted methods. If no tests remain for this module, delete the test file.

**Verification Checklist:**
- [x] `process_image_for_lambda` does not appear anywhere in `src/` or `tests/`
- [x] `create_data_url` does not appear anywhere in `src/` or `tests/`
- [x] `ruff check src/utils/lambda_helpers.py` passes
- [x] `pytest tests/unit/ -v --tb=short` passes

**Testing Instructions:**
- Run existing tests to confirm nothing breaks
- No new tests needed (removing dead code)

**Commit Message Template:**
```text
refactor(lambda-helpers): remove unused process_image_for_lambda and create_data_url

- Both methods flagged as dead code by vulture (90% confidence)
- Neither called anywhere in the codebase
- Reduces maintenance surface
```

---

### Task 2: Remove Unused TYPE_CHECKING Imports in aws_client.py

**Goal:** Clean up TYPE_CHECKING imports that are never used in type annotations within `aws_client.py`. The health audit (finding #10) identified `CloudWatchLogsClient` and `S3Client` as potentially unused, along with several Bedrock type imports.

**Files to Modify:**
- `src/services/aws_client.py` -- prune unused TYPE_CHECKING imports

**Implementation Steps:**
1. Read `src/services/aws_client.py` and check which TYPE_CHECKING imports are actually used in type annotations in this file.
2. Search for each imported name: `BedrockRuntimeClient`, `ConverseResponseTypeDef`, `InvokeModelResponseTypeDef`, `MessageTypeDef`, `CloudWatchLogsClient`, `S3Client`.
3. The property return types use string annotations (e.g., `-> "BedrockRuntimeClient"`). These DO reference the TYPE_CHECKING imports, so they are used. Verify each one:
   - `BedrockRuntimeClient` -- used in `bedrock_client` property return type
   - `S3Client` -- used in `s3_client` property return type
   - `CloudWatchLogsClient` -- used in `logs_client` property return type
   - `InvokeModelResponseTypeDef` -- used in `_process_image_response` parameter type
   - `ConverseResponseTypeDef` -- used in `_process_text_response` parameter type
   - `MessageTypeDef` -- used in `generate_prompt` cast
4. Remove only the imports that are genuinely unreferenced after verification. If all are used, document that finding and skip this task.

**Verification Checklist:**
- [x] No unused imports remain under `TYPE_CHECKING` (all 6 imports verified as used in type annotations)
- [x] `ruff check src/services/aws_client.py` passes
- [x] `mypy src/services/aws_client.py --ignore-missing-imports --no-strict-optional --allow-untyped-defs` passes
- [x] `pytest tests/unit/test_aws_client.py -v` passes

**Testing Instructions:**
- No new tests needed
- Existing tests confirm no runtime breakage

**Commit Message Template:**
```text
refactor(aws-client): remove unused TYPE_CHECKING imports

- Pruned imports not referenced in type annotations
- Confirmed remaining imports are used in property return types and method signatures
```

---

### Task 3: Fix seeds.json Relative Path

**Goal:** Fix `Path("seeds.json").open()` in `canvas_handlers.py` to use an absolute path relative to the module file. This is a quick win from the health audit (finding #4) and affects reliability in Lambda where CWD may differ.

**Files to Modify:**
- `src/handlers/canvas_handlers.py` -- fix the path in `generate_nova_prompt`

**Implementation Steps:**
1. In `generate_nova_prompt` (around line 475), replace `Path("seeds.json")` with `Path(__file__).resolve().parent.parent.parent / "seeds.json"`. This resolves to the project root regardless of CWD.
   - `__file__` is `src/handlers/canvas_handlers.py`
   - `.parent` = `src/handlers/`
   - `.parent` = `src/`
   - `.parent` = project root
2. Verify the path resolves correctly by checking that `seeds.json` exists at the project root.

**Verification Checklist:**
- [x] `seeds.json` path is absolute (uses `__file__` as anchor)
- [x] `ruff check src/handlers/canvas_handlers.py` passes
- [x] `pytest tests/unit/test_canvas_handlers.py -v` passes

**Testing Instructions:**
- If a test exists for `generate_nova_prompt`, confirm it still passes
- Consider adding a test that verifies the path resolves to an existing file (optional, low priority)

**Commit Message Template:**
```text
fix(handlers): resolve seeds.json path relative to module file

- Prevents FileNotFoundError when CWD differs from project root
- Uses __file__ as anchor for reliable resolution in Lambda
```

---

### Task 4: Fix or Remove Dead health_endpoint Function

**Goal:** The `health_endpoint()` function in `app.py` (line 362-365) is defined but never registered as a route. Either wire it up as a Gradio API route or delete it. Given that health status is already accessible via the System Info tab, delete it.

**Files to Modify:**
- `app.py` -- delete `health_endpoint` function and its comment

**Implementation Steps:**
1. Delete the `health_endpoint` function (lines 361-365) and the comment above it.
2. Verify that `health_checker.increment_request()` is not called anywhere else. If `increment_request` is only called from `health_endpoint`, note this for a later task (wiring error counting in Phase 3).

**Verification Checklist:**
- [x] `health_endpoint` does not appear in `app.py`
- [x] `ruff check app.py` passes
- [x] Application still launches (no import errors)

**Testing Instructions:**
- No tests needed (removing dead code)

**Commit Message Template:**
```text
refactor(app): remove dead health_endpoint function

- Function was never registered as a route
- Health status accessible via System Info tab
```

---

### Task 5: Fix or Remove Unwired color_picker Component

**Goal:** The `color_picker` Gradio component (app.py line 293) is visible in the UI but its value is never passed to any handler. Wire it to append its value to the `colors` textbox, or remove it.

**Files to Modify:**
- `app.py` -- wire `color_picker` to the `colors` textbox

**Implementation Steps:**
1. The `color_picker` should append its selected color to the `colors` textbox. Add a `.change()` event handler on `color_picker` that appends the selected hex color to the `colors` textbox value.
2. Create a small helper function (or use a lambda) that takes the current `colors` text and the new color, and returns the updated comma-separated string. Example:

```python
def append_color(current_colors: str, new_color: str) -> str:
    if not current_colors or not current_colors.strip():
        return new_color
    return f"{current_colors},{new_color}"
```

3. Wire it: `color_picker.change(append_color, inputs=[colors, color_picker], outputs=colors)`

**Verification Checklist:**
- [x] `color_picker.change(...)` event is registered
- [x] `ruff check app.py` passes
- [x] Application launches without error

**Testing Instructions:**
- Manual verification: launch app, pick a color, confirm it appears in the colors textbox
- No automated test needed for UI wiring

**Commit Message Template:**
```text
fix(app): wire color_picker to colors textbox in Color Guided tab

- ColorPicker change event now appends selected color to the colors input
- Previously the component was visible but had no effect
```

---

### Task 6: Add UUID Suffix to S3 Storage Keys

**Goal:** Fix S3 key collision risk (health audit finding #23) by appending a UUID suffix to the timestamp-based key in `_store_response_sync`.

**Files to Modify:**
- `src/services/aws_client.py` -- modify `_store_response_sync` method

**Implementation Steps:**
1. Add `import uuid` at the top of the file (with the other stdlib imports).
2. In `_store_response_sync`, change the key generation from:
   ```python
   timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
   ```
   to:
   ```python
   timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
   unique_id = uuid.uuid4().hex[:8]
   ```
3. Update the S3 keys to include the unique suffix:
   ```python
   response_key = f"responses/{timestamp}_{unique_id}_response.json"
   image_key = f"images/{timestamp}_{unique_id}_image.png"
   ```

**Verification Checklist:**
- [x] S3 keys include UUID suffix
- [x] `ruff check src/services/aws_client.py` passes
- [x] `pytest tests/unit/test_aws_client.py -v` passes

**Testing Instructions:**
- Existing tests should pass (mocked S3 calls)
- No new tests needed for key format

**Commit Message Template:**
```text
fix(aws-client): add UUID suffix to S3 storage keys

- Prevents key collisions under concurrent Lambda invocations
- Timestamp alone was insufficient for uniqueness
```

---

### Task 7: Delete or Wire increment_error in HealthCheck

**Goal:** `increment_error()` in `health.py` is defined but never called, making the error rate metric always 0%. For now, delete the method and the `error_count` field. Error tracking will be added properly in Phase 3 when request tracing is introduced.

**Files to Modify:**
- `src/handlers/health.py` -- remove `increment_error` method and `error_count` field
- `tests/unit/test_health.py` -- remove tests for `increment_error` if any

**Implementation Steps:**
1. In `HealthCheck.__init__`, remove `self.error_count = 0`.
2. Delete the `increment_error` method.
3. In `get_health_status`, change the error rate check (line 64) to remove the `error_count` reference. Since we are removing error tracking for now, remove the unhealthy status check based on error rate entirely. The method should only check service status for degraded state.
4. In `_get_metrics`, remove `total_errors` and `error_rate` from the returned dict.
5. Update `src/types/common.py` `MetricsInfo` TypedDict to remove `total_errors` and `error_rate` fields, or make them `NotRequired`.
6. Check `tests/unit/test_health.py` for any tests that reference `error_count` or `increment_error` and update accordingly.

**Verification Checklist:**
- [x] `increment_error` does not appear in `src/`
- [x] `error_count` field removed from `HealthCheck`
- [x] `ruff check src/handlers/health.py` passes
- [x] `pytest tests/unit/test_health.py -v` passes

**Testing Instructions:**
- Run existing health tests to confirm they pass after removal
- Verify `get_health_status` still returns valid structure

**Commit Message Template:**
```text
refactor(health): remove unused increment_error and error_count

- increment_error was never called, making error rate always 0%
- Error tracking will be reintroduced with request tracing in a later phase
```

## Phase Verification

After completing all tasks:

1. Run full lint: `ruff check src/ tests/ && ruff format --check src/ tests/`
2. Run full test suite: `pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=75 -m "not integration"`
3. Run type check: `mypy src/ --ignore-missing-imports --no-strict-optional --allow-untyped-defs`
4. Verify no dead code references remain for deleted items

**Known limitations:** This phase does not address the module-level singleton instantiation (Phase 2), the rate limiter race condition (Phase 2), or documentation drift (Phase 5).
