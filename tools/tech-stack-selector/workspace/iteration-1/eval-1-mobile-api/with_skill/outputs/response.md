## Recommended Stack: FastAPI + PostgreSQL + Firebase (Push) + Railway

### Language & Framework

**FastAPI** — Your team knows Python well, and FastAPI is the right Python choice for a mobile-backend REST API. It's async-native (so push notification delivery and concurrent mobile requests don't block each other), auto-generates OpenAPI docs your mobile devs can reference, and has first-class support for Pydantic models which makes request/response validation clean and explicit. For 50k users in year 1, it will handle load without issue and scale further if you need to move to multiple workers.

Avoid Django here: it's heavier than you need for a JSON REST API, and the ORM and admin panel aren't relevant to a mobile backend. FastAPI gives you the productivity without the overhead.

### Database

**PostgreSQL** — Users, auth tokens, CRUD entities, push notification preferences — all relational data. PostgreSQL handles all of it with ACID guarantees, and you won't need to add a second database for anything at 50k users. Use **Supabase** as the managed host: you get Postgres plus built-in auth (JWT-based, row-level security) and storage in one place, with a generous free tier and a great DX. This also lets you defer building your own auth system — Supabase Auth handles sign-up, login, refresh tokens, OAuth providers, and email verification out of the box.

**ORM: SQLModel** — It's built on SQLAlchemy and Pydantic, integrates natively with FastAPI, and reduces boilerplate. You define one model class that works as both the SQLAlchemy table and the Pydantic schema. Use Alembic for migrations (SQLModel wraps it).

### Push Notifications

**Firebase Cloud Messaging (FCM)** — It's the standard for sending push notifications to both iOS and Android from a single API. Your backend calls the FCM HTTP v1 API with a device token; FCM handles the platform-specific delivery to APNs (Apple) and GCM (Google). Use the `firebase-admin` Python SDK. Store device tokens in your Postgres DB, tied to the user record.

### Infrastructure

**Railway** — For a 2-person team at this scale, Railway is the right deployment target. It deploys from Git, handles environment variables, lets you run Postgres alongside your app (or connect to Supabase), and has no infrastructure configuration overhead. You can be deployed in under an hour. Move to AWS or GCP when Railway's limitations actually bite you — not before.

### Tooling

| Role | Tool | Why |
|------|------|-----|
| Linting & formatting | **Ruff** | Replaces Black + isort + flake8 in one tool; fast, zero config needed to start |
| Type checking | **mypy** (strict) | FastAPI + Pydantic already pushes you toward typed code; mypy enforces it |
| Testing | **pytest + httpx** | pytest is the Python standard; httpx gives you an async test client that works natively with FastAPI's `TestClient` |
| CI | **GitHub Actions** | Free for small teams, integrates with Railway deploy hooks |
| Git hooks | **pre-commit** with Ruff + mypy | Catch formatting and type errors before they hit CI |

### What to add later (not now)

- **Redis / caching layer** — Not needed at 50k users with a well-indexed Postgres schema. Add it when you see slow repeated reads (e.g., notification preferences or user profile fetched on every request).
- **Background task queue (Celery, ARQ)** — FastAPI's `BackgroundTasks` is enough for sending push notifications asynchronously. Only add a real queue (ARQ with Redis) if you need retries, scheduling, or job observability.
- **Rate limiting** — Start with Railway's built-in request limits. Add a proper rate limiter (slowapi wraps it nicely for FastAPI) when you have a concrete abuse vector.
- **Separate auth service** — Supabase Auth handles this. Don't build your own until Supabase's model is genuinely blocking you.

### One tradeoff to know

Supabase Auth is excellent but it's a dependency on a third-party platform. If you ever need advanced auth logic (custom claims, complex SSO, fine-grained session control), you'll be working around Supabase's model rather than owning it. For year 1 at this scale, the tradeoff is clearly worth it — the productivity gain is large and the risk is low. Just don't deeply couple your business logic to Supabase internals: keep auth concerns in a thin adapter layer so you can swap it later if needed.

---

### Bootstrap Commands

```bash
# Create project and virtualenv
mkdir mobile-api && cd mobile-api
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install fastapi uvicorn sqlmodel alembic psycopg2-binary \
  firebase-admin pydantic-settings pytest httpx ruff mypy pre-commit

# Scaffold the project
mkdir -p src/api src/domain src/db src/config tests scripts .github/workflows

# Generate requirements
pip freeze > requirements.txt

# Initialize Alembic for migrations
alembic init alembic

# Initialize pre-commit
cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
EOF
pre-commit install
```

**Connect to Supabase:**
1. Create a project at supabase.com — you get a Postgres connection string and anon/service keys.
2. Set `DATABASE_URL` and `SUPABASE_SERVICE_KEY` as environment variables in Railway.
3. Run Alembic migrations against the Supabase Postgres instance on deploy.

**FCM setup:**
1. Create a Firebase project, download the service account JSON.
2. Store it as a secret in Railway (or as a base64 env var).
3. Initialize `firebase_admin` with `credentials.Certificate(...)` at app startup.
