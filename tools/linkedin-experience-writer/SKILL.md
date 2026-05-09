---
name: linkedin-experience-writer
description: >
  Writes polished LinkedIn experience bullets for a tech professional's job experience section,
  optimized for recruiter engagement and LinkedIn search visibility.
  Use this skill whenever the user wants to write, rewrite, update, or improve their LinkedIn
  experience section, work history, or professional accomplishments — even if they just say
  "help me update my LinkedIn", "write my experience bullets", "make this sound better for
  LinkedIn", or "turn my notes into LinkedIn bullets".
  Generates 1-3 bullets per project covering genuinely distinct aspects, each with 2 alternative
  phrasings so the user can pick the one that reads better.
---

# LinkedIn Experience Writer

Your job is to turn a project description into polished LinkedIn bullets that stop a recruiter
mid-scroll. Recruiters spend ~6 seconds on an initial profile scan — the first 2 bullets
determine whether they keep reading. Every word choice must earn its place.

## Step 1: Targeting question

Before anything else, ask:

> "What type of role are you targeting? (e.g., senior IC, engineering lead, staff/principal,
> startup generalist, PM-facing engineer)"

This shapes vocabulary throughout — not just tone, but the specific words you choose:

| Role tier | Lead with | Power words to use |
|-----------|-----------|-------------------|
| Senior IC | Technical depth, ownership of hard problems | architected, designed, owned, shipped, optimized |
| Engineering lead | People leverage, cross-team influence | drove, aligned, scaled, enabled, championed, spearheaded |
| Staff/Principal | Org-wide impact, technical strategy | established, defined, led, transformed, shaped, standardized |
| Startup generalist | Breadth, speed, 0→1 delivery | built from scratch, launched, wore multiple hats, moved fast |
| PM-facing | Business outcomes, stakeholder communication | partnered, translated, prioritized, delivered, accelerated |

## Step 2: Source check

Ask:

> "Tell me about the project. Do you have notes, a ticket log, or a doc I can read? If not,
> just describe it — what you built, your specific contribution, and any results you remember."

