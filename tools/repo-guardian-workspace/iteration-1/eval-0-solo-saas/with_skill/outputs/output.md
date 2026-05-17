# Repo Guardian — Django SaaS Project

## Situation summary

Based on what you've shared:

- **Team size**: Solo right now, with 1–2 contractors expected in a few months
- **Project stage**: New repo — just a `.gitignore` and `requirements.txt`, nothing else set up
- **Risk**: High — customers are paying, broken deployments are not acceptable
- **Current governance**: None
- **Python version**: 3.12

## Recommended tier: Strict

You're solo today, but high risk (paying customers, zero tolerance for broken deployments) and an imminent team expansion tips this into Strict. It's much easier to set the bar high now than to retrofit governance once contractors are already committing. A solo developer shipping a customer-facing SaaS should be held to the same standard as a small team.

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
Add `pre-commit` to `requirements-dev.txt` (or `[dev]` extras in `pyproject.toml`) so contractors get it automatically when they clone.

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

### ✅ Secret detection
**Why**: Prevents credentials, API keys, and tokens from ever entering git history — removing a committed secret requires a full history rewrite, which is painful. Especially critical for a SaaS with DB credentials and payment API keys.
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
**Why**: Catches Python-specific security issues: hardcoded passwords, use of `eval`, weak cryptography, SQL injection risks — all particularly relevant in a Django/Postgres app.
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

### ✅ Mypy (type checker)
**Why**: Catches type mismatches before runtime — the class of bugs that silently pass tests but blow up in production with real data.
**Effort**: ~10 min (including fixing initial errors)
**How**: Add to `.pre-commit-config.yaml`:
```yaml
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy
        additional_dependencies: []  # add e.g. types-requests, django-stubs if needed
```
Add `mypy.ini` (or `[tool.mypy]` in `pyproject.toml`):
```ini
[mypy]
python_version = 3.12
ignore_missing_imports = true
```
Start with `strict = false` and tighten over time. For Django, add `django-stubs` to get proper type support.

---

### ✅ Branch protection (basic)
**Why**: Prevents direct pushes to `main` that skip review — even if it's just you, this protects against accidental force-pushes and enforces the same gate for future contractors.
**Effort**: ~3 min
**How**: GitHub → Settings → Branches → Add rule for `main`:
- ✅ Require a pull request before merging
- ✅ Require status checks to pass before merging _(add your CI job name once CI is set up)_
- ✅ Do not allow bypassing the above settings

---

### ✅ PR template
**Why**: Makes PRs self-documenting — reviewers (including future you reviewing contractor work) know what changed, how to test it, and what to check without asking.
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

### ✅ GitHub Actions CI
**Why**: Pre-commit only runs on the committing developer's machine; CI enforces the same checks for everyone, including contractors and bots — and it's what branch protection will gate on.
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
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements.txt pre-commit pytest
      - name: Run pre-commit
        run: pre-commit run --all-files
      - name: Run tests with coverage
        run: |
          pip install pytest-cov
          pytest --cov=. --cov-fail-under=80
```

---

### ✅ Coverage enforcement
**Why**: Tests without coverage enforcement drift — the suite grows but critical paths go untested, which is unacceptable when customers depend on correct behaviour.
**Effort**: ~5 min
**How**: The CI step above already includes coverage. Add a `.coveragerc` to exclude boilerplate:
```ini
[run]
omit = tests/*, .venv/*, setup.py, manage.py
```
Start at 80% and raise the threshold as you add tests.

---

### ✅ Dependabot
**Why**: Keeps dependencies up to date automatically — most supply-chain attacks exploit known vulnerabilities in outdated packages, and a SaaS with paying customers is a real target.
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

### ✅ CodeQL (SAST via GitHub Actions)
**Why**: Deep static analysis that finds vulnerabilities black, ruff, and bandit miss — runs in CI so it doesn't slow local commits, and it's free for public repos (and available for private repos on GitHub).
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

### ✅ Stricter branch protection
**Why**: Requires human review and prevents reviewers from rubber-stamping stale PRs — the most common way bad code bypasses review, and essential before contractors start submitting code.
**Effort**: ~5 min
**How**: Update the `main` branch rule in GitHub (build on the basic rule you set earlier):
- ✅ Require at least 1 approving review
- ✅ Dismiss stale reviews when new commits are pushed
- ✅ Require conversation resolution before merging
- ✅ Do not allow bypassing (even admins)

---

### ✅ CODEOWNERS
**Why**: Automatically assigns you as reviewer on every PR — when contractors start contributing, you'll never miss a review request, and critical paths like CI config get mandatory review.
**Effort**: ~5 min
**How**: Create `.github/CODEOWNERS`:
```
# Default owners for everything
* @your-github-username

# CI/CD and security changes require your review
.github/ @your-github-username
```

---

## Closing advice

**Order of operations**: pre-commit → branch protection → CI → security scanning. This sequence minimizes feedback loop time — local hooks catch most issues before they ever hit CI.

**The two-layer model**: Branch rules protect against merging bad code; pre-commit protects against bad commits. Both layers are needed because CI can be skipped on forks, and pre-commit only runs if installed.

**Team onboarding**: Create a `CONTRIBUTING.md` with one required step: `pre-commit install` after cloning. Without this, hooks silently don't run. This is especially important for your future contractors — make it step one in your onboarding doc. Alternatively, add it to a `Makefile` as `make setup`.
