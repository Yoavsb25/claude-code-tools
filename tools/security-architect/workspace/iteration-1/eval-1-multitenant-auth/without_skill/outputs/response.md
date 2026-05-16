# Multi-Tenant SaaS: Auth and Permissions System Design

Designing auth and permissions correctly from the start saves you from the worst kind of refactor: the kind where you have to audit every query and endpoint for data leakage. Here is a practical, battle-tested approach.

---

## 1. Core Mental Model: Three Layers

Every request must pass through three checks in sequence:

1. **Authentication** — Who are you? (valid session/token)
2. **Tenant resolution** — Which company are you acting on behalf of?
3. **Authorization** — Are you allowed to do this action in this tenant?

Never skip or reorder these. Tenant resolution must happen before authorization.

---

## 2. Data Model

### Tenants, Users, and Memberships

```sql
-- The anchor for all tenant data
CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        TEXT UNIQUE NOT NULL,   -- e.g., "acme-corp" for subdomain routing
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Users are global — they exist independently of any tenant
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- Membership table is the join — role lives here, not on the user
CREATE TABLE tenant_memberships (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('admin', 'editor', 'viewer')),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (tenant_id, user_id)   -- one role per user per tenant
);

-- Index for fast lookups in both directions
CREATE INDEX ON tenant_memberships(tenant_id, user_id);
CREATE INDEX ON tenant_memberships(user_id);
```

**Key decisions:**
- Users are global entities. A person can belong to multiple tenants with different roles in each.
- Roles live on the membership, not on the user. Never put `role` or `tenant_id` directly on the users table.
- Soft-delete memberships (add `deleted_at`) rather than hard-deleting if you need audit trails.

### All Tenant Data Must Carry tenant_id

Every table that holds tenant-specific data must have a `tenant_id` foreign key:

```sql
CREATE TABLE projects (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON projects(tenant_id);   -- required for every tenant-scoped table
```

This is non-negotiable. If a table can hold data from multiple tenants, it needs the column and the index.

---

## 3. Authentication

Use JWT or opaque session tokens — either works, but pick one and stick to it.

### JWT (stateless)

The access token payload should include enough to resolve tenant context:

```json
{
  "sub": "user-uuid",
  "email": "alice@example.com",
  "tenant_id": "tenant-uuid",
  "role": "admin",
  "iat": 1716000000,
  "exp": 1716003600
}
```

**Caution:** If you embed `role` in the JWT, role changes don't take effect until the token expires or is refreshed. For most SaaS apps a 15-minute access token is short enough. If roles must revoke instantly, use a short-lived token and validate the role from the database on each request instead of trusting the JWT claim.

### Session tokens (stateful)

Store sessions in Redis or a `sessions` table with `user_id`, `tenant_id`, and an expiry. Slower but simpler to revoke.

### Multi-tenant login flow

```
1. User submits email + password (no tenant selected yet)
2. Look up user by email — verify password
3. Query tenant_memberships for all tenants this user belongs to
4. If one tenant → auto-select it and issue token
5. If multiple tenants → return list, prompt user to pick one
6. Issue token scoped to the selected (user_id, tenant_id) pair
```

This keeps login clean and lets you support the "switch organization" UX later.

---

## 4. Tenant Resolution Middleware

Every authenticated request must resolve the active tenant before hitting any business logic. Do this in middleware, not in individual handlers.

```python
# Example: FastAPI middleware

async def resolve_tenant(request: Request, call_next):
    token = extract_bearer_token(request)
    if not token:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    claims = verify_jwt(token)
    tenant_id = claims.get("tenant_id")
    user_id = claims.get("sub")

    # Optional: validate membership still exists and role hasn't changed
    membership = await db.fetch_one(
        "SELECT role FROM tenant_memberships WHERE tenant_id=$1 AND user_id=$2",
        tenant_id, user_id
    )
    if not membership:
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    # Attach to request state — all downstream code reads from here
    request.state.tenant_id = tenant_id
    request.state.user_id = user_id
    request.state.role = membership["role"]

    return await call_next(request)
```

