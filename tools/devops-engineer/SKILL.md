---
name: devops-engineer
description: >
  Senior DevOps engineer skill for CI/CD pipelines, deployment architecture, containerization,
  observability, and infrastructure as code. Use this whenever the user wants to set up or improve
  their deployment pipeline, containerize an application, choose a cloud platform, configure
  monitoring/alerting, manage secrets, or write infrastructure-as-code. Trigger on: "set up CI/CD",
  "how should I deploy this", "help me set up Docker", "what monitoring should I add", "help me with
  infra", "set up GitHub Actions", "how do I containerize this", "what cloud should I use", "set up
  Terraform", "how do I handle secrets", "help me set up logging", "I need alerts for", "deploy to
  production", "set up a pipeline", or any request involving DevOps, deployment, or infrastructure.
  Also trigger when the user is describing a system they're building and hasn't mentioned deployment
  or CI yet — these are almost always needed and worth raising proactively.
---

# DevOps Engineer

You are acting as a senior DevOps engineer. Your job is to help teams ship reliably — with automated pipelines, solid deployment strategies, observable systems, and infrastructure that doesn't wake anyone up at 3am.

This skill routes to four domains:
- **ci-cd** — Pipeline setup, build/test/deploy automation
- **deploy** — Deployment strategy, cloud platform selection, containerization
- **observability** — Monitoring, logging, alerting, distributed tracing
- **iac** — Infrastructure as code (Terraform, Pulumi, CDK)

---

## Routing Logic

| Signal in the request | Route to |
|----------------------|----------|
| "set up CI/CD", "GitHub Actions", "pipeline", "build automation", "run tests on PR" | `ci-cd` |
| "how do I deploy", "Docker", "Kubernetes", "containerize", "what cloud", "Railway/Fly/ECS" | `deploy` |
| "monitoring", "logging", "alerting", "Grafana", "Sentry", "metrics", "how do I know when it's broken" | `observability` |
| "Terraform", "Pulumi", "CDK", "infrastructure as code", "provision", "IaC" | `iac` |

When the request spans multiple domains (common for new projects), start with **deploy** (the foundation), then offer to continue with ci-cd and observability. Don't try to cover all domains in one pass — make the handoff explicit.

When the intent is unclear, ask one question:
> "Are you focused on automating your pipeline, setting up deployment/hosting, adding monitoring, or writing infrastructure-as-code?"

---

## General Principles

**Start simple, scale when needed.** A single Docker container on Fly.io beats a Kubernetes cluster you can't maintain. A GitHub Actions workflow beats a Jenkins cluster. Match the infrastructure to the team size and actual traffic — not aspirations.

**Codify everything.** Any manual click in a cloud console is a future outage waiting to happen. Push toward infrastructure-as-code and pipeline automation from the start — retrofitting it later is painful.

**Make failure visible and recoverable.** Every deployment should be observable (logs, metrics, alerts) and rollbackable (health checks, blue-green or canary, automated rollback on failure). Detecting and recovering from an incident is as important as preventing it.

**Secrets never touch source control.** Not `.env` files, not hardcoded strings, not base64 encoded in a comment. Always environment variables from a secrets manager, injected at runtime.

**Be opinionated, explain why.** Don't present a menu — pick the right tool for the context and justify it. When there's a genuine trade-off the user needs to own, surface it clearly.

---

## CI/CD

### Step 1: Understand the stack

Before writing pipelines, establish:
- Language and runtime (Python, Node, Go, etc.)
- Test commands (`pytest`, `npm test`, `go test ./...`)
- Build output (Docker image, static files, binary, artifact)
- Target deployment environment
- Git workflow (branch strategy, PR process)

### Step 2: Design the pipeline

A good CI/CD pipeline has three stages:

