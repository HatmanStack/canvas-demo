---
type: doc-health
date: 2026-03-25
prevention_scope: markdownlint + lychee
language_stack: both
---

# Documentation Audit: canvas-demo

## Configuration
- **Prevention Scope:** Markdown linting (markdownlint) + link checking (lychee)
- **CI Platform:** GitHub Actions
- **Language Stack:** Both JS/TS and Python
- **Constraints:** None

## Summary
- Docs scanned: 4 files (README.md, CONTRIBUTING.md, CLAUDE.md, .env.example)
- Code modules scanned: 12 (app.py + 11 src/ modules)
- Findings: 7 drift, 3 gaps, 1 stale, 0 broken links, 3 config drift

## Findings

### DRIFT (doc exists, does not match code)

1. **`README.md:17`** -- Gradio badge says "Gradio 5.6.0"
   - Installed version: `6.5.1`
   - `requirements.txt` pins no version (just `gradio`), so the badge is stale relative to both the pinned spec and the actual install.

2. **`README.md:95`** -- `make test-cov` documented as "75% minimum"
   **`CONTRIBUTING.md:45`** -- "75% coverage minimum"
   **`CLAUDE.md:67`** -- "50% minimum (`--cov-fail-under=50`)"
   - `Makefile:24` uses `--cov-fail-under=75`
   - `ci.yml:82` uses `--cov-fail-under=75`
   - `pyproject.toml:116` has `fail_under = 75`
   - CLAUDE.md's claim of 50% contradicts all three authoritative sources. README and CONTRIBUTING are correct at 75%.

3. **`CLAUDE.md:51`** -- Describes `services/rate_limiter.py` as "using ETags for optimistic locking"
   - Code reality: `rate_limiter.py` uses simple GET/PUT with no ETag-based conditional writes. The class docstring itself says "Uses simple GET -> check -> PUT." Zero references to ETags anywhere in the file.

4. **`CLAUDE.md:54`** -- Describes `utils/exceptions.py` as containing a `@handle_gracefully` decorator
   - Code reality: `exceptions.py` contains only exception classes. The `@handle_gracefully` decorator was deleted. `canvas_handlers.py:53` explicitly notes "Unlike the deleted handle_gracefully." The replacement is `@gradio_handler` in `canvas_handlers.py`.

5. **`CLAUDE.md:55`** -- Describes `utils/logger.py` as "CloudWatch log batching (10 logs or 30s intervals)"
   - Code reality: The numbers are correct, but the CLAUDE.md omits that this only activates in Lambda environments (`config.is_lambda`), which is a meaningful operational detail.

6. **`README.md:31-39`** -- Lists "8 image manipulation capabilities" in the overview, then lists 8 bullet items including "Health Monitoring"
   - Health Monitoring is not an image manipulation capability. The actual image manipulation count is 7 (text-to-image, inpainting, outpainting, variation, conditioning, color-guided, background removal). The Gradio UI has 7 image tabs plus 1 System Info tab.
   - CLAUDE.md:7 also says "8 image manipulation capabilities" and then parenthetically lists only 7.

7. **`README.md:104`** -- Claims `/health` endpoint exists: "Access `/health` for health status"
   - Code reality: `app.py` defines `health_endpoint()` function but never registers it as a route. No `/health` URL endpoint is mounted on the Gradio app. Health status is only accessible through the "System Info" tab button in the UI.

### GAPS (code exists, no doc)

1. **`src/utils/lambda_helpers.py`** -- `LambdaImageHandler` class with `process_image_for_lambda()`, `create_data_url()`, `cleanup_temp_files()` methods.
   - Not mentioned anywhere in README, CONTRIBUTING, or CLAUDE.md architecture section.

2. **`src/types/common.py`** -- Comprehensive type definitions module (17 TypedDicts/type aliases).
   - Not mentioned in CLAUDE.md's `src/` layout section despite being a significant module.

3. **`src/utils/validation.py`** -- Input validation module with `validate_prompt()`, `validate_dimensions()`, `validate_seed()`, `validate_cfg_scale()`, `validate_hex_colors()`, and a custom `ValidationError` class.
   - Not mentioned in CLAUDE.md's `src/` layout section. The `ValidationError` class lives here, not in `exceptions.py`, which could confuse developers looking for exception types.

### STALE (doc exists, code does not)

1. **`CLAUDE.md:54`** -- Documents `@handle_gracefully` decorator in `utils/exceptions.py`.
   - This decorator was removed from the codebase. Its replacement (`@gradio_handler`) lives in `handlers/canvas_handlers.py`.

### BROKEN LINKS

None found. Internal relative links all resolve to existing files.

### STALE CODE EXAMPLES

None. Shell command examples in README and CLAUDE.md match Makefile targets and CI configuration.

### CONFIG DRIFT

1. **Code reads `AWS_ID`** (`src/models/config.py:14`) as a fallback for `AMP_AWS_ID`.
   **Code reads `AWS_SECRET`** (`src/models/config.py:17`) as a fallback for `AMP_AWS_SECRET`.
   - Neither `AWS_ID` nor `AWS_SECRET` appears in `.env.example` or any documentation. These are silent fallback env vars.

2. **Code reads `AWS_LAMBDA_FUNCTION_NAME`** (`src/models/config.py:49`) to detect Lambda environment.
   **Code reads `AWS_LAMBDA_HTTP_PORT`** (`src/models/config.py:50`) for Lambda port configuration.
   - Neither appears in `.env.example` or docs. The port default (8080) should be documented for Docker deployments.

3. **Code reads `MINISTACK_URL`** (`tests/integration/conftest.py:11`) for integration testing.
   - `.env.example` does not include this. CONTRIBUTING.md mentions integration tests but does not document the `MINISTACK_URL` env var needed to run them.

### STRUCTURE ISSUES

1. **Coverage threshold inconsistency across docs** -- CLAUDE.md says 50%, README/CONTRIBUTING/Makefile/CI/pyproject.toml all say 75%. CLAUDE.md is the outlier and must be corrected.

2. **No `docs/` directory for project documentation** -- `docs/` contains only `plans/` (audit artifacts). All documentation lives in root-level markdown files. Acceptable for this project size but no place for API docs or operational runbooks if it grows.

3. **README "Prompt Model" reference** (line 128) -- Documents `Amazon Nova Lite (us.amazon.nova-lite-v1:0)` which is accurate per `config.py:25`, but this model is not mentioned in CLAUDE.md at all, creating incomplete architecture docs.

### DRIFT PREVENTION TOOLING RECOMMENDATIONS

**Markdown linting (markdownlint):** Add to `.pre-commit-config.yaml`:
```yaml
- repo: https://github.com/igorshubovych/markdownlint-cli
  rev: v0.44.0
  hooks:
    - id: markdownlint
      args: ['--fix']
```

**Link checking (lychee):** Add as a CI job in `.github/workflows/ci.yml`:
```yaml
link-check:
  name: Check Links
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v6
    - uses: lycheeverse/lychee-action@v2
      with:
        args: --no-progress '**/*.md'
        fail: true
```
