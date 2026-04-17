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

## Step 3: Aspect extraction

Identify **1-3 concrete domains of work** the person actually owned. Think in terms that a
recruiter searching LinkedIn would recognize: API development, system architecture, deployment/CI,
data modeling, authentication, ML infrastructure, platform reliability, etc.

Each bullet should demonstrate a **different searchable capability**. Ask yourself: *"If a
recruiter filtered for this skill, would this bullet surface?"* If two bullets would tell
the same story to a hiring manager, merge or drop one.

1-2 strong bullets beats 3 thin ones. Don't manufacture bullets to fill a quota.

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

## Step 5: Write exactly 2 phrasings per bullet

For each aspect, write **exactly 2 alternative phrasings** (Option A and Option B) — same angle,
genuinely different structure and rhythm. Not synonym-swaps.

### Two structures that perform well on LinkedIn

**Result-first** (strongest for impact-heavy achievements — lead with the win):
```
[Outcome with metric] by [action verb + what you did], [context or scale]
```
Example: Cut deployment time by 70% by migrating to ArgoCD-managed GitOps workflows, eliminating manual release steps across 4 engineering teams.

**Action-first** (better when the work itself is the story):
```
[Strong action verb] [what you did + scale], [result or impact]
```
Example: Architected a unified deployment pipeline across 4 microservices teams, cutting release cycle time by 70% and eliminating environment drift.

### Rules
- Keep bullets to 1-2 lines (~150–200 chars) — LinkedIn truncates long entries in preview
- Use `[add metric]` placeholders rather than inventing numbers
- Vary structure between A and B — one result-first, one action-first when both fit
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

Option A: [result-first or action-first phrasing]

Option B: [alternative phrasing with different structure]

---

After all bullets, add a starred recommendation:

> ⭐ If you only add one bullet: [paste the strongest single option here] — this front-loads
> the highest-signal achievement for a [target role] and embeds the keywords recruiters search for.

End with: "Pick your favorites and fill in any `[add metric]` placeholders. Happy to refine
wording or combine elements from different options."
