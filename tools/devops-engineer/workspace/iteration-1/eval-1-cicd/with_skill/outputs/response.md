# CI/CD Setup for FastAPI + PostgreSQL on GitHub

Great starting point. Since you're on GitHub and have pytest tests, **GitHub Actions** is the obvious choice — it's free for public repos, generous on private ones, and deeply integrated with GitHub PRs, branches, and secrets.

Here's exactly what you need and in what order.

---

## What You're Building

A two-stage pipeline:

```
CI (on every PR)                     CD (on merge to main)
──────────────────────────────────   ──────────────────────────────────
✓ Install dependencies               ✓ Build Docker image
✓ Start PostgreSQL service           ✓ Push to container registry
✓ Run pytest                         ✓ Deploy to hosting platform
✓ Block merge if tests fail          ✓ Rollback if health check fails
```

Start with CI. Get that green. Then wire up CD once you've decided where you're deploying.

---

## Step 1: Containerize Your App

Before setting up a pipeline, your app needs a `Dockerfile`. CI and CD both depend on it.

```dockerfile
# Dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app

# Never run as root
RUN adduser --disabled-password --gecos '' appuser

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .

USER appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Also add a `.dockerignore`:

```
.venv/
__pycache__/
*.pyc
.env
.git/
```

---

## Step 2: Add a Health Check Endpoint

Your deployment platform needs this to know if a deploy succeeded. Add it to your FastAPI app:

```python
@app.get("/health")
def health():
    return {"status": "ok"}
```

If you want to check database connectivity too:

```python
from sqlalchemy import text

@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
```

---

## Step 3: Set Up CI with GitHub Actions

Create this file in your repo:

```yaml
# .github/workflows/ci.yml
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
          POSTGRES_USER: testuser
          POSTGRES_PASSWORD: testpassword
          POSTGRES_DB: testdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Cache pip dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: pytest
        env:
          DATABASE_URL: postgresql://testuser:testpassword@localhost:5432/testdb
```

**Key things happening here:**

- `services.postgres` spins up a real PostgreSQL container alongside the test runner — no mocking needed
- The `--health-cmd pg_isready` options block tests from starting until Postgres is actually ready
- `DATABASE_URL` is passed as an env var so your app connects to the test database
- Caching pip speeds up runs significantly after the first one

---

## Step 4: Configure Your App to Use DATABASE_URL

Your FastAPI app should read the database URL from an environment variable, not hardcode it:

```python
import os
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_async_engine(DATABASE_URL)
```

In CI, the `DATABASE_URL` env var is set in the workflow. In production, it'll come from your hosting platform's environment config.

---

## Step 5: Secrets Management

For any real secrets your tests need (API keys, external service credentials), **never put them in the YAML file**.

In GitHub: **Settings → Secrets and variables → Actions → New repository secret**

Then reference in your workflow:

```yaml
env:
  SOME_API_KEY: ${{ secrets.SOME_API_KEY }}
```

The test database credentials in the example above are not real secrets (they only exist in the ephemeral CI runner), so they can live directly in the YAML.

---

## Step 6: Add CD (Deploy on Merge to Main)

Once CI is passing, add a deploy job. The exact command depends on your hosting platform.

**Recommendation for a FastAPI + Postgres app with no existing cloud preference:** use **Railway**. It handles managed Postgres + app in one place, has a free tier, and deploys from GitHub automatically.

Here's how to add the deploy job to your workflow:

```yaml
  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment: production

    steps:
      - uses: actions/checkout@v4

      - name: Install Railway CLI
        run: npm install -g @railway/cli

      - name: Deploy to Railway
        run: railway up --service my-fastapi-app
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

The `needs: test` line ensures this job only runs if tests passed. The `environment: production` line lets you set environment-scoped secrets and optionally add a manual approval gate in GitHub Settings.

---

## Step 7: Protect Your Main Branch

In GitHub: **Settings → Branches → Add branch protection rule** for `main`:

- Check: **Require status checks to pass before merging**
- Select the `test` job from your workflow
- Check: **Require branches to be up to date before merging**

This enforces that no one (including you) can merge a PR if CI is failing.

---

## What You'll Have When Done

```
.github/
  workflows/
    ci.yml          # Runs tests on every PR against real Postgres
Dockerfile          # Containerizes the app for CD
.dockerignore
```

And in your app: a `/health` endpoint and `DATABASE_URL` read from env.

**First green CI run is the milestone.** After that, add CD once you've picked a hosting platform.

---

## Common Pitfalls

**"My tests pass locally but fail in CI"** — Usually a missing env var or a service that isn't ready yet. Add `echo $DATABASE_URL` as a debug step temporarily and check the `--health-*` options on the Postgres service are set correctly.

**"I don't want to commit my .env file"** — Good instinct. Never do this. Use GitHub Secrets for CI and your platform's environment variable config for production.

**"Should I run migrations in CI?"** — Yes. Run `alembic upgrade head` (or your migration tool) as a step before `pytest`. This ensures your migrations are always tested against a clean database.

```yaml
      - name: Run migrations
        run: alembic upgrade head
        env:
          DATABASE_URL: postgresql://testuser:testpassword@localhost:5432/testdb

      - name: Run tests
        run: pytest
        env:
          DATABASE_URL: postgresql://testuser:testpassword@localhost:5432/testdb
```