**The rule:** Never let handlers accept `tenant_id` from the request body or query params. Always take it from `request.state` (or your framework's equivalent). This prevents tenant spoofing.

---

## 5. Authorization: Role-Based Access Control (RBAC)

Define permissions as explicit actions, not just roles. Roles map to permission sets.

```python
# permissions.py

PERMISSIONS = {
    "admin": {
        "project:create",
        "project:read",
        "project:update",
        "project:delete",
        "member:invite",
        "member:remove",
        "member:change_role",
        "billing:manage",
    },
    "editor": {
        "project:create",
        "project:read",
        "project:update",
    },
    "viewer": {
        "project:read",
    },
}

def has_permission(role: str, action: str) -> bool:
    return action in PERMISSIONS.get(role, set())
```

Then in your route handlers:

```python
@router.delete("/projects/{project_id}")
async def delete_project(project_id: UUID, request: Request):
    if not has_permission(request.state.role, "project:delete"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Scope the query — always filter by tenant_id
    project = await db.fetch_one(
        "SELECT * FROM projects WHERE id=$1 AND tenant_id=$2",
        project_id, request.state.tenant_id
    )
    if not project:
        raise HTTPException(status_code=404)

    await db.execute("DELETE FROM projects WHERE id=$1", project_id)
```

Notice the double filter: permission check first, then the database query always includes `AND tenant_id = $current_tenant`. Even if someone passes a valid `project_id` from another tenant, the second filter returns nothing.

### Permission check helper (decorator pattern)

```python
from functools import wraps

def require_permission(action: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request: Request, **kwargs):
            if not has_permission(request.state.role, action):
                raise HTTPException(status_code=403)
            return await func(*args, request=request, **kwargs)
        return wrapper
    return decorator

# Usage
@router.delete("/projects/{project_id}")
@require_permission("project:delete")
async def delete_project(project_id: UUID, request: Request):
    ...
```

---

## 6. Database-Level Tenant Isolation (Defense in Depth)

Application-level filtering is the first line of defense, but add a second one at the database layer.

### Option A: Row-Level Security (PostgreSQL)

```sql
-- Enable RLS on every tenant-scoped table
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

-- Create a policy using a session variable your app sets per connection
CREATE POLICY tenant_isolation ON projects
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- In your app, set the variable at the start of each request's DB transaction:
-- SET LOCAL app.current_tenant_id = '<tenant-uuid>';
```

With RLS, even if a developer forgets to add `WHERE tenant_id = $1` in a query, the database will silently filter the rows. It's a safety net, not a replacement for application-layer filtering.

### Option B: Separate schemas or databases per tenant

Higher isolation, much higher operational overhead. Only consider this for regulated industries (healthcare, finance) where tenants contractually require data separation. For most SaaS, shared schema + RLS is the right trade-off.

---

## 7. API Design Conventions

Follow these patterns consistently so tenant context is never ambiguous:

```
# Always scope resources under the tenant context
GET    /api/v1/tenants/{tenant_id}/projects
POST   /api/v1/tenants/{tenant_id}/projects
GET    /api/v1/tenants/{tenant_id}/projects/{project_id}
DELETE /api/v1/tenants/{tenant_id}/projects/{project_id}

# Members
GET    /api/v1/tenants/{tenant_id}/members
POST   /api/v1/tenants/{tenant_id}/members/invite
DELETE /api/v1/tenants/{tenant_id}/members/{user_id}
```

Even if `tenant_id` is redundant (it's in the token), keeping it in the URL makes the scoping explicit and makes your logs easier to read.

In middleware, validate that the `tenant_id` in the URL matches the one in the token — otherwise a user could craft a request to a tenant they belong to but with a resource path from a different tenant.

---

## 8. Invitation Flow

Users don't create accounts in a vacuum — they get invited:

```
1. Admin sends invite to email@example.com for tenant X
2. System creates pending_invitations record (email, tenant_id, role, token, expires_at)
3. Email sent with link: /accept-invite?token=<secure-random-token>
4. User clicks link:
   a. If no account → create user account
   b. Verify token is valid and not expired
   c. Create tenant_memberships row (tenant_id, user_id, role)
   d. Delete or mark invitation as used
5. Issue auth token and redirect to the tenant workspace
```

Never store the invitation token as plain text — store a hash and compare hashes on lookup.

---

## 9. Common Pitfalls to Avoid

**Putting tenant_id in the request body for write operations.** The tenant always comes from the validated token, never from user-supplied input.

**Forgetting to scope list queries.** `SELECT * FROM projects` with no `WHERE tenant_id = ?` is a data breach waiting to happen. Use a linter or query wrapper that enforces tenant scoping.

**Conflating authentication and authorization.** A valid token proves who you are. It does not prove you can do what you're asking. Always run both checks.

**Storing roles on the users table.** Roles are a property of a membership, not a user. A user who is an admin at company A might be a viewer at company B.

**Giant superuser bypass.** If you build a "platform admin" role (for your own ops team), make it explicit — a separate boolean on the users table (`is_platform_admin`) with its own middleware check. Never reuse tenant roles for this.

**Not indexing tenant_id.** Every query that filters by `tenant_id` will be slow without an index. Add `CREATE INDEX ON <table>(tenant_id)` to every tenant-scoped table, day one.

---

## 10. What to Build First vs. Later

### Build on day one:
- Users, tenants, tenant_memberships schema
- JWT auth with tenant_id + role in claims
- Tenant resolution middleware
- `has_permission()` helper and role definitions
- Database-level RLS (takes one afternoon, saves you from bugs forever)
- Invitation flow

### Add later (after you have real users):
- Fine-grained permissions (e.g., per-resource ACLs where a user can be given access to a specific project regardless of their role)
- Permission inheritance and hierarchies
- Audit log table (`audit_events` with actor, tenant, action, resource, timestamp)
- API key authentication (same middleware, different token format)
- SSO / SAML integration (slot in at the authentication layer, everything else stays the same)

---

## Summary

The architecture that survives growth is built on three pillars:

1. **Membership table owns the role** — never denormalize role onto the user
2. **Middleware owns tenant resolution** — never trust tenant context from the client
3. **Every query is tenant-scoped** — in application code and reinforced by RLS

If you get these three right from the start, adding features (new roles, new resource types, SSO, API keys) is additive. You will never need to rip this out.
