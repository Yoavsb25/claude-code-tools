# Multi-Tenant SaaS: Auth & Permissions Architecture

This question spans **auth-design** (RBAC, tenant isolation) and **threat-modeling** (what breaks if you get this wrong). I'll cover both — threat model first, because it shapes every other decision.

---

## 1. Threat Model

### What you're protecting

| Asset | Why it matters |
|-------|---------------|
| Tenant data (rows, files, configs) | Core product — a tenant seeing another tenant's data is a critical breach |
| User credentials | Account takeover, cascading access to tenant data |
| Role assignments | Privilege escalation within or across tenants |
| Admin/super-admin access | Full-system compromise |
| Audit logs | Tamper = inability to detect or prove breaches |

### Trust boundaries

```
[Public internet]
      │
      ▼
[API Gateway / Auth middleware]   ← Unauthenticated → authenticated
      │
      ▼
[App server — resolves tenant + user context]  ← User → admin escalation
      │
      ▼
[Database layer with tenant_id enforcement]    ← App → DB trust boundary
      │
      ▼
[Third-party services (email, storage, etc.)]  ← Your data → vendor boundary
```

Every arrow is a potential attack vector. The most dangerous: the app-to-database boundary, because if your app layer fails to enforce `tenant_id`, your DB will happily return any row.

### STRIDE Analysis

| Component | Threat | Likelihood | Impact | Priority |
|-----------|--------|------------|--------|----------|
| Tenant data access | **IDOR / tenant data leak** — querying without `tenant_id` filter | High | Critical | P0 |
| Role assignments | **Elevation of privilege** — user promotes themselves to admin | Med | High | P1 |
| Auth tokens | **Spoofing** — forged or replayed JWT | Med | High | P1 |
| Role checks | **Tampering** — role claim modified in client-side token | Med | High | P1 |
| Audit logs | **Repudiation** — user denies sensitive action, no log exists | Med | Med | P2 |
| Login endpoint | **Credential stuffing / brute force** | High | Med | P2 |
| API | **Broken access control** — missing authz check on one endpoint | High | High | P1 |

**P0 focus**: Tenant data leakage. This is the canonical failure mode in multi-tenant systems — missing or bypassable `tenant_id` scoping at the data layer.

---

## 2. Data Model — Get This Right First

The entire auth system depends on your data model. Retrofit is expensive.

### Core tables

```sql
-- Tenants (companies)
CREATE TABLE tenants (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug        TEXT UNIQUE NOT NULL,       -- e.g. "acme-corp" (for subdomain routing)
  name        TEXT NOT NULL,
  plan        TEXT NOT NULL DEFAULT 'free',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Users (exist independently of tenants — one user can belong to multiple tenants)
CREATE TABLE users (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email        TEXT UNIQUE NOT NULL,
  password_hash TEXT,                     -- null if SSO-only
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Memberships — the join table that carries the role
CREATE TABLE tenant_memberships (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role       TEXT NOT NULL CHECK (role IN ('admin', 'editor', 'viewer')),
  invited_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, user_id)             -- one role per user per tenant
);

-- Index for the hot path: "what role does this user have in this tenant?"
CREATE INDEX ON tenant_memberships (tenant_id, user_id);
```

**Why users are independent of tenants**: A user can be a member of multiple tenants (e.g., a consultant). Tying `tenant_id` to the users table forces account duplication. Separate them.

**Why role lives on the membership, not the user**: Role is contextual — the same person is an admin in one company and a viewer in another.

---

## 3. Authentication

### Recommendation: Use a managed auth provider

Don't implement your own. Use **Clerk**, **Auth0**, or **Supabase Auth**. Reasons:
- MFA, SSO/SAML, magic links, passkeys — handled without custom code
- Security patches are the provider's problem, not yours
- Enterprise customers will ask for SSO — Clerk and Auth0 support it on paid plans

If you must implement yourself, follow JWT design below.

### JWT design (if self-implementing)

- Sign with **RS256** (asymmetric) — your auth service signs, your app services only need the public key
- **Access token TTL**: 15 minutes
- **Refresh token**: long-lived (30 days), stored in `HttpOnly; Secure; SameSite=Strict` cookie, rotated on every use (refresh token rotation)
- Store access tokens in **memory only** — never `localStorage` (XSS risk)
- Validate on every request: signature, `exp`, `iss`, `aud`

### What goes in the JWT

```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "iss": "https://auth.yourdomain.com",
  "aud": "https://api.yourdomain.com",
  "exp": 1716000000,
  "iat": 1715999100
}
```

