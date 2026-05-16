# REST API Stack Recommendation: Mobile Backend (iOS + Android)

## Context Summary

- Team: 2 developers, strong Python, some TypeScript
- Scale: ~50k users in year 1
- Features: User auth, push notifications, CRUD endpoints
- Clients: iOS + Android

---

## Recommended Stack

### Backend Framework: FastAPI (Python)

Use **FastAPI**. It fits your team's Python expertise, has excellent async support, auto-generates OpenAPI docs (great for mobile client coordination), and handles 50k users comfortably without over-engineering.

- Built-in async/await support via Starlette
- Pydantic for request/response validation — catches bugs before they hit mobile clients
- Auto-generated `/docs` endpoint reduces API miscommunication with mobile devs
- Well-supported with mobile-friendly patterns (JWT auth, pagination, file uploads)

**Alternative considered:** Django REST Framework is viable but heavier and slower for a greenfield API. Flask is too minimal — you'd rebuild too much by hand.

### Database: PostgreSQL

Use **PostgreSQL** via **SQLAlchemy 2.x** (async) with **Alembic** for migrations.

- Handles 50k users with ease — scales to millions without re-architecture
- JSONB columns give you flexibility for device tokens, preferences, and notification payloads without a separate NoSQL store
- Strong ecosystem: hosted on Supabase, Railway, Render, or AWS RDS
- SQLAlchemy async keeps the FastAPI async model consistent throughout the stack

**Do not use MongoDB here.** Your data (users, CRUD entities) is relational. Document stores add complexity without benefit at this scale.

### Authentication: JWT + python-jose or PyJWT

- Issue short-lived access tokens (15–60 min) + refresh tokens stored in the DB
- Store hashed passwords with **bcrypt** via `passlib`
- Use `fastapi-users` library to skip boilerplate: it handles registration, login, password reset, and OAuth out of the box
- For social auth (Apple Sign-In, Google) — add later via `fastapi-users` OAuth backend; scope it out of v1 unless required

### Push Notifications: Firebase Cloud Messaging (FCM)

Use **FCM** for both iOS and Android — single integration, no separate APNs handling needed.

- Store FCM device tokens in a `device_tokens` table linked to users
- Use `firebase-admin` Python SDK to send notifications
- For more than simple sends (scheduling, analytics, batching): add **Expo** push notification service if the mobile team uses React Native, or keep raw FCM if native

### Task Queue (for notifications + async work): Celery + Redis

Push notifications should be sent async, not in the request/response cycle.

- **Redis** as the Celery broker (also doubles as a cache for rate limiting, session data)
- **Celery** workers handle notification dispatch, email sends, and any background jobs
- Redis is lightweight to run and straightforward to host (Redis Cloud free tier, Upstash, or AWS ElastiCache)

---

## Full Stack Summary

| Layer | Choice | Why |
|---|---|---|
| Framework | FastAPI | Python-native, async, fast to build |
| Database | PostgreSQL | Relational, scalable, flexible |
| ORM | SQLAlchemy 2 (async) + Alembic | Async-compatible, solid migrations |
| Auth | fastapi-users + JWT + bcrypt | Battle-tested, minimal boilerplate |
| Push Notifications | Firebase FCM | Unified iOS + Android |
| Task Queue | Celery + Redis | Async jobs, notification dispatch |
| Hosting | Railway or Render (start) → AWS/GCP (scale) | Low ops overhead early |

---

## Infrastructure Recommendation

Start simple:

- **Railway** or **Render** for hosting FastAPI + Celery workers — both support Docker, auto-deploys from GitHub, and have managed PostgreSQL and Redis add-ons
- Move to AWS (ECS + RDS + ElastiCache) when you hit operational limits or need more control — 50k users does not require AWS complexity on day 1

---

## What to Skip in v1

- GraphQL — unnecessary complexity for 2 developers
- Microservices — monolith is the right call until you have pain points
- Kubernetes — overkill at this scale
- Separate NoSQL store — PostgreSQL JSONB covers dynamic data needs

---

## Quick-Start Checklist

1. `pip install fastapi uvicorn sqlalchemy alembic psycopg asyncpg fastapi-users firebase-admin celery redis`
2. Structure: `app/routers/`, `app/models/`, `app/schemas/`, `app/services/`, `app/workers/`
3. Configure Alembic for async migrations from day 1
4. Implement device token registration endpoint early — mobile teams need this before notification work begins
5. Add rate limiting via `slowapi` (FastAPI-compatible) on auth endpoints
