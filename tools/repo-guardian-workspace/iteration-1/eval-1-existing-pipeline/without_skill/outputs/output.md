# Getting Your Internal Data Pipeline Under Control

Good news: six months in with a working pipeline and a team of four is actually a great time to do this. You're small enough that the transition won't be painful, but you've already felt the pain of moving fast without guardrails. Here's how to get there.

---

## 1. Enable Branch Protection on `main`

This is the single highest-leverage change. Go to **Settings > Branches > Add rule** on your GitHub repo and set:

- **Require pull requests before merging** — no direct pushes to `main`
- **Require at least 1 approving review** — forces a second pair of eyes
- **Require status checks to pass before merging** — gates merges on CI (set this up first, then come back)
- **Require branches to be up to date before merging** — prevents stale branches sneaking in
- **Do not allow bypassing the above settings** — applies to admins too

This alone will stop the "someone pushed a bad change at midnight" class of incident.

---

## 2. Set Up a CI Pipeline (GitHub Actions)

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt  # if you have one

      - name: Lint
        run: |
          ruff check .
          ruff format --check .

      - name: Type check
        run: mypy .

      - name: Run tests
        run: python -m pytest --tb=short
```

Adjust to match your actual test runner and linting setup. The key point: **every PR must be green before it can merge**.

---

## 3. Write Tests If You Don't Have Them

If tests are sparse or nonexistent, start here before everything else — CI is only as useful as your test suite.

Priorities for a data pipeline:

1. **Unit tests for transformation logic** — pure functions are easy to test and catch most bugs
2. **Integration tests for critical path** — mock external systems (databases, APIs), but test the wiring
3. **A smoke test for the ETL job entrypoint** — even just "does it start and not immediately crash"

Don't try to hit 80% coverage overnight. Pick the three places that caused your 6am incidents and write tests there first.

---

## 4. Adopt a Simple Branching Workflow

You don't need GitFlow. For a team of four, this is enough:

- `main` is always deployable / runnable
- Work happens on short-lived feature branches: `fix/etl-null-handling`, `feat/add-retry-logic`
- Open a PR, get one review, merge
- Delete the branch after merging

Branches should live for hours or a day or two — not weeks. Long-lived branches are where merge conflicts and big-bang merges come from.

---

## 5. Add Pre-commit Hooks Locally

This catches formatting and obvious issues before they even reach CI:

```bash
pip install pre-commit
```

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-merge-conflict
```

Run `pre-commit install` once per developer machine. Then it runs automatically on every `git commit`.

---

## 6. Add a Staging / Dry-Run Mode to the ETL Job

If you don't already have one, add a `--dry-run` flag or a separate staging environment that the ETL can run against. Then:

- Your CI pipeline can run the ETL in dry-run mode on every PR
- You catch data-shape and config errors before they hit production
- The 6am incident becomes "CI failed on the PR" not "production is down"

---

## 7. Set Up Alerting for the Production ETL Run

Separately from CI, you want to know *fast* when the scheduled job fails:

- If you're running on Airflow, use its built-in email/Slack alerting
- If it's a cron job, wrap it: `python etl.py && notify_success || notify_failure`
- Use a dead man's switch service (Healthchecks.io is free for small use) — it alerts you if the job *doesn't* check in, not just if it errors

This won't prevent incidents but it cuts your response time from "someone notices at 9am" to "Slack pings at 6:03am".

---

## 8. Document the Runbook

One markdown file in the repo: `RUNBOOK.md`. Contents:

- How to run the ETL locally
- How to run in dry-run mode
- What to do when it fails (step-by-step)
- Where the logs are
- Who owns what

When the 6am incident happens again (it will), you want the on-call person to have a checklist, not to be guessing.

---

## Rollout Order

Do these in order — each one builds on the last:

1. Write a few tests for the highest-risk code paths
2. Set up GitHub Actions CI running those tests
3. Enable branch protection requiring CI to pass
4. Install pre-commit hooks on all developer machines
5. Add dead man's switch alerting for the production job
6. Write the runbook

Steps 1-4 will prevent most of your incidents. Steps 5-6 minimize blast radius when something still goes wrong.

---

## What Not to Do

- Don't block on perfect test coverage before enabling branch protection — ship branch protection now
- Don't set up a complex branching strategy (develop, release, hotfix branches) — you're four people, it will slow you down
- Don't add every possible linter and checker at once — pick one (ruff covers a lot) and move on
