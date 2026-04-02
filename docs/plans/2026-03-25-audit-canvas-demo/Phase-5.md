# Phase 5: [DOC-ENGINEER] Documentation Fixes and Prevention Tooling

## Phase Goal

Fix all documentation drift, fill gaps, and add prevention tooling (markdownlint, lychee link checker) so drift does not recur.

**Success criteria:**
- All 7 drift findings from doc-audit resolved
- All 3 gap findings addressed
- All 3 config drift items documented
- Stale `@handle_gracefully` reference removed
- markdownlint added to pre-commit
- lychee link checker added to CI
- Coverage threshold consistent across all docs (75%)

**Estimated tokens:** ~10,000

## Prerequisites

- Phases 1-4 complete (code changes must land before docs reference them)
- Familiarity with the doc-audit findings in `docs/plans/2026-03-25-audit-canvas-demo/doc-audit.md`

## Tasks

### Task 1: Fix CLAUDE.md Drift and Gaps

**Goal:** Fix all CLAUDE.md inaccuracies identified in the doc audit: coverage threshold, rate limiter description, handle_gracefully reference, module listing gaps, and capability count.

**Files to Modify:**
- `CLAUDE.md` -- fix drift items

**Implementation Steps:**

1. **Coverage threshold (drift #2):** Change `--cov-fail-under=50` to `--cov-fail-under=75` in the "Run tests" section. The project CLAUDE.md currently says 50%, but Makefile/CI/pyproject.toml all use 75%.

2. **Rate limiter description (drift #3):** Change the `services/rate_limiter.py` description from "S3-backed distributed rate limiter using ETags for optimistic locking" to accurately reflect the code after Phase 2 changes. After Phase 2, ETags ARE used, so update the description to match reality:
   - "S3-backed distributed rate limiter using ETags for optimistic locking (20 req/20min sliding window)"
   - This should now be accurate after Phase 2's changes.

3. **handle_gracefully reference (drift #4, stale #1):** Change the `utils/exceptions.py` description from mentioning `@handle_gracefully` to just describing the exception classes. The decorator was replaced by `@gradio_handler` in `handlers/canvas_handlers.py`. Update the line to:
   - `utils/exceptions.py` -- Custom exception hierarchy (CanvasError, ImageError, NSFWError, RateLimitError, ConfigurationError, BedrockError)

4. **Logger description (drift #5):** Add the Lambda-only detail:
   - `utils/logger.py` -- CloudWatch log batching (10 logs or 30s intervals, Lambda environments only), thread-safe

5. **Capability count (drift #6):** Change "8 image manipulation capabilities" to "7 image generation capabilities" and list them correctly. Remove "health monitoring" from the capability list (it is a separate system tab, not an image capability).

6. **Module gaps (gap #2, #3):** Add missing modules to the `src/` layout section:
   - `types/common.py` -- TypedDict definitions for Bedrock requests, rate limit data, health status, and Gradio types
   - `utils/validation.py` -- Input validation (prompt, dimensions, seed, CFG scale, hex colors) with custom ValidationError

7. **Lambda helpers gap (gap #1):** `lambda_helpers.py` had dead code removed in Phase 1. Update the description based on what remains:
   - `utils/lambda_helpers.py` -- Lambda environment utilities (temp file cleanup)

**Verification Checklist:**
- [x] Coverage threshold says 75% everywhere in CLAUDE.md
- [x] No reference to `@handle_gracefully` in CLAUDE.md
- [x] Rate limiter description matches post-Phase-2 code
- [x] `types/common.py` and `utils/validation.py` listed in `src/` layout
- [x] Capability count is 7, not 8

**Testing Instructions:**
- No automated tests (documentation only)
- Manual review of each changed line against the codebase

**Commit Message Template:**
```
docs(claude-md): fix drift items and add missing module descriptions

- Coverage threshold corrected to 75%
- Rate limiter description updated to reflect ETag implementation
- Removed stale @handle_gracefully reference
- Added types/common.py and utils/validation.py to layout section
- Fixed capability count from 8 to 7
```

---

### Task 2: Fix README.md Drift

**Goal:** Fix all README.md inaccuracies: Gradio badge version, capability count, health endpoint claim.

**Files to Modify:**
- `README.md` -- fix drift items

**Implementation Steps:**

1. **Gradio badge (drift #1):** The Gradio badge says "5.6.0" but the installed version is much newer. Since Gradio is not pinned to a specific version, change the badge to not include a version number:
   ```html
   <img src="https://img.shields.io/badge/Gradio-yellow" alt="Gradio" />
   ```
   Or remove the version and just say "Gradio".

2. **Capability count (drift #6):** The capabilities list includes "Health Monitoring" as an 8th item. Remove it from the capabilities list. Health monitoring is a system feature, not an image manipulation capability. The list should have 7 items.

3. **Health endpoint (drift #7):** Remove or update the line "Access `/health` for health status". After Phase 1 removed the dead `health_endpoint` function, there is no `/health` route. Change to:
   ```
   Use the "System Info" tab in the UI for health status and performance metrics.
   ```

**Verification Checklist:**
- [x] Gradio badge does not reference a specific outdated version
- [x] Capabilities list has 7 items (no Health Monitoring)
- [x] No reference to `/health` endpoint
- [x] All markdown links in README resolve to existing files

**Testing Instructions:**
- No automated tests
- Verify links manually: `CONTRIBUTING.md` link should resolve

**Commit Message Template:**
```
docs(readme): fix Gradio badge version, capability count, and health endpoint reference

- Gradio badge no longer references outdated version
- Capabilities list reduced to 7 (removed Health Monitoring)
- Health endpoint reference replaced with System Info tab
```

---

### Task 3: Document Undocumented Environment Variables

**Goal:** Fix config drift items from doc audit. Document fallback env vars and Lambda-specific vars in `.env.example`.

**Files to Modify:**
- `.env.example` -- add missing env var documentation

**Implementation Steps:**

1. Read the current `.env.example` file.

2. Add comments documenting the fallback chain for AWS credentials:
```bash
# AWS Credentials (checked in this order: AMP_AWS_ID > AWS_ID > AWS_ACCESS_KEY_ID)
AMP_AWS_ID=your-access-key-id
AMP_AWS_SECRET=your-secret-access-key
```

3. Add Lambda-specific variables with comments:
```bash
# Lambda Configuration (auto-detected, typically set by AWS)
# AWS_LAMBDA_FUNCTION_NAME=  # Presence triggers Lambda mode
# AWS_LAMBDA_HTTP_PORT=8080  # Default Lambda port
```

4. Add integration test variable:
```bash
# Integration Testing
# MINISTACK_URL=http://localhost:4566  # Required for integration tests
```

**Verification Checklist:**
- [x] `AWS_ID` / `AWS_SECRET` fallbacks documented
- [x] `AWS_LAMBDA_FUNCTION_NAME` and `AWS_LAMBDA_HTTP_PORT` documented
- [x] `MINISTACK_URL` documented
- [x] No real credentials in `.env.example`

**Testing Instructions:**
- No automated tests
- Verify `.env.example` does not contain real credential values

**Commit Message Template:**
```
docs(env): document fallback env vars and Lambda-specific configuration

- AWS credential fallback chain documented
- Lambda detection env vars documented
- MINISTACK_URL for integration tests documented
```

---

### Task 4: Add markdownlint to Pre-commit

**Goal:** Add markdown linting to prevent future documentation drift. Uses markdownlint-cli.

**Files to Modify:**
- `.pre-commit-config.yaml` -- add markdownlint hook

**Files to Create:**
- `.markdownlint.yaml` -- markdownlint configuration

**Implementation Steps:**

1. Add to `.pre-commit-config.yaml`:

```yaml
  - repo: https://github.com/igorshubovych/markdownlint-cli
    rev: v0.44.0
    hooks:
      - id: markdownlint
        args: ['--fix']
```

2. Create `.markdownlint.yaml` in the project root with sensible defaults:

```yaml
# markdownlint configuration
default: true

# Allow long lines (common in markdown)
MD013: false

# Allow inline HTML (used in README badges)
MD033: false

# Allow duplicate headings in different sections
MD024:
  siblings_only: true

# Allow trailing punctuation in headings
MD026: false
```

3. Run `markdownlint` locally on existing docs to check for issues: `npx markdownlint-cli '**/*.md' --fix`. Fix any issues that arise.

**Verification Checklist:**
- [x] markdownlint hook in `.pre-commit-config.yaml`
- [x] `.markdownlint.yaml` config file exists
- [x] `npx markdownlint-cli '*.md'` passes on root-level docs
- [x] Pre-commit runs without errors: `pre-commit run markdownlint --all-files`

**Testing Instructions:**
- Run `pre-commit run markdownlint --all-files` to verify
- Fix any lint errors in existing markdown files

**Commit Message Template:**
```
ci(pre-commit): add markdownlint for documentation quality

- Catches formatting issues before commit
- Configuration allows inline HTML and long lines
```

---

### Task 5: Add Link Checker to CI

**Goal:** Add lychee link checker as a CI job to catch broken links in documentation.

**Files to Modify:**
- `.github/workflows/ci.yml` -- add link-check job

**Files to Create:**
- `.lychee.toml` -- lychee configuration to exclude known-unreachable URLs

**Implementation Steps:**

1. Add a new job to `ci.yml`:

```yaml
link-check:
  name: Check Links
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v6
    - name: Check markdown links
      uses: lycheeverse/lychee-action@v2
      with:
        args: --no-progress '**/*.md'
        fail: true
```

2. This job runs independently (not in the `all-checks` needs list) to avoid blocking PRs on transient external link failures. It serves as an advisory check.

3. Optionally add a `.lychee.toml` config file to exclude known-flaky external URLs:

```toml
# lychee configuration
exclude = [
    "https://t7bmxtdc6ojbkd3zgknxe32xdm0oqxkw.lambda-url.us-west-2.on.aws/",
]
```

The Lambda URL in the README may not be publicly accessible, so exclude it.

**Verification Checklist:**
- [x] `link-check` job appears in CI workflow
- [x] `.lychee.toml` excludes known-unreachable URLs
- [x] Workflow YAML is valid

**Testing Instructions:**
- No local tests needed
- Will be verified on next CI run

**Commit Message Template:**
```
ci: add lychee link checker for markdown documentation

- Catches broken links in markdown files
- Runs as advisory check (does not block merges)
- Excludes Lambda URL (not publicly accessible)
```

## Phase Verification

After completing all tasks:

1. Verify all doc-audit findings are addressed:
   - Drift #1-7: all fixed
   - Gap #1-3: all addressed
   - Stale #1: fixed
   - Config drift #1-3: all documented
2. Run `pre-commit run --all-files` to verify markdownlint passes
3. Verify `.github/workflows/ci.yml` is valid YAML
4. Read through CLAUDE.md, README.md, and `.env.example` to confirm accuracy against current code

**Known limitations:**
- markdownlint may flag issues in `docs/plans/` audit documents. These are not code docs and can be excluded via `.markdownlintignore` if needed.
- Lychee link checker may have false positives for external URLs behind auth. The `.lychee.toml` exclusion list should be maintained.
