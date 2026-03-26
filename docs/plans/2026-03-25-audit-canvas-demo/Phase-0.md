# Phase 0: Foundation

This phase defines architecture decisions, conventions, and testing strategy that apply across all subsequent phases.

## Architecture Decision Records

### ADR-1: Preserve Existing Module Structure

**Decision:** Keep the existing `src/` package layout (`models/`, `services/`, `handlers/`, `utils/`, `types/`). No structural reorganization.

**Rationale:** The layout is sound. The audit findings are about implementation details within modules, not about module boundaries. Restructuring would create unnecessary churn.

### ADR-2: Defer Config Lazy-Init to Phase 2

**Decision:** The global singleton instantiation pattern (`config = AppConfig()` at module scope) is a critical finding, but fixing it requires careful coordination across all modules. Phase 1 (hygienist) should not touch it. Phase 2 introduces a factory function pattern.

**Rationale:** Changing config initialization affects every module that imports `config`. Doing it alongside dead code removal risks cascading failures.

### ADR-3: Keep S3-Based Rate Limiter (Add Conditional Writes)

**Decision:** Keep S3 as the rate limiter backend. Do not migrate to DynamoDB. Add conditional writes using ETags to fix the race condition.

**Rationale:** DynamoDB would add a new service dependency and IAM permissions for a demo app. S3 conditional writes (using `IfMatch` on ETag) solve the TOCTOU race at the same cost.

### ADR-4: Replace aiohttp with Synchronous stdlib HTTP (urllib.request)

**Decision:** Remove `aiohttp` dependency. Replace async NSFW check with synchronous `urllib.request` from the standard library.

**Rationale:** The current async/sync dance (`asyncio.run()` with `RuntimeError` fallback) is fragile in Gradio's runtime context. Gradio handlers are synchronous. The NSFW API call is a simple POST. Using `urllib.request` eliminates the event loop complexity, the `aiohttp` dependency, and avoids adding any new runtime dependency.

### ADR-5: No New Dependencies

**Decision:** No new runtime dependencies will be added. The `aiohttp` replacement uses `urllib.request` from the standard library.

**Rationale:** YAGNI. The codebase has 7 runtime deps, which is proportional for its scope.

## Shared Patterns and Conventions

### Commit Message Format

All commits use conventional commits:

```text
type(scope): description

- detail 1
- detail 2
```

Types: `fix`, `refactor`, `test`, `chore`, `ci`, `docs`, `style`
Scopes: `config`, `aws-client`, `rate-limiter`, `image-processor`, `handlers`, `health`, `logger`, `lambda-helpers`, `validation`, `ci`, `dockerfile`, `docs`

### Testing Strategy

- All tests run without live AWS credentials (mocked via `tests/conftest.py` env var setup)
- Unit tests in `tests/unit/`, integration tests in `tests/integration/`
- Use `pytest` fixtures for shared mocks; prefer constructor injection over patching where possible
- Run tests after each task: `pytest tests/unit/ -v --tb=short`
- Run full suite with coverage before committing phase work: `pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=75 -m "not integration"`

### Linting and Formatting

- Run `ruff check src/ tests/` and `ruff format --check src/ tests/` before each commit
- Fix lint issues with `ruff check --fix src/ tests/` and `ruff format src/ tests/`

### Branch Strategy

- All work on the current feature branch (not `main` directly)
- One commit per task (squash at PR time)
