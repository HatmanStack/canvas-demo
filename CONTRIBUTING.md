# Contributing

## Setup

```bash
git clone <repository-url>
cd canvas-demo
make install-dev
cp .env.example .env  # Edit with your AWS credentials
pre-commit install
pre-commit install --hook-type commit-msg
```

## Development Workflow

1. Create a feature branch from `github-branch`
2. Make changes, ensuring `make lint && make typecheck && make test-cov` all pass
3. Commit using [conventional commits](#commit-conventions)
4. Open a PR against `github-branch`

## Commit Conventions

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/). This is enforced by a pre-commit hook.

Allowed prefixes:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks
- `ci:` - CI/CD changes
- `refactor:` - Code refactoring (no behavior change)
- `style:` - Formatting, whitespace (no logic change)
- `build:` - Build system or dependency changes

Examples:
```
feat: add image rotation support
fix: handle empty mask in outpainting
test: add rate limiter integration tests
```

## PR Process

- All PRs require passing CI (lint, typecheck, test with 75% coverage minimum)
- PRs should be **squash-merged** to keep `github-branch` history clean
- Write a clear PR description summarizing changes

## Testing

```bash
make test          # Run all unit tests
make test-cov      # Run with coverage (75% minimum)
make test-integration  # Run integration tests (requires LocalStack)
```

## Architecture

See `CLAUDE.md` for detailed architecture documentation.
