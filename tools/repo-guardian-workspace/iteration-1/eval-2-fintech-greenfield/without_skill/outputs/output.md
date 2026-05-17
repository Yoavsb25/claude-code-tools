# Fintech Microservice Repo Governance — Day One Setup

For a 15-engineer team running Python 3.12 on a PCI-DSS compliant fintech platform, here is the complete governance setup to put in place from day one.

---

## 1. Branch Protection (GitHub Settings)

Configure branch protection on `main` (and `develop` if you use GitFlow):

- **Require pull request reviews before merging** — minimum 2 reviewers (given 15 engineers, 2 is the right floor for fintech)
- **Dismiss stale pull request approvals when new commits are pushed**
- **Require review from Code Owners** — enable CODEOWNERS file enforcement
- **Require status checks to pass before merging** — CI (tests, lint, security scans) must be green
- **Require branches to be up to date before merging**
- **Require signed commits** — mandatory for PCI-DSS audit trails
- **Do not allow bypassing the above settings** — applies even to admins
- **Restrict who can push to matching branches** — allow only via PR, no direct pushes

```
# GitHub repo settings > Branches > Add rule
Branch name pattern: main
✅ Require a pull request before merging
  ✅ Require approvals: 2
  ✅ Dismiss stale pull request approvals when new commits are pushed
  ✅ Require review from Code Owners
✅ Require status checks to pass before merging
  ✅ Require branches to be up to date before merging
  Status checks: ci/tests, ci/lint, ci/security
✅ Require signed commits
✅ Do not allow bypassing the above settings
```

---

## 2. CODEOWNERS

Create `.github/CODEOWNERS` to enforce ownership-based review requirements:

```
# Global fallback — any two senior engineers must review
* @org/team-leads

# Payment and cardholder data paths — security team must review
src/payments/          @org/security-team @org/payments-team
src/cardholder/        @org/security-team
infra/                 @org/platform-team @org/security-team
.github/               @org/platform-team
requirements*.txt      @org/security-team
Dockerfile             @org/security-team @org/platform-team
pyproject.toml         @org/platform-team
```

---

## 3. CI/CD Pipeline (GitHub Actions)

Minimum pipeline for PCI-DSS compliance. Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff mypy
      - run: ruff check .
      - run: mypy src/

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements-dev.txt
      - run: python -m pytest --cov=src --cov-fail-under=80

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install bandit pip-audit safety
      # Static analysis — catches common security bugs
      - run: bandit -r src/ -ll
      # Dependency vulnerability scanning
      - run: pip-audit
      # Check against known CVE database
      - run: safety check
      # Secret scanning
      - uses: trufflesecurity/trufflehog-actions-scan@main
        with:
          path: ./
          base: ${{ github.event.repository.default_branch }}
          head: HEAD

  sast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: returntocorp/semgrep-action@v1
        with:
          config: >-
            p/python
            p/owasp-top-ten
            p/pci-dss
```

---

## 4. Pre-commit Hooks

Install `pre-commit` so issues are caught before they reach CI. Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: ["--maxkb=500"]
      - id: detect-private-key
      - id: no-commit-to-branch
        args: ["--branch", "main"]

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ["--baseline", ".secrets.baseline"]

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.8
    hooks:
      - id: bandit
        args: ["-r", "src/", "-ll"]
```

Add to `Makefile` or `README.md`:
```bash
pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg
```

---

## 5. Dependency Management and Pinning

For PCI-DSS, you need reproducible, auditable builds with no supply chain surprises.

**Use `pyproject.toml` + `pip-tools` or `uv`:**

```toml
# pyproject.toml
[project]
name = "my-fintech-service"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111,<0.112",
    "pydantic>=2.7,<3",
    # ... pinned ranges, not wildcards
]

[tool.ruff]
line-length = 100
target-version = "py312"
select = ["E", "F", "B", "S", "I"]  # includes bandit-style (S) rules

[tool.mypy]
strict = true
python_version = "3.12"
```

Commit both `requirements.txt` (pinned via `pip-compile`) and `requirements.in` (abstract deps). Automate updates with Dependabot:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: pip
    directory: "/"
    schedule:
      interval: weekly
    reviewers:
      - org/security-team
    labels:
      - dependencies
      - security

  - package-ecosystem: github-actions
    directory: "/"
    schedule:
      interval: weekly
    reviewers:
      - org/platform-team
