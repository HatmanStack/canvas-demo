# Phase 4: [FORTIFIER] CI Hardening, Type Safety, Reproducibility

## Phase Goal

Harden the CI pipeline, improve type safety, modernize the Dockerfile, and pin dependencies for reproducible builds. These are additive guardrails that prevent regression.

**Success criteria:**
- mypy runs in CI with strict flags matching `pyproject.toml` (no escape hatches)
- `_cloudwatch_client: Any | None` replaced with proper type
- Handler methods use TypedDict types where applicable
- `uv.lock` committed to repo
- Dockerfile uses `uv` instead of `pip`
- Commit message lint added to CI
- All tests pass

**Estimated tokens:** ~15,000

## Prerequisites

- Phase 3 complete
- Tests passing: `pytest tests/unit/ -v --tb=short`

## Tasks

### Task 1: Align mypy CI Config with pyproject.toml

**Goal:** Fix eval Code Quality finding. CI runs mypy with `--ignore-missing-imports --no-strict-optional --allow-untyped-defs`, effectively disabling the strict config in `pyproject.toml`. Align them.

**Files to Modify:**
- `.github/workflows/ci.yml` -- update mypy command
- `Makefile` -- update typecheck target
- `pyproject.toml` -- potentially adjust mypy overrides

**Implementation Steps:**

1. The goal is to run mypy using the `pyproject.toml` configuration (which has `strict = true`) without the CLI escape hatches. However, this will likely produce many errors on the first run.

2. Strategy: keep `pyproject.toml` strict config, but add per-module overrides for modules that currently have type issues. This is more honest than CLI flags.

3. In `.github/workflows/ci.yml`, change:
```yaml
- name: Run mypy
  run: mypy src/ --ignore-missing-imports --no-strict-optional --allow-untyped-defs
```
to:
```yaml
- name: Run mypy
  run: mypy src/
```

4. In `Makefile`, change:
```
typecheck:
	mypy src/ --ignore-missing-imports --no-strict-optional --allow-untyped-defs
```
to:
```
typecheck:
	mypy src/
```

5. Run `mypy src/` locally and catalog the errors. For each module with errors, add overrides in `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = ["src.services.aws_client"]
disallow_untyped_defs = false
# Reason: boto3 client factory returns dynamic types
```

Add the minimum overrides needed to pass. The existing overrides for `gradio.*`, `aiohttp.*`, `PIL.*`, `numpy.*` handle missing stubs. After removing `aiohttp` in Phase 2, remove that override.

6. Remove the `aiohttp.*` override from `pyproject.toml` (dependency was removed in Phase 2).

7. Remove `pytest-asyncio` from the CI install steps. Phase 2 removed `aiohttp` and all async tests, so `pytest-asyncio` is no longer needed. In `.github/workflows/ci.yml`, change both occurrences of:
```yaml
uv pip install --system pytest pytest-cov pytest-asyncio
```
to:
```yaml
uv pip install --system pytest pytest-cov
```
These appear on lines 76 and 114 (in the `test` and `integration-test` jobs). Also remove `pytest-asyncio` from `pyproject.toml` dev dependencies if it was not already removed in Phase 2.

**Verification Checklist:**
- [x] CI runs `mypy src/` without CLI escape hatches
- [x] `Makefile` runs `mypy src/` without CLI escape hatches
- [x] `mypy src/` passes locally
- [x] Per-module overrides in `pyproject.toml` are documented with reasons
- [x] `pytest-asyncio` not referenced in CI workflow or dev dependencies

**Testing Instructions:**
- Run `mypy src/` locally and confirm zero errors
- No pytest changes needed

**Commit Message Template:**
```
ci(typecheck): align mypy CI config with pyproject.toml strict settings

- Remove --ignore-missing-imports, --no-strict-optional, --allow-untyped-defs from CI
- Add per-module overrides in pyproject.toml where needed
- Remove aiohttp override (dependency removed)
```

---

### Task 2: Fix CloudWatch Client Type Annotation

**Goal:** Replace `_cloudwatch_client: Any | None` in `logger.py` with the proper `CloudWatchLogsClient` type. Eval Type Rigor remediation target.

**Files to Modify:**
- `src/utils/logger.py` -- fix type annotation

**Implementation Steps:**

1. Add a TYPE_CHECKING import:

```python
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

if TYPE_CHECKING:
    from mypy_boto3_logs import CloudWatchLogsClient
```

2. Change the type annotation:

```python
self._cloudwatch_client: "CloudWatchLogsClient | None" = None
```

3. Update the `cloudwatch_client` property return type:

```python
@property
def cloudwatch_client(self) -> "CloudWatchLogsClient | None":
```

**Verification Checklist:**
- [x] `Any` not used for `_cloudwatch_client`
- [x] `mypy src/utils/logger.py` passes (with the TYPE_CHECKING guard)
- [x] `ruff check src/utils/logger.py` passes

**Testing Instructions:**
- No runtime changes, existing tests pass

**Commit Message Template:**
```
fix(logger): replace Any type with CloudWatchLogsClient for cloudwatch_client

- Proper type annotation enables type checker to catch misuse
```

---

### Task 3: Commit uv.lock and Modernize Dockerfile

**Goal:** Fix reproducibility findings. Commit `uv.lock` for deterministic dependency resolution. Switch Dockerfile from `pip` to `uv`.

**Files to Modify:**
- `Dockerfile` -- use `uv` for installation
- `.gitignore` -- ensure `uv.lock` is not ignored (check current state)

**Implementation Steps:**

1. Check `.gitignore` for any `uv.lock` entry. Remove it if present.

2. Generate/update `uv.lock`:
```bash
uv lock
```

3. Stage `uv.lock` for commit.