**Do not put the role or tenant_id in the JWT.** Roles are resolved server-side on each request. If you embed roles in the token, you can't revoke them without invalidating the token — and you create a path for tampering (if the client can influence what goes in the token).

---

## 4. Tenant Resolution

Every API request must establish two things before authorization: **who** (user identity) and **which tenant** (context). These must be resolved independently and never trusted from client input.

### Resolution strategies

**Option A — Subdomain routing** (recommended for B2B SaaS):
```
acme.yourapp.com → tenant_slug = "acme"
```
- Look up `tenant_id` from `slug` on every request
- Never accept `tenant_id` as a query param or request body field

**Option B — Path prefix**:
```
yourapp.com/t/acme/dashboard → tenant_slug = "acme"
```

**Option C — JWT claim** (only valid if the token is short-lived and server-issued):
- Acceptable if the token TTL is ≤15 min and you trust your issuance process
- Still verify membership server-side — don't rely solely on the claim

### Middleware pattern

```python
def resolve_request_context(request):
    # Step 1: Authenticate — who is this user?
    user = verify_jwt(request.headers["Authorization"])
    if not user:
        raise Unauthorized()

    # Step 2: Resolve tenant — which company is this request for?
    tenant_slug = extract_tenant_from_subdomain(request.host)
    tenant = db.get_tenant_by_slug(tenant_slug)
    if not tenant:
        raise NotFound("Tenant not found")

    # Step 3: Authorize — is this user a member of this tenant?
    membership = db.get_membership(tenant_id=tenant.id, user_id=user.id)
    if not membership:
        raise Forbidden("Not a member of this organization")

    # Attach to request context — everything downstream uses this
    request.ctx.user = user
    request.ctx.tenant = tenant
    request.ctx.role = membership.role  # 'admin' | 'editor' | 'viewer'
```

This runs on every authenticated request. No endpoint should resolve tenant or role itself — it comes from context.

---

## 5. Authorization (RBAC)

### Role definitions

Define roles explicitly and exhaustively. Don't leave them implicit.

| Permission | viewer | editor | admin |
|-----------|--------|--------|-------|
| Read resources | yes | yes | yes |
| Create / update resources | no | yes | yes |
| Delete resources | no | no | yes |
| Manage members | no | no | yes |
| Change billing | no | no | yes |
| Invite users | no | no | yes |
| View audit logs | no | no | yes |
| Change member roles | no | no | yes |

### Enforcement — three layers

**Layer 1: Service/API layer** (primary enforcement)

```python
def require_permission(permission: str):
    def decorator(handler):
        def wrapper(request, *args, **kwargs):
            role = request.ctx.role
            if not ROLE_PERMISSIONS[role].get(permission):
                raise Forbidden(f"Role '{role}' cannot '{permission}'")
            return handler(request, *args, **kwargs)
        return wrapper
    return decorator

ROLE_PERMISSIONS = {
    "viewer": {"read": True},
    "editor": {"read": True, "write": True},
    "admin":  {"read": True, "write": True, "delete": True, "manage_members": True},
}

@require_permission("delete")
def delete_resource(request, resource_id):
    # tenant_id is always taken from context, never from request body
    resource = db.get_resource(
        id=resource_id,
        tenant_id=request.ctx.tenant.id  # always scoped
    )
    ...
```

**Layer 2: Database query scoping** (defense in depth)

Every query that retrieves tenant data includes `tenant_id`:

```python
# WRONG — leaks data across tenants if service layer has a bug
resource = db.query("SELECT * FROM resources WHERE id = ?", resource_id)

# CORRECT — enforces at query level too
resource = db.query(
    "SELECT * FROM resources WHERE id = ? AND tenant_id = ?",
    resource_id, request.ctx.tenant.id
)
```

Even if your service layer has a bug, the query won't return another tenant's row.

**Layer 3: UI** (non-authoritative, UX only)

Hide buttons and navigation for unauthorized actions. Never rely on this for security — it's just UX. The API enforces the actual rule.

### Admin self-demotion / tenant lockout protection

Prevent an admin from demoting themselves if they're the last admin:

```python
def change_member_role(tenant_id, target_user_id, new_role, actor):
    require_permission("manage_members", actor)
    
    if actor.id == target_user_id and new_role != "admin":
        admin_count = db.count_admins(tenant_id)
        if admin_count <= 1:
            raise BadRequest("Cannot remove last admin from tenant")
    
    db.update_membership_role(tenant_id, target_user_id, new_role)
```

---

## 6. Data Access Pattern Summary

The golden rule: **tenant_id always comes from authenticated context, never from request input**.

