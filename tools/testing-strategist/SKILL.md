---
name: testing-strategist
description: >
  Scans the codebase architecture and existing tests to produce a tailored testing
  strategy — coverage gaps, recommended frameworks, test pyramid shape, and a
  prioritized action plan with inline example tests. Use this skill whenever the
  user wants guidance on how to structure or improve testing: "help me test this",
  "what should I test", "suggest a testing strategy", "improve test coverage",
  "how should I write tests for this project", "what testing framework should I use",
  "add tests to my project", "I don't have good tests", "I want to start testing",
  "review my test suite", or any context where the user wants to know what and how
  to test. Trigger even when the user just asks "how do I test X?" in the context
  of an existing project.
---

# Testing Strategist

Reads the actual codebase and existing tests, then recommends a testing strategy specific to what's there — not a generic template.

## Step 1: Discover the codebase

**If the project is described rather than present** (no real files to scan), skip the bash commands and proceed to Step 2 using only what the user described. Note in the Current State section: "Analysis based on project description — no filesystem scan performed." The rest of the report should be just as specific; use the module/file names the user mentioned as if you had read them.

Run these scans to understand the project. Exclude noise directories.

```bash
# Tech stack detection
find . -maxdepth 2 \( \
  -name "package.json" -o -name "pyproject.toml" -o -name "setup.py" -o \
  -name "requirements.txt" -o -name "go.mod" -o -name "Cargo.toml" -o \
  -name "pom.xml" -o -name "build.gradle" \
\) | grep -v node_modules

# Existing test files
find . -type f \( \
  -name "*.test.ts" -o -name "*.test.tsx" -o -name "*.test.js" -o \
  -name "*.spec.ts" -o -name "*.spec.tsx" -o -name "*.spec.js" -o \
  -name "test_*.py" -o -name "*_test.py" -o -name "*_test.go" \
\) | grep -v node_modules | grep -v .git | head -40

# Test directories
find . -maxdepth 3 -type d \( \
  -name "test" -o -name "tests" -o -name "__tests__" -o \
  -name "spec" -o -name "e2e" -o -name "integration" \
\) | grep -v node_modules | grep -v .git

# CI config
find . -maxdepth 3 \( -name "*.yml" -o -name "*.yaml" \) | \
  grep -i "ci\|test\|action\|pipeline\|workflow" | grep -v node_modules | head -10

# Coverage config
find . -maxdepth 2 \( \
  -name ".coveragerc" -o -name "coverage.xml" -o -name "jest.config.*" -o \
  -name "vitest.config.*" -o -name ".nycrc" -o -name "codecov.yml" \
\) | grep -v node_modules

# Top-level directory structure
find . -maxdepth 2 -type d | grep -v node_modules | grep -v .git | \
  grep -v __pycache__ | grep -v ".venv" | grep -v dist | sort
```

After scanning, note: total test file count, test frameworks visible in config files, whether a CI pipeline runs tests, and whether coverage is measured.

## Step 2: Read source code samples

**If no files are readable**, reason from the described architecture instead. Identify the same signals (what the core logic is, what external dependencies exist, what the natural test seams are) from the description alone. A good description is sufficient to produce a useful strategy.

Read 3–5 key source files (not test files) chosen to represent the architecture:
- Entry point (main.py, index.ts, app.py, server.go, etc.)
- A core business logic module
- A data/persistence layer file (if present)
- An API/handler layer file (if present)

You're trying to understand:
- What kind of application this is (API, CLI, library, frontend app, etc.)
- What the important logic does — the things that need to be correct
- Module/class/function boundaries — natural seams for unit testing
- External dependencies (databases, HTTP clients, 3rd-party SDKs) — these need boundary tests or mocks

## Step 3: Read existing tests

If test files exist, read up to 10 of them — spread across unit, integration, and e2e if present.

Look for:
- Which framework is actually in use (vs. just installed)
- Test patterns: are fixtures/factories used, or is setup inline and duplicated?
- Assertion quality: do tests assert meaningful outcomes, or just "it didn't crash"?
- What's conspicuously absent — are there tests for the API layer but none for the business logic?

## Step 4: Run the test suite

Run the collect-only command now — it has no side effects and gives useful signal immediately:

| Stack | Collect-only (run automatically) |
|-------|----------------------------------|
| Python | `python -m pytest --collect-only -q 2>&1 \| head -40` |
| JS/TS (Jest) | `npx jest --listTests 2>/dev/null` |
| JS/TS (Vitest) | `npx vitest list 2>/dev/null` |
| Go | `go test ./... -list '.*' 2>&1 \| head -30` |

