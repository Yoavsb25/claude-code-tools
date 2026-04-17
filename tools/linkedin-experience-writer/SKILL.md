---
name: linkedin-experience-writer
description: >
  Writes LinkedIn experience bullets for a single project a tech professional worked on.
  Use this skill whenever the user wants to write, rewrite, update, or improve
  their LinkedIn experience section, work history, or professional accomplishments —
  even if they just say "help me update my LinkedIn" or "write my experience bullets".
  Generates 1-3 bullets covering genuinely distinct aspects of the project, each with
  2 alternative phrasings so the user can pick the one that reads better.
---

# LinkedIn Experience Writer

Your job is to turn a description of one project into 1-3 polished LinkedIn bullets that a
tech professional would be proud to post. Each bullet must cover a **different aspect** of
the project — not the same point in a different tone.

## Step 1: Targeting question

Before anything else, ask:

> "What type of role are you targeting? (e.g., senior IC, engineering lead, startup generalist,
> PM-facing engineer)"

Use this throughout — lean into technical depth for IC roles, ownership/influence framing for
lead roles, breadth for generalist roles.

## Step 2: Source check

Ask:

> "Tell me about the project. Do you have notes, a ticket log, or a doc I can read? If not,
> just describe it — what you built, your specific contribution, and any results you remember."

- If they share files → read them before proceeding
- If verbal → ask up to 2 focused follow-up questions to fill gaps:
  - What was the project trying to solve?
  - What was YOUR specific contribution (not the team's)?
  - Any concrete results (latency, cost, users, time saved, adoption)?

Two rounds max, then move on with what you have.

## Step 3: Aspect extraction

From the project description, identify **1-3 concrete domains of work** the person actually did.
Think in terms of skills a recruiter would recognize: UI design, API development, deployment/CI,
data modeling, system architecture, authentication, testing, etc.

Each bullet should demonstrate a **different capability** — not the same work from a different angle.
Ask yourself: *"Would a recruiter see a distinct skill in each bullet?"* If two bullets would tell
the same story to a hiring manager, merge or drop one.

Only include a domain if there's real content to support it. 1-2 strong bullets beats 3 thin ones.
Don't manufacture bullets to fill the quota — the goal is to show breadth of skills, not volume.

## Step 4: Generate 2 phrasings per bullet

For each aspect, write **exactly 2 alternative phrasings** — same angle, different sentence
structure and flow. Both must stand alone without context.

```
[Strong action verb] [what you did] [context or scale], [result or impact]
```

Good action verbs: led, designed, migrated, shipped, reduced, improved, built, automated,
refactored, integrated, drove, established, cut, scaled, onboarded.

Rules:
- Keep bullets to 1-2 lines (LinkedIn truncates long entries)
- Use `[add metric]` placeholders rather than inventing numbers
- Vary sentence rhythm between Option A and Option B — don't just swap synonyms

Label them:
- **Option A:**
- **Option B:**

## Step 5: Present output + best pick

Group bullets by domain with a short header that names the actual area of work (e.g., **Deployment**, **API Design**, **UI**, **Data Layer**, **Architecture**) — not abstract categories like "Technical" or "Impact".

---
**Technical**

Option A: Redesigned the ingestion pipeline to replace polling with event-driven processing, cutting end-to-end latency by `[add metric]`.

Option B: Built an event-driven ingestion pipeline from scratch, eliminating polling overhead and reducing latency by `[add metric]` across `[N]` upstream sources.

---

After all bullets, add a starred recommendation:

> ⭐ If you only add one bullet: [paste the strongest Option A or B here] — this leads with
> the highest-signal detail for a [targeting role].

End with: "Pick your favorites and fill in any `[add metric]` placeholders. Happy to refine
wording or combine elements from different options."
