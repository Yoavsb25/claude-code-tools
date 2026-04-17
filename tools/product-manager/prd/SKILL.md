---
name: product-manager:prd
description: >
  Use when the user wants to write a Product Requirements Document, spec out a feature, define
  product requirements, document a problem statement, or turn a product idea into a structured brief.
  Triggers on: "write a PRD", "help me spec this out", "I need a product brief", "write up the
  requirements for", "define what we're building", "document this feature", "write a product spec",
  or when a user describes a product idea and asks for structure. Also triggers when a vague product
  idea needs to be sharpened into a written artifact.
---

# PRD Sub-Skill

Draft a structured Product Requirements Document. Works for new features, products, experiments, or redesigns — at any level of initial clarity.

---

## Phase 1 — Intake and Interview

Before drafting anything, assess what's known vs. missing.

**If the brief is substantive** (3+ sentences covering the problem, user, and rough solution): proceed to Phase 2 with at most one clarifying question.

**If the brief is thin** (just a name, one sentence, or a vague idea): run an intake interview. Keep it conversational — ask questions in batches of 2–3, not one by one, and not as a 10-question form. Cover:

1. **Problem**: What's broken or missing today? Who experiences this and how often?
2. **User**: Who is the primary beneficiary? What do they care about?
3. **Success**: How will you know this worked? What changes in user behavior or metrics?
4. **Constraints**: Timeline, team size, technical limits, non-starters?
5. **Scope boundary**: What is explicitly NOT in scope for this version?

Why this matters: PRDs fail when they are drafted before the problem is understood. The interview forces that understanding before a single word of requirements is written.

---

## Phase 2 — Draft the PRD

Produce the document in full. Do not ask for approval section by section — draft it end-to-end, then invite feedback.

Use this structure:

---

```
# PRD: [Feature or Product Name]

**Status**: Draft | Under Review | Approved
**Author**: [if known]
**Last updated**: [today's date]
**Target release**: [if known, else TBD]

---

## 1. Problem Statement

What specific problem are we solving, for whom, and why does it matter now?
Include: current pain, frequency/severity, who is most affected.

Avoid: solution language, implementation detail, or aspirational framing at this stage.

---

## 2. Goals

What outcomes do we want to achieve? Write as measurable objectives where possible.

- Goal 1: [specific, ideally with a metric]
- Goal 2: ...

---

## 3. Non-Goals

What are we explicitly NOT trying to solve in this version?
This section prevents scope creep and misaligned expectations.

- Not in scope: ...
- Deferred to later: ...

---

## 4. User Personas

Who are we building this for? List 1–3 personas with:
- Role / context
- Primary job-to-be-done
- What they care about most in this feature

Avoid generic descriptions. If real user research exists, reference it.

---

## 5. Functional Requirements

What must the product do?
Number each requirement. Use "The system shall..." or "Users can..." framing.

### Must Have (P0)
- FR-01: ...
- FR-02: ...

### Should Have (P1)
- FR-03: ...

### Nice to Have (P2)
- FR-04: ...

---

## 6. Non-Functional Requirements

Performance, security, accessibility, scalability, and compliance constraints.

- NFR-01: [e.g., "Page load time under 2 seconds for 95th percentile"]
- NFR-02: ...

---

## 7. Success Metrics

How will we measure whether this worked?

| Metric | Baseline | Target | Measurement method |
|--------|----------|--------|--------------------|
| [e.g., task completion rate] | [X%] | [Y%] | [e.g., analytics event] |

---

## 8. Open Questions

Things that need resolution before or during development. Be honest — real open questions are valuable.

- [ ] [Question] — Owner: [name or TBD] — Due: [date or TBD]
- [ ] ...

---

## 9. Out of Scope / Future Considerations

Ideas that came up but don't belong in this version. Capture them so they aren't lost.
```

---

## Phase 3 — Flag Issues

After drafting, review the PRD for structural problems. Call them out explicitly:

- Goals that are unmeasurable: suggest a metric or flag as aspirational
- Missing persona: if requirements exist but the user is not defined
- Conflicting requirements: flag them as open questions
- No definition of done: if success metrics are absent, note the risk

Why this matters: a PM's job is to surface ambiguity before engineering begins. Delivering a clean document that hides real gaps is worse than delivering an honest draft with flags.

---

## Phase 4 — Offer Next Steps

After the PRD is accepted or iterated to satisfaction:

> "PRD done. Next steps from here:
> - Decompose into user stories → use the `user-stories` skill
> - Map to a roadmap or prioritize against other work → use the `roadmap` skill
> - Or iterate further on this document — what would you like?"