Then offer to run the full suite with coverage: "I can run the full test suite now to get real pass/fail and coverage data — want me to? It won't modify any files."

If the user agrees:

| Stack | Full run with coverage |
|-------|------------------------|
| Python | `python -m pytest --tb=short -q --cov=. --cov-report=term-missing 2>&1 \| head -60` |
| JS/TS (Jest) | `npx jest --coverage --passWithNoTests 2>&1 \| tail -40` |
| JS/TS (Vitest) | `npx vitest run --coverage 2>&1 \| tail -40` |
| Go | `go test ./... -cover -short 2>&1 \| tail -30` |

If the user declines or the run fails, proceed with static analysis only and note in the report that coverage figures are estimated.

## Step 5: Gap analysis

Map the architecture layers to what you found in tests:

| Layer | What tests exist | Gap severity | Why it matters |
|-------|-----------------|-------------|----------------|
| Core business logic | (fill in) | Critical / High / Medium / Low | (fill in) |
| API / HTTP handlers | (fill in) | ... | ... |
| Data / persistence | (fill in) | ... | ... |
| External integrations | (fill in) | ... | ... |
| CLI / entry points | (fill in) | ... | ... |
| UI components (if any) | (fill in) | ... | ... |

**Severity guide:**
- **Critical** — zero tests on code that directly determines correctness, handles money, or controls access. A bug here is a production incident or a silent wrong answer.
- **High** — tests exist but cover only the happy path; important error cases, edge cases, or integration points are uncovered
- **Medium** — reasonable coverage exists; gaps are in edge cases or secondary flows
- **Low** — well tested; only cosmetic or low-risk gaps remain

Bold Critical and High rows.

## Step 6: Calibrate the strategy to project size

Before recommending, gauge the codebase:
- **< 500 lines of source**: A single test file covering all logic paths is fine. Don't over-engineer.
- **500–10K lines**: A proper test pyramid matters. Prioritize integration tests at service boundaries.
- **> 10K lines**: Focus on high-churn modules, not blanket coverage. Contract tests for external boundaries are worth the investment.

## Step 7: Deliver the report

Use this exact structure:

---

## Testing Strategy Report — [Project Name]

### Current state
[If no tests exist, say so in one sentence and move on. Otherwise: 2–3 sentences on test count, rough coverage estimate, frameworks in use, and whether CI runs tests.]

### Architecture summary
[What the project does and its key layers — just enough to explain WHY the recommended strategy fits]

### Gap analysis
[The table from Step 5, filled in. Bold the Critical and High-severity rows.]

### Recommended test shape
[Name the shape that fits this project: **pyramid** (mostly unit), **diamond** (heavy integration), or **trophy** (integration-heavy with light unit and e2e). Explain why this shape fits the specific architecture and risk profile — not just as a ratio. Example: "A pyramid fits here because the core logic in task_service.py is pure and unit-testable; the HTTP layer is thin and doesn't need heavy coverage."]

### Framework & tooling recommendations

Recommend at most 3 tools to add. Pick only the ones the action plan's first 3 steps actually require — the user can add more later. If nothing needs to change, write: "No changes needed — existing tooling is sufficient."

| Tool | Purpose | Needed for |
|------|---------|------------|
| (e.g.) pytest-mock | Mocking external SDKs | Action items 1 and 2 |

### Action plan

The action plan lists tests to write, not tasks to complete. Installation and conftest setup are prerequisites — mention them in one line before the numbered list, then start counting from the first test. ROI means: logic that directly determines correctness or user-facing behavior first, not most lines covered.

Install: [tool1, tool2] *(omit if nothing is missing)*

1. **[Write the first test for X]** — [why this gap matters most]
2. ...
(5–8 steps max. Each step names a specific test or test file to write. "Wire tests to CI" is the one infrastructure task worth listing as a numbered action item if tests aren't running in CI yet.)

### Example tests
[2–3 code snippets using the project's actual module/class names and import style. Each example must include at least one assertion that would catch a real bug — not just "it didn't crash." These should be copy-paste-ready, not toy examples.]

### Start here

> **[One sentence naming the first test to write and where to put it.]**
>
> [Copy-paste the most important example test from the Examples section, or a stripped-down version of it.]

---

**One principle throughout:** recommend keeping what's there unless it's genuinely broken or missing. The goal is to tell the user what to do next, not to redesign their setup.
