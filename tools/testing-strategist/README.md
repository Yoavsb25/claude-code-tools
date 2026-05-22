# testing-strategist

Scans your codebase architecture and existing tests, then produces a testing strategy tailored to what's actually there.

## What it does

- Detects your tech stack, frameworks, and test tooling
- Reads your source code to understand the architecture (API layers, business logic, data layer)
- Reads existing tests to understand what's covered and how
- Optionally runs your test suite to get real pass/fail and coverage data
- Delivers a structured report: current state, gap analysis, recommended test pyramid, framework recommendations, and an ordered action plan with example tests in your project's own style

## When to use it

Say things like:
- "Suggest a testing strategy for my project"
- "What should I be testing?"
- "Review my test suite and tell me what's missing"
- "How do I improve test coverage?"
- "I want to add tests — where do I start?"

## Sample output

```
## Testing Strategy Report — my-api

### Current state
12 test files, ~40% line coverage via pytest. Tests are concentrated in the
API handler layer; business logic in `services/` has no tests. CI runs pytest
on push but no coverage gate is enforced.

### Gap analysis
| Layer              | What tests exist         | Gap severity |
|--------------------|--------------------------|-------------|
| Business logic     | None                     | High        |
| API handlers       | 8 test files, happy-path | Medium      |
| Data / ORM         | None                     | High        |
| External HTTP APIs | 1 smoke test             | Medium      |

### Action plan
1. Add unit tests for `services/pricing.py` — this is the most complex logic...
2. Add integration tests for the DB layer using a test database...
...
```
