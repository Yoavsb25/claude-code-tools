# Repo Guardian — Governance Checklist

## Interview Summary

| Question | Answer |
|----------|--------|
| Team size | 4 backend engineers (2–5 range) |
| Project stage | Existing repo being hardened |
| Risk | High — internal ETL tool with real production incidents (6am scrambles to fix broken daily jobs) |
| Current state | Nothing — no branch protection, no CI, direct pushes to main |
| Python version | 3.11 |

---

## Recommended Tier: Strict

You have 4 engineers pushing directly to main with no guardrails, and you've already had incidents where a bad merge broke a production ETL job. Even though this is an internal tool, the operational blast radius (a broken daily pipeline at 6am is a high-stress incident) puts your risk firmly in the High category. The Strict tier is the right call.

Here's your prioritized governance checklist — work top to bottom, each item builds on the last.

---

## Checklist

### ✅ Install pre-commit framework
**Why**: Hooks only run if pre-commit is installed; this is the foundation everything else builds on.
**Effort**: ~2 min
**How**:
```bash
pip install pre-commit
pre-commit install   # run once per dev clone
```
Add `pre-commit` to `requirements-dev.txt` (or `[dev]` extras in `pyproject.toml`) so teammates get it automatically.

---

### ✅ Black (auto-formatter)
**Why**: Eliminates all formatting debates and diff noise — Black is non-negotiable about style so you don't have to be.
**Effort**: ~2 min
**How**: Create `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.3.0
    hooks:
      - id: black
```

---

### ✅ Ruff (linter)
**Why**: Catches undefined names, unused imports, and ~700 other issues in milliseconds — faster than flake8 + isort combined.
**Effort**: ~2 min
**How**: Add to `.pre-commit-config.yaml`:
```yaml
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]
```

---

### ✅ Basic hygiene hooks
**Why**: Prevents the tiny issues (trailing whitespace, missing newline, accidental merge conflict markers) that make diffs ugly and confuse tools.
**Effort**: ~1 min
**How**: Add to `.pre-commit-config.yaml`:
```yaml
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-merge-conflict
      - id: check-added-large-files
```

---

### ✅ Branch protection (basic)
**Why**: Prevents direct pushes to `main` that skip review — this alone would have stopped the incidents you've been having.
**Effort**: ~3 min
**How**: GitHub → Settings → Branches → Add rule for `main`:
- ✅ Require a pull request before merging
- ✅ Require status checks to pass before merging _(add your CI job name once CI is set up)_
- ✅ Do not allow bypassing the above settings

---

### ✅ PR template
**Why**: Makes PRs self-documenting — reviewers know what changed, how to test it, and what to check, without asking.
**Effort**: ~5 min
**How**: Create `.github/pull_request_template.md`:
```markdown
## What changed and why

## How to test

## Checklist
- [ ] Tests added or updated
- [ ] No secrets or credentials committed
- [ ] PR title follows `type: short description` format (feat / fix / chore / docs)
```

---

### ✅ Mypy (type checker)
**Why**: Catches type mismatches before runtime — the class of bugs that silently pass tests but blow up in production with real data.
**Effort**: ~10 min (including fixing initial errors)
**How**: Add to `.pre-commit-config.yaml`:
```yaml
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy
        additional_dependencies: []  # add e.g. types-requests if needed
```
Add `mypy.ini` (or `[tool.mypy]` in `pyproject.toml`):
```ini
[mypy]
python_version = 3.11
ignore_missing_imports = true
```
Start with `strict = false` and tighten over time.

---

### ✅ GitHub Actions CI
**Why**: Pre-commit only runs on the committing developer's machine; CI enforces the same checks for everyone, including when someone forgets to run `pre-commit install`.
**Effort**: ~10 min
**How**: Create `.github/workflows/ci.yml`:
```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt pre-commit pytest
      - name: Run pre-commit
        run: pre-commit run --all-files
      - name: Run tests
        run: pytest
```

---

### ✅ Dependabot
**Why**: Keeps dependencies up to date automatically — most supply-chain attacks exploit known vulnerabilities in outdated packages.
**Effort**: ~2 min
**How**: Create `.github/dependabot.yml`:
```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
```

---

### ✅ Secret detection
**Why**: Prevents credentials, API keys, and tokens from ever entering git history — removing a committed secret requires a full history rewrite, which is painful.
**Effort**: ~5 min
**How**: Run once to create a baseline: `detect-secrets scan > .secrets.baseline`
Add to `.pre-commit-config.yaml`:
```yaml
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```
Commit `.secrets.baseline` (it stores hashes, not actual secrets).

---

### ✅ Bandit (security linter)
**Why**: Catches Python-specific security issues: hardcoded passwords, use of `eval`, weak cryptography, SQL injection risks.
**Effort**: ~5 min
**How**: Add to `.pre-commit-config.yaml`:
```yaml
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.8
    hooks:
      - id: bandit
        args: ["-c", "pyproject.toml"]
```
Add to `pyproject.toml`:
```toml
[tool.bandit]
exclude_dirs = ["tests", ".venv"]
skips = []
```

---

### ✅ CodeQL (SAST via GitHub Actions)
**Why**: Deep static analysis that finds vulnerabilities black, ruff, and bandit miss — runs in CI so it doesn't slow local commits.
**Effort**: ~5 min
**How**: Create `.github/workflows/codeql.yml`:
```yaml
name: CodeQL
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 6 * * 1'

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      actions: read
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: python
      - uses: github/codeql-action/analyze@v3
```

---

### ✅ Coverage enforcement
**Why**: Tests without coverage enforcement drift — the suite grows but critical ETL paths go untested, which is exactly the kind of gap that causes 6am incidents.
**Effort**: ~5 min
**How**: Update the `pytest` step in `ci.yml`:
```yaml
      - name: Run tests with coverage
        run: |
          pip install pytest-cov
          pytest --cov=. --cov-fail-under=80
```
Start at 80% and raise the threshold as you add tests. Add a `.coveragerc` to exclude boilerplate:
```ini
[run]
omit = tests/*, .venv/*, setup.py
```

---

### ✅ Stricter branch protection
**Why**: Requires human review and prevents reviewers from rubber-stamping stale PRs — the most common way bad code bypasses review.
**Effort**: ~5 min
**How**: Update the `main` branch rule in GitHub:
- ✅ Require at least 1 approving review
- ✅ Dismiss stale reviews when new commits are pushed
- ✅ Require conversation resolution before merging
- ✅ Do not allow bypassing (even admins)

---

### ✅ CODEOWNERS
**Why**: Automatically assigns reviewers based on which files changed — ETL pipeline code gets the right eyes without manual assignment.
**Effort**: ~5 min
**How**: Create `.github/CODEOWNERS`:
```
# Default owners for everything
* @your-github-username

# CI/CD changes require extra review
.github/ @your-github-username @another-reviewer
```

---

## Closing Notes

**Order of operations**: pre-commit → branch protection → CI → security scanning. This sequence minimizes feedback loop time — local hooks catch most issues before they ever hit CI.

**The two-layer model**: Branch rules protect against merging bad code; pre-commit protects against bad commits. Both layers are needed because CI can be skipped on forks, and pre-commit only runs if installed.

**Team onboarding**: Create a `CONTRIBUTING.md` with one required step: `pre-commit install` after cloning. Without this, hooks silently don't run. Alternatively, add it to your `Makefile` as `make setup`.
