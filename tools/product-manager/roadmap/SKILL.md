---
name: product-manager:roadmap
description: >
  Use when the user wants to prioritize features, reason about effort vs. impact trade-offs,
  decide what to build first, validate a proposed sequence, or produce a roadmap artifact.
  Triggers on: "help me prioritize", "what should we build first", "does this order make sense",
  "roadmap planning", "sequence these features", "effort vs impact", "what's the MVP", "how should
  we phase this", "should we build X or Y first", "rank these features", "quarterly roadmap",
  "make a roadmap", or any request involving prioritization logic, build-vs-defer decisions,
  or roadmap creation. Also triggers when a user presents a list of features and asks for a
  strategic perspective on ordering or scope.
---

# Roadmap Sub-Skill

Help prioritize features, reason through trade-offs, and produce a roadmap artifact. Works in two modes: **discovery** (what should we build?) and **validation** (does this order make sense?).

---

## Phase 1 — Mode Detection

**Discovery mode**: User has a list of ideas or a problem space but no clear priority order.
→ Run prioritization framework, produce ordered recommendation.

**Validation mode**: User has a proposed roadmap or sequence and wants a sanity check.
→ Critique it against stated goals and surface risks or gaps.

If the request is ambiguous, ask: "Are you trying to figure out what to build next, or does a proposed order already exist that you'd like me to review?"

---

## Phase 2 — Gather Context

Before prioritizing, establish the decision frame. Ask in a single batch if these aren't already clear:

1. **Goals this cycle**: What are the top 1–3 outcomes that matter most right now? (Growth, retention, revenue, technical foundation, etc.)
2. **Constraints**: Team size, time horizon (sprint / quarter / year), non-negotiables?
3. **Users**: Who are we optimizing for — and are there different user segments with different needs?
4. **Current state**: What's already built? What's broken or blocking?

Why this matters: prioritization without a goal frame produces a ranked list that optimizes for the wrong thing. A feature that's high-impact for acquisition may be irrelevant if the goal is retention.

---

## Phase 3 — Prioritization Framework

Apply the appropriate framework based on context:

### For most cases — Effort/Impact Matrix

Score each feature on two axes:

| Feature | Impact (1–5) | Effort (1–5) | Score (Impact/Effort) | Recommendation |
|---------|-------------|--------------|----------------------|----------------|
| [Feature A] | 4 | 2 | 2.0 | Build soon |
| [Feature B] | 5 | 5 | 1.0 | Evaluate carefully |
| [Feature C] | 2 | 1 | 2.0 | Quick win |
| [Feature D] | 1 | 4 | 0.25 | Defer |

Quadrant interpretation:
- High impact, low effort → **Quick wins — do first**
- High impact, high effort → **Strategic bets — phase carefully**
- Low impact, low effort → **Nice-to-haves — batch or defer**
- Low impact, high effort → **Traps — deprioritize or cut**

### For strategic bets — RICE Scoring (optional, higher rigor)

`RICE = (Reach × Impact × Confidence) / Effort`

Use when: comparing features with very different user reach, when confidence in estimates varies significantly, or when a stakeholder needs a quantified rationale.

| Feature | Reach | Impact | Confidence | Effort | RICE Score |
|---------|-------|--------|------------|--------|------------|
| ... | | | | | |

### For MVP scoping — MoSCoW

Use when: defining the minimum viable scope for a launch, or when time-boxing is the primary constraint.

- **Must**: Non-negotiable for the thing to work at all
- **Should**: High value but not launch-blocking
- **Could**: Worth doing if capacity allows
- **Won't** (this version): Explicitly deferred — not abandoned

---

## Phase 4 — Sequence and Phase

Produce a phased roadmap based on the prioritization output.

```
## Roadmap: [Product / Feature Area]
**Goal this cycle**: [primary outcome]
**Time horizon**: [e.g., Q2 2026 / next 3 sprints]

---

### Now (current sprint / next 4 weeks)
| Feature | Rationale | Owner | Status |
|---------|-----------|-------|--------|
| [Feature C] | Quick win, unblocks downstream work | — | Not started |

### Next (4–8 weeks)
| Feature | Rationale | Dependencies | Status |
|---------|-----------|--------------|--------|
| [Feature A] | High impact once [Feature C] is live | Feature C | — |

### Later (8+ weeks / backlog)
| Feature | Rationale | Trigger to reprioritize |
|---------|-----------|------------------------|
| [Feature B] | High effort — revisit when team grows | Hiring a second backend eng |

### Won't do (this cycle)
| Feature | Why deferred |
|---------|--------------|
| [Feature D] | Low impact, high effort — remove from active consideration |
```

---

## Phase 5 — Surface Trade-offs

After producing the roadmap, explicitly call out the key trade-offs made. This is the most important part.

```
**Trade-offs in this roadmap:**

- We're prioritizing [X] over [Y] because [reason tied to stated goal].
  Risk: [what we're accepting by making this choice].

- [Feature B] is pushed to "Later" despite being requested often.
  Assumption: [belief this rests on]. If wrong, it should move to "Next".

- This sequence assumes [dependency or constraint]. If that changes, revisit [specific item].
```

Why this matters: a roadmap without explicit trade-offs is a wish list. Naming the trade-offs is what makes a roadmap a decision — and gives stakeholders something to challenge.

---

## Phase 6 — Validation Mode (if applicable)

If the user provided a proposed roadmap for review, evaluate it against:

1. **Goal alignment**: Does the sequence optimize for the stated goals?
2. **Dependency order**: Are there items sequenced out of order given technical or UX dependencies?
3. **Missing quick wins**: Are there obvious high-impact, low-effort items not on the list?
4. **Scope creep risk**: Are any items scoped too broadly to be actionable?
5. **Missing "won't do"**: A roadmap without explicit deferrals invites scope expansion.

Produce a short critique:

```
**Roadmap review:**

Strengths:
- [What's working about this sequence]

Risks / suggested changes:
- [Issue]: [Why it matters] → [Suggested adjustment]

Open questions:
- [What needs clarification to validate this further]
```

---

## Phase 7 — Offer Next Steps

> "Roadmap complete. From here:
> - Write or refine requirements for the 'Now' items → use the `prd` skill
> - Break the 'Now' items into sprint-ready stories → use the `user-stories` skill
> - Or dig deeper into a specific trade-off — what would you like?"
