# Audit Remediation Plan: canvas-demo

## Overview

This plan addresses findings from three audit reports (health audit, 12-pillar evaluation, documentation audit) for the canvas-demo application, an AWS Bedrock Nova Canvas image generation app built with Gradio and deployed as a containerized Lambda.

The codebase scored PASS on only 1 of 12 evaluation pillars (Onboarding at 9/10). The remaining 11 pillars need work, with Performance at 5/10 and Defensiveness at 6/10 being the lowest. The health audit found 3 critical, 7 high, 9 medium, and 5 low-severity findings. The documentation audit found 7 drift items, 3 gaps, 1 stale reference, and 3 config drift items.

Work is sequenced as: cleanup first (remove dead code, unused deps), then structural fixes (architecture, error handling, performance, testing), then guardrails (CI hardening, type safety, linting), then documentation fixes. Each phase is tagged with the implementer role that handles it.

## Prerequisites

- Python >= 3.11 with `uv` package manager
- Project dependencies: `uv pip install --system -r requirements.txt && uv pip install --system -e ".[dev]"`
- Familiarity with: Gradio, boto3, PIL/Pillow, pytest
- Access to the repository on `github-branch`

## Phase Summary

| Phase | Tag | Goal | Token Estimate |
|-------|-----|------|----------------|
| 0 | -- | Foundation: ADRs, patterns, testing strategy | ~3k |
| 1 | [HYGIENIST] | Dead code removal, unused import cleanup, quick wins | ~12k |
| 2 | [IMPLEMENTER] | Architecture fixes: config, singleton, rate limiter, NSFW cache | ~25k |
| 3 | [IMPLEMENTER] | Defensiveness and performance: request tracing, error handling, datetime fixes | ~18k |
| 4 | [FORTIFIER] | CI hardening, type safety, Dockerfile modernization, dependency pinning | ~15k |
| 5 | [DOC-ENGINEER] | Documentation drift fixes, gap fills, prevention tooling | ~10k |

## Navigation

- [Phase-0.md](Phase-0.md) -- Foundation (ADRs, patterns, testing strategy)
- [Phase-1.md](Phase-1.md) -- [HYGIENIST] Dead code and cleanup
- [Phase-2.md](Phase-2.md) -- [IMPLEMENTER] Architecture and performance fixes
- [Phase-3.md](Phase-3.md) -- [IMPLEMENTER] Defensiveness, error handling, observability
- [Phase-4.md](Phase-4.md) -- [FORTIFIER] CI, type safety, reproducibility
- [Phase-5.md](Phase-5.md) -- [DOC-ENGINEER] Documentation fixes and prevention
- [feedback.md](feedback.md) -- Review feedback tracking