```

---

## 6. Secret Management

**Never commit secrets. Ever.** For PCI-DSS this is non-negotiable.

- Use GitHub Actions secrets for CI credentials (never hardcode)
- Use a secrets manager in production: AWS Secrets Manager, HashiCorp Vault, or GCP Secret Manager
- Add `.secrets.baseline` (detect-secrets) and commit it — this records known false positives so new secrets get caught
- Add `SECRET_SCANNING=true` in GitHub Advanced Security settings if on GitHub Enterprise

```gitignore
# .gitignore — must include these
.env
.env.*
*.pem
*.key
*.p12
*.pfx
secrets.json
credentials.json
```

---

## 7. Commit Signing (GPG or SSH)

Required for PCI-DSS audit trails — you need to prove who committed what.

```bash
# Each engineer sets up commit signing
git config --global commit.gpgsign true
git config --global user.signingkey <KEY_ID>
```

Or use SSH signing (simpler for modern Git):
```bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
```

Enforce in GitHub: Settings > Repositories > Require signed commits.

---

## 8. Repository Security Settings (GitHub)

In GitHub repo Settings:

- **Security advisories**: Enable private vulnerability reporting
- **Secret scanning**: Enable (alerts on detected secrets in pushes)
- **Secret scanning push protection**: Enable (blocks pushes containing secrets)
- **Dependency graph**: Enable
- **Dependabot alerts**: Enable
- **Dependabot security updates**: Enable
- **Code scanning (CodeQL)**: Enable for Python

Add `.github/workflows/codeql.yml`:
```yaml
name: CodeQL

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: "30 1 * * 1"  # Weekly on Monday

jobs:
  analyze:
    name: Analyze
    runs-on: ubuntu-latest
    permissions:
      actions: read
      contents: read
      security-events: write
    strategy:
      matrix:
        language: [python]
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
      - uses: github/codeql-action/autobuild@v3
      - uses: github/codeql-action/analyze@v3
```

---

## 9. Access Control and Permissions

- **Use Teams, not individuals**, for CODEOWNERS and branch protection
- **Principle of least privilege**: engineers get Write access, leads get Maintain, only platform/security leads get Admin
- **No personal access tokens with broad scopes** — use fine-grained PATs scoped to specific repos
- **Enable SSO enforcement** if on GitHub Enterprise with your IdP (Okta, etc.)
- **Audit log**: enable GitHub audit log streaming to your SIEM

Team structure suggestion:
```
org/payments-team     — Write
org/platform-team     — Maintain  
org/security-team     — Maintain
org/repo-admins       — Admin (2-3 people max)
```

---

## 10. Pull Request Template

Create `.github/pull_request_template.md`:

```markdown
## Summary
<!-- What does this PR do? -->

## Changes
- [ ] Feature / Bug fix / Refactor / Docs / Config

## Security checklist (required for PCI-DSS)
- [ ] No secrets or credentials committed
- [ ] No PAN, CVV, or cardholder data in code or logs
- [ ] Input validation added for any new endpoints
- [ ] Authentication/authorization unchanged or intentionally modified and reviewed
- [ ] Dependency changes reviewed for known CVEs

## Testing
- [ ] Unit tests added/updated
- [ ] Coverage did not decrease
- [ ] Integration tests pass

## Rollback plan
<!-- How do we revert if this causes an issue in production? -->
```

---

## 11. Issue Templates

Create `.github/ISSUE_TEMPLATE/` with at least:

- `bug_report.md` — includes severity, environment, steps to reproduce
- `security_vulnerability.md` — instructs reporters to use GitHub's private advisory feature instead of filing a public issue

---

## 12. Audit Logging

For PCI-DSS, you need an audit trail of who did what:

- **Enable GitHub audit log** (org-level) and stream it to your SIEM
- **Log all CI/CD executions** — store workflow run logs for at least 1 year (PCI-DSS requirement)
- **Protect audit logs**: store them in a separate, append-only storage location that developers cannot modify
- In code: ensure your service logs all cardholder data access events with user ID, timestamp, action, and outcome

---

## 13. Repository Configuration as Code

Create a `SECURITY.md` at repo root:

```markdown
# Security Policy

## Supported versions
| Version | Supported |
|---------|-----------|
| latest  | ✅        |

## Reporting a vulnerability
Please do NOT file a public GitHub issue for security vulnerabilities.
Use GitHub's private vulnerability reporting feature or email security@yourcompany.com.

We will acknowledge receipt within 24 hours and provide a resolution timeline within 72 hours.
```

---

## Summary: What to Do in Order

1. Create repo, add branch protection for `main` immediately
2. Set up `pyproject.toml`, `.gitignore`, `.pre-commit-config.yaml`
3. Commit `.github/CODEOWNERS`, PR template, issue templates
4. Set up GitHub Actions: `ci.yml` (lint + test + security) and `codeql.yml`
5. Configure Dependabot via `dependabot.yml`
6. Enable all GitHub security features (secret scanning, push protection, CodeQL)
7. Set up team permissions — no individual-level admin except 2-3 leads
8. Brief all engineers on commit signing setup
9. Wire audit log streaming to your SIEM before any production deployment

This setup gives you a defensible, auditable, PCI-DSS-aligned repo from day one without over-engineering it for a 15-person team.