- If they share files → read them before proceeding
- If verbal → ask up to 2 focused follow-up questions:
  - What was YOUR specific contribution (not the team's)?
  - Any concrete results? (latency, cost savings, revenue, users, time saved, adoption rate)

Two rounds max, then move on with what you have.

### Two-source synthesis (project context + work logs)

If the user provides both **project context docs** (architecture write-ups, initiative summaries) AND **work logs** (Jira reports, sprint summaries), use them differently:

| Source | Extract |
|--------|---------|
| Project context docs | Architecture decisions, design intent ("why it exists"), tech stack, your specific role, impact numbers |
| Work logs (Jira/sprint) | Scale signals (component counts, repo counts, ticket velocity), which epics shipped, temporal scope |

Bullets are built from project context (substance) + validated/scaled by work logs (scope). Don't write bullets from work logs alone — ticket titles are too shallow. Don't ignore work logs — they're where the concrete scale numbers live.

**Reading order**: project context first (understand what was built and why), then work logs (extract scale, confirm what shipped).

## Step 3: Aspect extraction

For each project or domain, identify **at least 2 genuinely distinct aspects** the person owned.
Think in terms a recruiter would search: system architecture, frontend/UI, backend services,
CI/CD pipeline, testing strategy, data modeling, authentication, ML integration, platform
reliability, release automation, developer experience, etc.

**Minimum 2 bullets per project — no exceptions.** Each bullet must showcase a different
searchable capability. Ask yourself: *"Could each bullet surface from a completely different
recruiter search query?"* If two bullets would answer the same query, they are the same bullet —
reframe one to cover a genuinely different skill.

Examples of distinct aspects for a full-stack solo project:
- System architecture / backend design
- Frontend / UI built
- CI/CD pipeline and deployment
- Testing strategy (unit, E2E, automation gates)
- AI/ML integration

**Do not combine** multiple distinct skills into one mega-bullet to stay brief. A recruiter
searching "Kubernetes" needs a bullet about deployment; one searching "React" needs a frontend
bullet. The same mega-bullet won't surface for both.

## Step 4: Diagnose and fix weak language

Before writing, scan the raw input for passive or junior-signaling language and reframe it:

| Weak (avoid) | Strong (use instead) |
|-------------|---------------------|
| helped / assisted | owned / led / drove |
| participated in | spearheaded / championed |
| contributed to | designed / built / shipped |
| worked on | architected / implemented / delivered |
| responsible for | owned / accountable for |
| supported | enabled / unblocked / scaled |

If the input contains weak language, use the stronger framing — don't just preserve what was given.

## Step 5: Write bullets — at least 2 per project, 2 phrasings each

For each project, produce **at least 2 bullets** — one per distinct aspect identified in Step 3.
For each bullet, write **exactly 2 alternative phrasings** (Option A and Option B): same angle,
genuinely different structure and rhythm. Not synonym-swaps.

**The 2 phrasings are alternative wordings of the same bullet. The 2+ bullets are different
skills entirely.** Do not confuse the two — Option A and Option B for bullet 1 should both be
about architecture; bullet 2's Option A and Option B should both be about the frontend. They are
not interchangeable across bullets.

### Three structures that perform well on LinkedIn

**Action + purpose** (default for platform, infrastructure, and architectural work — the capability is the story):
```
[Strong action verb] [what you built + scale], [purpose/capability enabled] (Stack)
```
Example: Designed a dual-routing architecture with a centralized component registry, enabling incremental component migration without disrupting weekly release cadence (Python, GitHub Actions, Kargo).

Scale belongs in the action clause, not the result: "supporting 29 components", "across 14 repositories", "handling 6-service monorepo" — embed it in what you built.

**Action-first with result** (use when you have a concrete outcome metric or a clean before/after):
```
[Strong action verb] [what you built + scale], [measurable result or impact] (Stack)
```
Example: Architected a unified deployment pipeline across 4 microservices teams, eliminating all manual release steps and reducing deployment time by 70% (Python, ArgoCD, GitHub Actions).

**Result-first** (use when the metric is the headline — reserved for strong, credible numbers):
```
[Outcome with metric] by [action verb + what you did], [context or scale] (Stack)
```
Example: Cut deployment time by 70% by migrating to ArgoCD-managed GitOps workflows across 4 engineering teams (Python, ArgoCD, GitHub Actions).

**Choosing A vs B:**
- Option A: action + purpose (or action-first with result if strong metric exists)
- Option B: different angle on the same aspect — reframe mechanism vs. capability, or scale vs. architectural decision
- If no metric available, write both as action + purpose with different emphasis; do NOT add `[add metric]` placeholders to architectural bullets where the capability itself is the value

### Rules

**Brevity — less is more when material is rich:**
- One clean purpose clause beats a list of technical details. When you have a lot of source material, your job is to edit down, not pack in.
- If a bullet feels crowded, you're trying to fit too much into one point — split it instead (see below).
- Lean stack tags: pick 2–3 most searchable technologies, not everything used. `(TypeScript, Docker)` beats `(React, TypeScript, Express, Node.js, Octokit, Docker, Kubernetes)`.

**One project = many bullets:**
- There is no limit to how many bullets a single project can generate. If a project has 3 genuinely distinct aspects (architecture, AI integration, CI/CD pipeline), write 3 bullets — don't compress them into one.
- The test: each bullet should be able to stand alone. If removing one bullet would make the others feel complete, it's redundant. If removing it would leave a gap, keep it.

**Other rules:**
- Keep bullets to 1-2 lines (~150–200 chars) — LinkedIn truncates long entries in preview
- **End every bullet with the tech stack in parentheses**: `(Python, GitHub Actions, Postgres)` — these are the keywords recruiters filter on
- Include concrete scale when available (number of services, repos, components, teams) — specificity signals seniority even without business metrics
- Use `[add metric]` placeholders only for product/feature bullets where a metric would materially strengthen — never on platform/infrastructure/architectural bullets where the capability is the point
- Embed searchable technical keywords naturally (e.g., "ArgoCD", "Kubernetes", "React", "Postgres") — these are what recruiters type into LinkedIn search
- Never start two bullets in the same role with the same verb
- Never use: helped, participated, contributed to, worked on, responsible for, supported

Label them:
- **Option A:**
- **Option B:**

## Step 6: Order and present output

Group bullets by domain with a short header naming the actual area of work (e.g., **Deployment**,
**API Design**, **Data Layer**, **Reliability**, **Architecture**). Avoid abstract labels like
"Technical" or "Impact".

**Order matters**: put the highest-signal bullet first — that's the one recruiter sees before scrolling.

Output format:

---
**[Domain]**

*[Aspect 1 — e.g., Architecture / Backend]*

Option A: [action-first phrasing] (Stack)

Option B: [result-first phrasing, or different angle] (Stack)

*[Aspect 2 — e.g., Frontend / UI]*

Option A: [action-first phrasing] (Stack)

Option B: [result-first phrasing, or different angle] (Stack)

*(add more aspects if the person owned genuinely distinct areas)*

---

After all bullets, add a starred recommendation:

> ⭐ If you only add one bullet: [paste the strongest single option here] — this front-loads
> the highest-signal achievement for a [target role] and embeds the keywords recruiters search for.

End with: "Pick your favorites and fill in any `[add metric]` placeholders. Happy to refine
wording or combine elements from different options."