```
Request arrives
  → Auth middleware validates JWT → sets user in context
  → Tenant middleware resolves tenant from subdomain → sets tenant in context
  → Membership middleware checks user∈tenant → sets role in context
  → Role middleware checks required permission for this endpoint
  → Handler runs, queries DB with tenant_id from context
  → Response
```

Any deviation from this chain — e.g., accepting `?tenant_id=` from a query param — creates an IDOR vector.

---

## 7. Audit Logging

Log every security-relevant action from day one. Retrofitting audit logs is painful (you lose history).

### What to log

```python
audit_events = [
    "user.login",
    "user.login_failed",
    "user.logout",
    "member.invited",
    "member.role_changed",
    "member.removed",
    "resource.created",
    "resource.deleted",
    "billing.changed",
    "tenant.settings_changed",
]
```

### Log structure

```json
{
  "event":     "member.role_changed",
  "tenant_id": "uuid",
  "actor_id":  "uuid",
  "target_id": "uuid",
  "before":    "editor",
  "after":     "admin",
  "ip":        "1.2.3.4",
  "user_agent": "...",
  "timestamp": "2026-05-16T10:30:00Z"
}
```

- Write to an append-only store (or a table where rows are never updated/deleted)
- Admins can read their own tenant's audit log — never another tenant's
- Retain for minimum 90 days; 1 year if you're aiming for SOC2

---

## 8. Invitation Flow

Member invitations are a common auth weakness. Design this carefully.

```
Admin invites user@example.com
  → Generate signed invite token (JWT or random token in DB), expires 48h
  → Send email with link: https://app.yourdomain.com/invite/<token>
  → User clicks link:
      if user account exists → auto-join tenant with invited role
      if no account → register flow, then auto-join
  → Invalidate token on use (single-use)
  → Log: member.invited, member.joined
```

Security controls:
- Tokens expire (48h max)
- Tokens are single-use — delete on consumption
- Only admins can invite
- An invitation does not grant access until the user accepts it

---

## 9. Super-Admin (Your Internal Team)

You'll need a way for your team to access any tenant for support. Design this deliberately — don't leave it ad-hoc.

Options:
- **Separate admin application** (recommended) — internal tool on a separate domain, requires VPN, separate credential set
- **Support role** in the membership table — your staff can be added as a special `support` role with read-only access and mandatory audit logging of every action

Never give your engineers direct database access in production without an audit trail. Every "I just needed to check something" query is a liability.

---

## 10. Implementation Checklist

### Before you write the first feature

- [ ] `tenants`, `users`, `tenant_memberships` tables created with proper constraints
- [ ] Auth middleware extracts and validates JWT on every request
- [ ] Tenant middleware resolves tenant from subdomain (not request body)
- [ ] Membership check confirms user belongs to resolved tenant
- [ ] `tenant_id` never accepted as user input — always from context
- [ ] Role permissions table defined exhaustively

### Before you ship to customers

- [ ] Every DB query for tenant data includes `AND tenant_id = ?` from context
- [ ] Audit log table created; key events are logged
- [ ] Invitation flow uses expiring single-use tokens
- [ ] Last-admin protection implemented
- [ ] Rate limiting on login endpoint (5 attempts → exponential backoff)
- [ ] Passwords hashed with bcrypt (cost ≥12) or Argon2id
- [ ] MFA offered (required for admins if you can enforce it)
- [ ] Penetration test: attempt to access Tenant B's data as a Tenant A user — this should 404, not 403 (don't leak tenant existence)

### Before enterprise customers ask

- [ ] SSO/SAML support (use a managed provider — don't implement yourself)
- [ ] Audit log export for compliance
- [ ] Role-level access reviews (quarterly)
- [ ] SOC2 Type I scoping discussion

---

## Key Architectural Decisions (Summarized)

| Decision | Recommendation | Rationale |
|----------|----------------|-----------|
| Users vs memberships | Separate `users` + `tenant_memberships` tables | One person, multiple companies; role is contextual |
| Role storage | In `tenant_memberships`, NOT in JWT | Roles change; JWT claims persist until expiry |
| Tenant resolution | From subdomain only, not request params | Prevents IDOR via URL manipulation |
| Authorization enforcement | Service layer (primary) + DB query (defense in depth) | Layered — one layer's bug doesn't equal full exposure |
| Auth provider | Managed (Clerk / Auth0) unless strong reason not to | Solves MFA, SSO, security patches — not worth reinventing |
| Audit logging | From day one, append-only | Retrofit is painful; you lose history |

The most important thing to get right before writing any feature code: the data model and the middleware chain. Everything else can be iteratively improved — those two are load-bearing.
