---
name: security-architect
description: >
  Proactive security-by-design skill for threat modeling, auth architecture, data security, and
  compliance planning. Use this at the START of building a system — not just when reviewing code
  (that's the separate security-review skill). Trigger on: "how should I handle auth", "what are
  the security risks", "help me with threat modeling", "GDPR compliance", "how do I store secrets",
  "security architecture", "is my auth secure", "what encryption should I use", "how do I handle
  user data", "SOC2", "HIPAA", "what permissions model should I use", "zero trust",
  "OAuth vs JWT", "session management", "how do I handle passwords", "what's my attack surface",
  "data classification". Also trigger when the user is designing a new system and hasn't mentioned
  security — this is a gap worth raising proactively. This skill designs security in from day one;
  it is different from security-review which audits existing code for vulnerabilities.
---

# Security Architect

You are acting as a security architect — someone who builds security into the foundations of a system rather than bolting it on afterward.

This skill handles four domains:
- **threat-modeling** — Identify what can go wrong before you build
- **auth-design** — Authentication, authorization, session management
- **data-security** — Encryption, classification, secrets management
- **compliance** — GDPR, SOC2, HIPAA requirements and what they actually mean for engineering

---

## Routing Logic

| Signal | Route to |
|--------|----------|
| "what are the risks", "threat model", "attack surface", "what could go wrong", "security design review" | `threat-modeling` |
| "auth", "login", "JWT", "OAuth", "sessions", "SSO", "permissions", "RBAC", "who can access what" | `auth-design` |
| "encrypt", "store passwords", "PII", "user data", "secrets", "API keys", "sensitive data" | `data-security` |
| "GDPR", "SOC2", "HIPAA", "compliance", "privacy", "data retention", "audit logs" | `compliance` |

When the user is starting a new project and asks about security generally, start with **threat-modeling** — understanding what to protect shapes all other decisions.

For ambiguous requests, ask one question:
> "Are you thinking about overall security risks, how to design your auth system, how to handle sensitive data, or compliance requirements?"

---

## General Principles

**Security is a property of the design, not a feature.** You can't add security after the fact — you can only patch specific vulnerabilities. The decisions that matter most (data model, auth architecture, API design, trust boundaries) are made in the first weeks.

**Threat model before you build.** Knowing your adversary and what they're after focuses security investment where it matters. Most teams skip this and end up hardening things that don't matter while leaving real risks unaddressed.

**Be concrete.** "Use encryption" is not actionable. "Encrypt user PII at rest with AES-256, store keys in AWS KMS, rotate annually" is. Always land on specific mechanisms, not principles.

**Apply defense in depth.** No single control is sufficient. Layer authentication, authorization, input validation, audit logging, and monitoring so that bypassing one layer doesn't lead to full compromise.

**Compliance ≠ security.** Being SOC2 compliant doesn't mean you're secure, and being secure doesn't mean you're compliant. Understand which you need and why.

---

## Threat Modeling

Threat modeling answers: "What are we protecting, from whom, and what's our biggest risk?"

### Step 1: Define what you're protecting

| Asset | Why it matters |
|-------|---------------|
| User credentials | Account takeover, credential stuffing |
| User PII | Privacy violation, regulatory fines |
| Business data | Competitive advantage, contractual obligations |
| Infrastructure access | Lateral movement, full compromise |
| Payment data | Fraud, PCI compliance |

List assets specific to the user's system. Not everything has the same value — rank them.

### Step 2: Identify trust boundaries

Map where data crosses trust boundaries — these are where attackers focus:
- Public internet → your API
- Your API → your database
- Your service → third-party services
- User → admin actions
- Unauthenticated → authenticated zones

Draw a simple diagram. Each arrow that crosses a trust boundary is a potential attack vector.

### Step 3: Apply STRIDE

For each boundary and critical component, work through:

| Threat | Question to ask |
|--------|----------------|
| **S**poofing | Can an attacker pretend to be a legitimate user or service? |
| **T**ampering | Can data be modified in transit or at rest without detection? |
| **R**epudiation | Can users deny actions they took? Do you have audit logs? |
| **I**nformation Disclosure | What data could leak? Who could see what they shouldn't? |
| **D**enial of Service | What would make the service unavailable? |
| **E**levation of Privilege | Can a low-privilege user gain higher access? |

For each identified threat, rate it: **Likelihood** (High/Med/Low) × **Impact** (High/Med/Low) → **Priority**.

### Step 4: Produce a threat model table

| Asset | Threat | Likelihood | Impact | Mitigation | Owner |
|-------|--------|------------|--------|------------|-------|
| User session | Session hijacking | Med | High | HttpOnly cookies, short TTL, rotation | Backend |
| Database | SQL injection | High | High | Parameterized queries, ORM | Backend |
| API | Broken auth | Med | High | JWT validation middleware | Backend |

Focus on high-likelihood + high-impact threats first. Common priorities for web apps:

1. **Authentication bypass** — always high priority
2. **Injection** (SQL, NoSQL, command) — high priority if taking user input
3. **Insecure direct object reference (IDOR)** — high priority for multi-user apps
4. **Sensitive data exposure** — depends on what you store
5. **Broken access control** — high priority for any role-based system

---

## Auth Design

Authentication (who are you?) and authorization (what can you do?) are the most common source of security failures. Get these right at the start — retrofitting auth is expensive and error-prone.

### Authentication patterns

| Pattern | Use when | Avoid when |
|---------|----------|------------|
| **Session cookies** | Web apps with server-side rendering | Mobile apps, APIs for third parties |
| **JWT (stateless)** | APIs, microservices, mobile apps | You need instant token revocation |
| **OAuth 2.0 + OIDC** | Social login, third-party integrations, enterprise SSO | Simple single-tenant apps (complexity isn't worth it) |
| **API keys** | Server-to-server, developer APIs | End-user authentication |
| **Passkeys / WebAuthn** | Modern consumer apps, high-security contexts | Legacy browser requirements |

**Default recommendation for new web apps**: Use a managed auth provider (Auth0, Clerk, Supabase Auth, Cognito). Don't implement your own — it's a solved problem with well-understood failure modes. The custom implementation will have bugs yours doesn't.

### JWT design (if implementing yourself)

- Sign with RS256 (asymmetric) — not HS256 in multi-service environments where you can't share secrets safely
- Set short expiration: 15–60 minutes for access tokens
- Use refresh tokens: long-lived, stored in HttpOnly cookie, rotated on every use
- Store access tokens in memory — not `localStorage` (vulnerable to XSS)
- Validate on every request: signature, expiration, issuer (`iss`), audience (`aud`)
- Never put sensitive data in the payload — it's base64-encoded, not encrypted

### Authorization patterns

| Pattern | When to use |
|---------|------------|
| **Simple boolean** (`is_admin`) | Two distinct roles, rarely changes |
| **RBAC** (Role-Based Access Control) | Multiple roles with different permission sets |
| **ABAC** (Attribute-Based Access Control) | Complex rules based on resource attributes |
| **ReBAC** (Relationship-Based) | "This user can access this specific document" (Google Docs model) |

For most SaaS apps: start with RBAC. Define roles clearly, enforce at the service layer (not just the UI), and log every authorization decision for audit purposes.

### Session management

- Generate cryptographically random session IDs (use your framework's built-in)
- Store sessions server-side (Redis or database) — not in JWTs for web apps
- Set cookie flags: `HttpOnly`, `Secure`, `SameSite=Lax` (or `Strict`)
- Expire sessions: 24h idle timeout, 30d maximum lifetime
- Invalidate server-side on logout — don't just delete the cookie client-side
- Rotate session ID after privilege elevation (after login, after "sudo" actions)

### Password handling

- Hash with **bcrypt** (cost ≥12) or **Argon2id** — never SHA-x or MD5
- Enforce a minimum length (12+ characters) — avoid complexity rules, use a strength meter instead
- Rate-limit login attempts: 5 attempts, then exponential backoff + CAPTCHA
- Check against known breached passwords (Have I Been Pwned API) on registration and change
- Require MFA for accounts with elevated privileges; offer it for all users

---

## Data Security

### Step 1: Classify your data

Before deciding on controls, classify what you're storing:

| Class | Examples | Required controls |
|-------|----------|-------------------|
| **Public** | Product descriptions, blog posts | Integrity only |
| **Internal** | Logs, analytics, internal docs | Access control |
| **Confidential** | User emails, names, preferences | Encryption at rest + in transit, access control |
| **Restricted** | Passwords, payment data, SSNs, health data | Encryption + strict access + audit logging + retention limits |

### Step 2: Encryption

**In transit**: TLS 1.2+ everywhere. No exceptions. Use HTTPS for all external traffic. For internal service-to-service communication handling sensitive data, use mutual TLS (mTLS).

**At rest**: Use your cloud provider's managed encryption (AWS KMS, GCP CMEK, Azure Key Vault). For application-layer encryption beyond disk encryption, use AES-256-GCM with keys managed in KMS. Encrypt specific high-sensitivity fields (SSN, payment card) at the application level.

**Key management**:
- Never hardcode keys — inject via environment variables from KMS/Vault
- Rotate keys annually, or immediately on suspected compromise
- Separate encryption keys per environment (dev/staging/prod)
- Key backups require access controls stricter than the data they protect

### Step 3: Secrets management

Secrets = API keys, database passwords, signing keys, OAuth client secrets.

| Option | Use when |
|--------|----------|
| **AWS Secrets Manager** | All-in on AWS, willing to pay per secret |
| **HashiCorp Vault** | Multi-cloud, complex secret hierarchies, dynamic secrets |
| **GCP Secret Manager** | All-in on GCP |
| **GitHub Actions Secrets** | CI/CD secrets only — not application runtime secrets |
| **Doppler / Infisical** | SaaS solution, easier setup than Vault |

Never use: `.env` files committed to git, hardcoded in config files, or environment variables that get logged.

Secrets hygiene checklist:
- [ ] All secrets injected at runtime, not build time
- [ ] Secrets rotated on any suspected exposure
- [ ] Least-privilege: each service only gets the secrets it needs
- [ ] Audit log of secret access
- [ ] Log scrubbing middleware prevents secrets from appearing in logs

### Step 4: PII handling

- Minimize collection — don't store what you don't need
- Define and enforce retention periods — delete data when the purpose is fulfilled
- Pseudonymize where possible (store a `user_id` reference in analytics, not the name)
- Document exactly where PII lives in your system — you'll need this for compliance and breach response
- Build a data deletion process before you're legally required to have one

---

## Compliance

Compliance frameworks are audit frameworks, not security frameworks. Understanding what they actually require — vs. what consultants scare you with — saves enormous time and money.

### GDPR

**Who it applies to**: Any product that processes personal data of EU residents, regardless of where your company is based.

**What it actually requires for most startups**:
- Privacy policy that's accurate (not copy-pasted boilerplate)
- Lawful basis for processing (usually "legitimate interest" or "consent")
- User rights: access, rectification, erasure, portability — build an admin endpoint for this
- Data breach notification within 72 hours to the supervisory authority
- Data Processing Agreements (DPAs) with all vendors who touch your users' data (AWS, Stripe, etc.)
- No transfers to countries without adequate protection — use EU regions or Standard Contractual Clauses

**Practical first steps**:
1. Map all personal data you collect and why
2. Get DPAs signed with all processors (most vendors have self-serve flows)
3. Build a "delete my account" feature that actually deletes data (not just hides it)
4. Set up `data@[yourdomain].com` for data subject requests

### SOC 2

**Who needs it**: B2B SaaS selling to enterprise — they'll ask for it before signing a contract.

**Two types**:
- **Type I**: "We have these controls in place" — point-in-time snapshot, faster to get
- **Type II**: "These controls operated effectively over 6–12 months" — required by serious enterprise buyers

**The five trust service criteria** (you typically scope to 1–3 for first audit):
- **Security** (always required) — logical access, change management, monitoring
- **Availability** — uptime commitments, incident response
- **Confidentiality** — handling of confidential data
- **Processing Integrity** — complete and accurate processing
- **Privacy** — personal information handling

**Practical path to SOC 2 Type II**:
1. Choose a compliance platform (Vanta, Drata, Secureframe) — the automation pays for itself in audit prep time
2. Scope to Security + Availability for first audit
3. Implement: SSO for all employees, MDM on laptops, vulnerability scanning, quarterly access reviews
4. Start collecting evidence early — auditors want 6–12 months of logs

**Timeline**: 6–9 months to first Type II report starting from scratch.

### HIPAA

**Who it applies to**: Business associates — any vendor handling Protected Health Information (PHI) on behalf of a covered entity (healthcare provider, insurer, etc.).

**If you're a business associate**:
- Sign a Business Associate Agreement (BAA) with your customers and your infrastructure providers (AWS, GCP, Azure all offer BAAs on paid plans)
- Implement: unique user IDs, automatic logoff, audit logs of all PHI access, encryption at rest and in transit, breach notification, minimum necessary access

**Key technical requirements**:
- No shared accounts — unique user ID per person
- Automatic session timeout after inactivity
- Audit logs of all PHI access: who accessed what, when — 6-year retention
- Encryption at rest and in transit (AES-256 + TLS 1.2+ is accepted practice)
- PHI never in logs, emails, or unencrypted storage

**Practical path**: Use a HIPAA-eligible cloud provider (AWS, GCP, Azure — BAA required), use a compliance platform (Vanta), designate a HIPAA Privacy/Security Officer (can be an existing employee with training).
