# Setting Up CI/CD for a FastAPI App on GitHub

## Overview

You'll set up a GitHub Actions pipeline that automatically runs your pytest tests against a real PostgreSQL database on every push and pull request. This guide covers everything from zero to a working CI/CD pipeline.

---

## What You Need to Set Up

1. A GitHub Actions workflow file (`.github/workflows/ci.yml`)
2. A way to manage secrets (database credentials, etc.)
3. Optionally: a deployment step (CD) once CI passes

---

## Step 1: Create the GitHub Actions Workflow

Create the directory and file in your repo:

```
.github/
  workflows/
    ci.yml
```

Here is a complete `ci.yml` that runs your pytest suite against PostgreSQL:

```yaml
name: CI

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
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

    env:
      DATABASE_URL: postgresql://testuser:testpassword@localhost:5432/testdb

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run tests
        run: |
          python -m pytest --tb=short -q
```

### Key points:

- **`services.postgres`**: GitHub Actions spins up a real PostgreSQL container alongside your tests. No mocking needed.
- **`DATABASE_URL`**: Passed as an environment variable so your app and tests can connect to it.
- **`--health-cmd pg_isready`**: Ensures Postgres is accepting connections before tests start.
- **`actions/checkout@v4`** and **`actions/setup-python@v5`**: Always pin to a major version.

---

## Step 2: Make Your App Read the Database URL from the Environment

Your FastAPI app should read `DATABASE_URL` from the environment, not have it hardcoded. A common pattern:

```python
# config.py or database.py
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/mydb")
```

If you use SQLAlchemy:

```python
from sqlalchemy import create_engine

engine = create_engine(DATABASE_URL)
```

In your pytest tests, the `DATABASE_URL` env var set in the workflow will be picked up automatically.

---

## Step 3: Store Secrets for Real Environments

For local development or production deployments, you don't want credentials in your code. Use **GitHub Secrets** for anything sensitive.

**How to add a secret:**
1. Go to your GitHub repo
2. Settings → Secrets and variables → Actions → New repository secret
3. Add secrets like `DATABASE_URL`, `SECRET_KEY`, etc.

**Use them in your workflow:**

```yaml
env:
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
  SECRET_KEY: ${{ secrets.SECRET_KEY }}
```

For CI tests, you can use hardcoded test credentials (like in the example above) since it's a throwaway container — no real data is at risk.

---

## Step 4: Verify Your `requirements.txt` Is Complete

GitHub Actions installs exactly what's in `requirements.txt`. Make sure it includes everything:

```
fastapi
uvicorn
sqlalchemy
psycopg2-binary   # PostgreSQL driver
pytest
httpx             # For FastAPI TestClient (if using async)
pytest-asyncio    # If your tests are async
alembic           # If you use migrations
```

Generate it from your venv if you haven't already:

```bash
pip freeze > requirements.txt
```

---

## Step 5: (Optional) Run Database Migrations Before Tests

If you use Alembic, add a migration step before running pytest:

```yaml
      - name: Run migrations
        run: alembic upgrade head
        env:
          DATABASE_URL: postgresql://testuser:testpassword@localhost:5432/testdb

      - name: Run tests
        run: python -m pytest --tb=short -q
```

---

## Step 6: (Optional) Add Continuous Deployment

Once tests pass, you can deploy automatically. The approach depends on where you host the app.

### Example: Deploy to a VPS (via SSH)

```yaml
  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'

    steps:
      - name: Deploy to server
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SSH_HOST }}
          username: ${{ secrets.SSH_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /srv/myapp
            git pull origin main
            source .venv/bin/activate
            pip install -r requirements.txt
            alembic upgrade head
            sudo systemctl restart myapp
```

### Example: Deploy to Render / Railway / Fly.io

These platforms detect pushes to `main` and auto-deploy — no extra CI step needed. Just connect your GitHub repo in their dashboard.

### Example: Deploy a Docker image

```yaml
  build-and-push:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Log in to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: youruser/yourapp:latest
```

---

## Complete File Structure

```
your-repo/
├── .github/
│   └── workflows/
│       └── ci.yml          ← The workflow you create
├── app/
│   ├── main.py
│   └── database.py
├── tests/
│   └── test_main.py
├── requirements.txt
└── alembic.ini             ← If using Alembic
```

---

## Quick Checklist

- [ ] Created `.github/workflows/ci.yml`
- [ ] Workflow uses a `postgres` service with health checks
- [ ] `DATABASE_URL` is set as an env var in the workflow
- [ ] App reads `DATABASE_URL` from the environment (not hardcoded)
- [ ] `requirements.txt` includes `psycopg2-binary` and `pytest`
- [ ] Secrets stored in GitHub Settings → Secrets (for production creds)
- [ ] (Optional) Alembic migrations run before tests
- [ ] (Optional) Deploy job runs only on push to `main`, after tests pass

---

## Troubleshooting Common Issues

| Problem | Fix |
|---|---|
| `Connection refused` to Postgres | Check the `options: --health-cmd pg_isready` block is present |
| `psycopg2` not found | Add `psycopg2-binary` to `requirements.txt` |
| Tests pass locally but fail in CI | Ensure `DATABASE_URL` env var is set and your app reads it |
| Migrations fail | Run `alembic upgrade head` as a step before `pytest` |
| Secrets not available | Confirm the secret name in GitHub Settings matches `${{ secrets.NAME }}` |
