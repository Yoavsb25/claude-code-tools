---
name: product-manager:user-stories
description: >
  Use when the user wants to break a feature or PRD into user stories, write acceptance criteria,
  create a backlog, or prepare stories for sprint planning. Triggers on: "write user stories",
  "break this into stories", "create acceptance criteria", "I need tickets for this", "decompose
  this feature", "sprint planning", "as a user I want", "backlog refinement", "help me write
  story cards", or when a PRD or feature description exists and needs to be translated into
  actionable development units.
---

# User Stories Sub-Skill

Decompose features or PRDs into well-formed user stories with acceptance criteria. Scales from quick backlog creation to sprint-planning-quality output.

---

## Phase 1 — Intake

Determine what input exists:

**If a PRD or detailed spec is provided**: proceed directly to decomposition using it as the source of truth.

**If only a feature description is provided**: ask two questions before decomposing:
1. Who are the user types involved? (So stories can be properly attributed)
2. What scope are we targeting — quick rough breakdown, or sprint-ready detailed stories?

Why this matters: stories written without a clear user perspective are really just task lists. The persona grounds the "so that" and makes acceptance criteria meaningful.

---

## Phase 2 — Decompose into Epics (if needed)

For features with significant scope (5+ stories), group stories into epics first. An epic represents a coherent user journey or capability area.

```
Epic: [Name]
Description: [What user capability this delivers]
Stories: [Count estimate]
```

For small features (2–4 stories), skip epics and go directly to stories.

---

## Phase 3 — Write User Stories

Use this format for each story:

```
## Story [ID]: [Short title]

**As a** [type of user]
**I want** [to do something]
**So that** [I achieve some goal or value]

**Acceptance Criteria:**
- [ ] AC-1: [Specific, testable condition]
- [ ] AC-2: ...
- [ ] AC-3: ...

**Notes / Assumptions:**
- [Any clarifications, edge cases, or open questions]

**Size estimate:** XS / S / M / L / XL
**Dependencies:** [Story IDs this depends on, if any]
```

**Writing rules:**

| Element | What good looks like | What to avoid |
|---------|----------------------|---------------|
| "As a" | Specific persona from PRD or provided context | "As a user" (too generic) |
| "I want" | Concrete action the user takes | "I want the system to..." (system perspective) |
| "So that" | Business or user value — the why | Restatement of the feature |
| Acceptance criteria | Testable, binary — pass/fail | Vague ("works correctly") |
| Size | Relative, not hours | Precise hour estimates |

Why acceptance criteria matter: stories without ACs create ambiguity about what "done" means. Every AC is a contract between PM, engineer, and QA.

---

## Phase 4 — Optional Task Breakdown

If the user asks for sprint-ready output or says "break this down further", add a task list under each story:

```
**Tasks:**
- [ ] T-1: [Engineering task — specific enough for a developer to start]
- [ ] T-2: ...
```

Tasks are implementation-level. Stories are user-outcome-level. Don't conflate them — tasks belong in the story card, not in the story title.

---

## Phase 5 — Story Map (optional)

If there are 8+ stories across multiple epics, offer a story map summary:

```
| Epic | Story | Priority | Size | Dependencies |
|------|-------|----------|------|--------------|
| [Epic name] | [Story title] | P0 | M | — |
| ...
```

This makes sequencing visible without being a full roadmap.

---

## Phase 6 — Flag Issues

Before closing, check for:

- Stories that are too large (no clear single user action) — suggest splitting
- Missing "so that" value — flag and ask what outcome the user is after
- Acceptance criteria that aren't testable — rewrite or flag
- Stories with no clear owner persona — ask which user this is for

---

## Phase 7 — Offer Next Steps

> "Stories complete. From here:
> - Prioritize and sequence these against other work → use the `roadmap` skill
> - Go back and refine the PRD → use the `prd` skill
> - Or add more detail to specific stories — what would you like?"