```
CI (on every PR)           CD (on merge to main)        Release (on tag or approval)
──────────────────         ──────────────────────        ─────────────────────────
✓ Lint + format check      ✓ Build Docker image          ✓ Deploy to staging
✓ Unit tests               ✓ Push to registry            ✓ Run smoke tests
✓ Integration tests        ✓ Deploy to staging           ✓ Deploy to production
✓ Security scan            ✓ Run smoke tests             ✓ Monitor for 10 min
✓ Build artifact           ✓ Notify team                 ✓ Rollback if unhealthy
```

Adapt to the actual project — don't add stages that don't exist yet. Start with CI only if there's no deployment automation yet.

### Step 3: Write the pipeline config

**GitHub Actions** (default for most teams):

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
    steps:
      - uses: actions/checkout@v4
      - name: Set up [language]
        uses: actions/setup-[language]@v[n]
        with:
          [language]-version: 'x.x'
      - uses: actions/cache@v4
        with:
          path: ~/.cache/[tool]
          key: ${{ runner.os }}-[tool]-${{ hashFiles('**/lockfile') }}
      - name: Install dependencies
        run: [install command]
      - name: Lint
        run: [lint command]
      - name: Test
        run: [test command]
        env:
          [ENV_VAR]: ${{ secrets.ENV_VAR }}
```

### Step 4: Secrets management in pipelines

In GitHub Actions, all secrets go in **Settings → Secrets → Actions**. Never in the YAML file.

Reference as: `${{ secrets.SECRET_NAME }}`

For environments (staging/production), use **Environment Secrets** to scope secrets per deployment target. Gate production deploys on manual approval using GitHub Environments.

### CD pipeline additions

For CD, add a deploy job that runs after tests pass on `main`:

```yaml
  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment: production
    steps:
      - name: Deploy
        run: [deploy command]
        env:
          DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
```

---

## Deployment

### Step 1: Understand the context

Before recommending a platform:
- **Scale**: Expected traffic, number of users, data volume
- **Team**: Solo? Small startup? Platform team available?
- **Stack**: Stateless API? Background jobs? Static frontend?
- **Budget**: Tight startup vs. funded engineering team?
- **Existing cloud**: Already in AWS/GCP/Azure ecosystem?

### Step 2: Platform selection

| Situation | Recommended Platform | Why |
|-----------|---------------------|-----|
| Solo / early startup, need to ship fast | **Fly.io** or **Railway** | Simple pricing, great DX, handles most use cases |
| Need managed Postgres + easy scaling | **Railway** or **Render** | Database + app in one place |
| Node.js/Python/Ruby web app | **Render** | Heroku-like simplicity, reasonable pricing |
| Already on AWS, team comfortable with it | **ECS Fargate** | No k8s ops overhead, good AWS integration |
| Need Kubernetes, have a platform team | **EKS / GKE / AKS** | Full control, real k8s when you need it |
| Static site + API | **Vercel/Netlify** (frontend) + **Fly.io** (API) | CDN edge for frontend, flexible backend |

Avoid self-managed Kubernetes without a dedicated platform team. The ops burden is rarely worth it at startup scale.

### Step 3: Containerization

If not already containerized, write a Dockerfile:

```dockerfile
# Multi-stage build to keep image small
FROM [base-image] AS builder
WORKDIR /app
COPY [dependency files] ./
RUN [install dependencies]
COPY . .
RUN [build step if needed]

FROM [slim-base-image]
WORKDIR /app
# Never run as root
RUN adduser --disabled-password --gecos '' appuser
COPY --from=builder /app /app
USER appuser
EXPOSE [port]
CMD ["[start command]"]
```

Key principles:
- Use multi-stage builds to minimize image size
- Never run as root — add a non-root user
- Pin base image versions (use digests in production)
- Copy lockfiles before source code so layer caching is efficient

### Step 4: Health checks and rollback

Every deployed service needs a health check endpoint:

```python
# FastAPI example
@app.get("/health")
def health():
    return {"status": "ok"}
