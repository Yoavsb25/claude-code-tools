# Repo Protection Setup for a Solo Django/Postgres SaaS

Here's what to set up, prioritized by impact. Since paying customers are involved, reliability and deployment safety are the top concerns.

---

## 1. Branch Protection (High Priority)

Go to **Settings → Branches → Add rule** on GitHub and protect your `main` branch:

- Require pull requests before merging (even for yourself — this builds the habit before contractors arrive)
- Require at least 1 approval (can be relaxed now, but set it up)
- Require status checks to pass before merging (CI must be green)
- Do not allow force pushes
- Do not allow branch deletion

This is the single most important thing. It prevents accidental pushes directly to main and broken deployments.

---

## 2. CI with GitHub Actions (High Priority)

Create `.github/workflows/ci.yml`. A minimal but solid setup for Django + Postgres:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run migrations check
        env:
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/test_db
        run: python manage.py migrate --check

      - name: Run tests
        env:
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/test_db
        run: python -m pytest
```

Key things this gives you:
- Tests run against a real Postgres instance (not SQLite), so you catch real bugs
- Migration check fails fast if you forgot to commit a migration
- PRs can't merge if tests fail

---

## 3. Pre-commit Hooks (Medium Priority)

Install `pre-commit` to catch issues before they even reach CI:

```bash
pip install pre-commit
```

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black
        language_version: python3.12

  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]
```

Then run:
```bash
pre-commit install
```

This means code style is enforced locally before a PR is even opened — cheaper than fixing it in review.

---

## 4. Secrets Management (High Priority)

Never commit secrets. Set up:

1. Add to `.gitignore` (if not already):
   ```
   .env
   *.env
   .env.*
   ```

2. Use `python-dotenv` or `django-environ` for local development.

3. Store secrets in GitHub Actions secrets (Settings → Secrets and variables → Actions).

4. For production, use your hosting provider's secret/environment variable system (Railway, Render, Heroku, etc.) — never hardcode.

Consider adding `detect-secrets` or `gitleaks` to your CI to scan for accidental secret commits:

```yaml
- name: Scan for secrets
  uses: gitleaks/gitleaks-action@v2
```

---

## 5. Dependency Management (Medium Priority)

Pin your dependencies precisely to avoid "works on my machine" breakage:

```bash
pip freeze > requirements.txt
```

Consider splitting into:
- `requirements.txt` — production deps only
- `requirements-dev.txt` — dev/test tools (pytest, black, etc.)

Add **Dependabot** to get automatic PRs when dependencies have security updates:

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
```

---

## 6. Issue and PR Templates (Low Priority, High Value When Contractors Arrive)

Create `.github/PULL_REQUEST_TEMPLATE.md`:

```markdown
## What does this PR do?

## How to test

## Checklist
- [ ] Tests added or updated
- [ ] Migrations included if models changed
- [ ] No secrets committed
```

This becomes essential when contractors are submitting PRs — it sets expectations without a conversation.

---

## 7. Environments and Deployment Gate (Medium Priority)

In GitHub Settings → Environments, create a `production` environment with:
- Required reviewers (yourself)
- Only deploy from `main`

Then update your deploy workflow to require environment approval before it runs. This prevents an accidental push from auto-deploying broken code.

---

## Recommended Order of Operations

1. Branch protection on `main` — do this today
2. GitHub Actions CI with Postgres — do this today
3. Secrets audit — make sure nothing sensitive is in git history
4. Pre-commit hooks — set up this week
5. Dependabot — 5 minutes, set it and forget it
6. PR template — before the first contractor starts
7. GitHub Environments deployment gate — before you have real paying users in production

---

## Summary Table

| Area | Tool | Priority |
|------|------|----------|
| Branch protection | GitHub Settings | Critical |
| CI/CD | GitHub Actions | Critical |
| Secret scanning | gitleaks / detect-secrets | High |
| Code style | black + ruff + pre-commit | Medium |
| Dependency updates | Dependabot | Medium |
| PR process | PR template | Medium |
| Deploy gating | GitHub Environments | High |