4. Update `Dockerfile` to use `uv sync` with the lock file for truly deterministic builds:

```dockerfile
FROM public.ecr.aws/docker/library/python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies using lock file for reproducibility
COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-dev --no-editable

COPY src/ src/
COPY app.py seeds.json ./
COPY static/ static/

ARG TARGETARCH=amd64

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.0 /lambda-adapter /opt/extensions/lambda-adapter

CMD ["python3", "app.py"]
```

Note: `uv sync --frozen` installs from `uv.lock` without re-resolving, providing deterministic builds. The `--no-dev` flag excludes dev dependencies. The `--no-editable` flag installs the project package as a regular install. This replaces the previous `uv pip install -r requirements.txt` approach, which does NOT consult `uv.lock`.

**Verification Checklist:**
- [x] `uv.lock` is tracked by git (not in `.gitignore`)
- [x] `Dockerfile` uses `uv sync --frozen --no-dev --no-editable` instead of `pip install`
- [ ] `docker build -t canvas-demo .` succeeds (if Docker is available) -- Docker not available in env
- [x] `ruff check` still passes

**Testing Instructions:**
- Build the Docker image locally if Docker is available
- If Docker is not available, verify the Dockerfile syntax is valid

**Commit Message Template:**
```
chore(dockerfile): use uv for dependency installation and commit uv.lock

- Dockerfile now uses uv instead of pip for reproducible builds
- uv.lock committed for deterministic dependency resolution
- Eliminates pip/uv inconsistency between dev and production
```

---

### Task 4: Add Commit Message Lint to CI

**Goal:** Fix eval Git Hygiene remediation target. Add conventional commit validation in CI for PRs from contributors who may not have pre-commit hooks installed.

**Files to Modify:**
- `.github/workflows/ci.yml` -- add commit message lint job

**Implementation Steps:**

1. Add a new job to `ci.yml`:

```yaml
commit-lint:
  name: Commit Messages
  runs-on: ubuntu-latest
  if: github.event_name == 'pull_request'
  steps:
    - uses: actions/checkout@v6
      with:
        fetch-depth: 0

    - name: Check commit messages
      uses: webiny/action-conventional-commits@v1.3.0
      with:
        allowed-commit-types: "feat,fix,docs,test,chore,ci,refactor,style,build"
```

2. Do NOT add `commit-lint` to the `all-checks` needs list. The `commit-lint` job has `if: github.event_name == 'pull_request'`, so it will be `skipped` on push events. The `all-checks` job checks each dependency result with `!= "success"`, so a `skipped` result would fail the check and break push CI. Let `commit-lint` run independently as an advisory check for PRs.

3. Make the `commit-lint` job conditional on `pull_request` events only (not `push`), since push events to `github-branch` may include squash merges.

**Verification Checklist:**
- [x] `commit-lint` job appears in CI workflow
- [x] Job only runs on `pull_request` events
- [x] `commit-lint` is NOT in the `all-checks` needs list (it runs independently)
- [x] Workflow YAML is valid (check with `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`)

**Testing Instructions:**
- No local tests needed
- Will be verified on next PR

**Commit Message Template:**
```
ci: add conventional commit message linting for pull requests

- Uses webiny/action-conventional-commits
- Catches PRs with non-conventional messages from contributors without pre-commit hooks
```

---

### Task 5: Pin Critical Dependencies in requirements.txt

**Goal:** Fix finding #18. Pin `boto3`, `gradio`, and other runtime dependencies to minimum versions for reproducibility.

**Files to Modify:**
- `requirements.txt` -- add version pins
- `pyproject.toml` -- add minimum version constraints

**Implementation Steps:**

1. Run `uv pip list --format=columns` to get currently installed versions.

2. Update `requirements.txt` with minimum version pins (using `>=` for flexibility with lock file providing exact pins):

```
Pillow>=12.1.0
boto3>=1.35.0
python-dotenv>=1.0.0
gradio>=5.0.0
psutil>=5.9.0
numpy>=1.26.0
```

Note: Remove the `Pillow==12.1.1` exact pin and use `>=` since the lock file handles exact resolution. Or keep the exact pin if there is a specific reason.

3. Update `pyproject.toml` dependencies to match:

```toml
dependencies = [
    "Pillow>=12.1.0",
    "boto3>=1.35.0",
    "python-dotenv>=1.0.0",
    "gradio>=5.0.0",
    "psutil>=5.9.0",
    "numpy>=1.26.0",
]
```

4. Remove `aiohttp` from both files if not already done in Phase 2.

5. Regenerate `uv.lock`: `uv lock`

**Verification Checklist:**
- [x] All runtime dependencies have version constraints
- [x] `aiohttp` not in dependencies
- [x] `uv lock` succeeds
- [ ] `uv pip install --system -r requirements.txt` succeeds -- system pip not available in env

**Testing Instructions:**
- Install from fresh venv and run tests to confirm compatibility

**Commit Message Template:**
```
chore: pin runtime dependency versions for reproducibility

- All dependencies now have minimum version constraints
- Lock file provides exact resolution
- Removes aiohttp (replaced with stdlib urllib in Phase 2)
```

## Phase Verification

After completing all tasks:

1. `ruff check src/ tests/ && ruff format --check src/ tests/`
2. `mypy src/` (no CLI escape hatches)
3. `pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=75 -m "not integration"`
4. Verify `.github/workflows/ci.yml` is valid YAML
5. Verify `uv.lock` is tracked by git

**Known limitations:**
- `pyproject.toml` mypy overrides may need adjustment as the codebase evolves. The overrides should be treated as tech debt to reduce over time.
- Docker build verification requires Docker, which may not be available in all dev environments.