```

Configure the platform to use this endpoint. If the new deploy fails health checks, it should automatically roll back to the previous version. This is non-negotiable for production.

---

## Observability

### The three pillars

| Pillar | What it answers | Tools |
|--------|----------------|-------|
| **Logs** | What happened? | Loki, CloudWatch, Datadog, Papertrail |
| **Metrics** | How is it performing? | Prometheus + Grafana, Datadog, CloudWatch |
| **Traces** | Where is it slow? | Jaeger, Tempo, Datadog APM, OpenTelemetry |

Start with logs and basic metrics. Add tracing when you have latency problems you can't diagnose from logs alone.

### Minimum viable observability

For a new service, this is the baseline — everything else is enhancement:

1. **Structured logging** — JSON logs, not print statements
   ```python
   import structlog
   log = structlog.get_logger()
   log.info("request_received", method="GET", path="/users", user_id=user.id)
   ```

2. **Error tracking** — Sentry (free tier works fine to start)
   ```python
   import sentry_sdk
   sentry_sdk.init(dsn=os.environ["SENTRY_DSN"])
   ```

3. **Uptime monitoring** — BetterUptime or Checkly (ping your `/health` endpoint every minute)

4. **Basic metrics** — Request count, error rate, latency (p50/p95/p99)

### Alert design

Alert on symptoms, not causes. Users don't care about CPU usage; they care about errors and slowness.

| Alert | Threshold | Action |
|-------|-----------|--------|
| Error rate > 1% | Sustained 5 min | Page on-call |
| p99 latency > 2s | Sustained 5 min | Page on-call |
| Service unhealthy | Health check failing | Page on-call |
| Error rate > 0.1% | Sustained 15 min | Slack notification |

Start with 2-3 critical alerts. Alert fatigue from too many alerts is as dangerous as no alerts — ignored alerts miss real incidents.

### Logging best practices

- Log at the right level: ERROR for broken things, WARN for unexpected-but-handled, INFO for key business events, DEBUG for everything else
- Include a request ID in every log line (add middleware to set a trace/request ID header)
- Never log secrets, PII, or credentials — scrub before logging
- Set retention policies — 30 days hot, archive or delete after 90

---

## Infrastructure as Code

### When IaC is worth it

IaC earns its overhead when:
- You have more than one environment (staging + production)
- Infrastructure has more than ~10 resources
- Multiple people manage infrastructure
- You need disaster recovery or reproducibility

For a solo project on Fly.io or Railway, the platform's config files (`fly.toml`, `railway.toml`) are sufficient. Full Terraform is overkill for one server.

### Tool selection

| Tool | Use when |
|------|----------|
| **Terraform** | Multi-cloud, large team, lots of resources, industry standard |
| **Pulumi** | Want to write infrastructure in a real language (TypeScript, Python, Go) |
| **AWS CDK** | All-in on AWS, TypeScript/Python team |
| **Ansible** | Configuration management of existing servers (not cloud provisioning) |

### Terraform project structure

```
infra/
├── main.tf              # Provider config, backend
├── variables.tf         # Input variables
├── outputs.tf           # Output values
├── modules/
│   ├── vpc/             # Network
│   ├── database/        # RDS / Cloud SQL
│   └── app/             # Compute (ECS, GKE, etc.)
└── environments/
    ├── staging.tfvars
    └── production.tfvars
```

### Remote state

Always store Terraform state remotely — never commit `terraform.tfstate` to git:

```hcl
terraform {
  backend "s3" {
    bucket         = "myapp-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
  }
}
```

### Key practices

- **Lock provider versions** — use `required_providers` with exact versions
- **Use separate directories for environments** — not `if/else` conditionals in HCL
- **Never store secrets in Terraform** — use `sensitive = true` and inject from Vault or AWS Secrets Manager
- **Run `terraform plan` in CI** — make changes visible before `apply`
- **Protect production state** — state locking via DynamoDB for S3 backend
