---
name: skill-reviewer
description: Audits a Claude Code skill file (SKILL.md) and produces a scored report with detailed findings and improvement steps. Use when the user says "review this skill", "rate my skill", "audit skill X", "how good is this skill", "give me feedback on my skill", "what's wrong with this skill", "grade my skill file", or provides a path to a SKILL.md and asks for feedback — even if they just say "check this" while pointing at a skill file. Also triggers on "improve my skill" before implementation, since the review is a prerequisite.
---

# Skill Reviewer

Produce a scored audit report for a Claude Code skill, with concrete improvement steps.

## Step 1 — Find the Skill File

The user will provide either a **path** or a **skill name**.

- **Path given**: read it directly.
- **Name given**: search these locations in order, stop at the first match:
  1. `~/.claude/skills/<name>.md`
  2. `~/.claude/plugins/*/skills/<name>.md` (glob)
  3. `./tools/<name>/SKILL.md` (relative to cwd)
  4. `./<name>/SKILL.md`

If you cannot find it, tell the user exactly where you looked and ask for the full path.

## Step 2 — Read and Parse

Read the full file. Note:
- The YAML frontmatter (`name`, `description`, and any other fields like `disable-model-invocation`)
- The skill body (structure, sections, length in lines)
- Any bundled resources referenced (scripts/, references/, assets/) and whether those paths actually exist on disk
- Writing patterns: voice, use of MUST/ALWAYS/NEVER, presence of "why" reasoning

Don't start scoring until you've read the whole file.

## Step 3 — Anti-Pattern Scan

Before scoring, do a quick pass for these failure modes. Note any you find — they'll inform the scores and improvement steps.

- **Contradictory instructions**: does the skill say to do X in one place and not-X in another?
- **Fragile step references**: does it say "as in Step 3" or "see above" — references that break if someone reorders sections?
- **Scope creep**: is this skill clearly trying to do 3 different things that would be better as separate skills?
- **Human-readable description**: does the frontmatter description read like a README ("This skill helps you...") instead of a trigger phrase ("Use when the user says...")?
- **Dangling resource references**: does the skill reference a file in `scripts/` or `references/` that doesn't exist?
- **MUST-spam**: more than ~3 all-caps commands (MUST/ALWAYS/NEVER) without reasoning given for any of them?

## Step 4 — Score Each Category

Score each category **0–10**. Half-points are fine (e.g. 7.5). A 10 should be genuinely exceptional.

### Category Rubrics

**1. Trigger / Description**
Does the description reliably invoke this skill in the right situations, and avoid false positives? Is it optimized for *triggering* (action-oriented, covers synonyms, edge cases, naturally "pushy") rather than written for humans to read?
- **9–10**: Specific, action-oriented, covers synonyms and edge cases, naturally pushy without spamming; clearly optimized for Claude to invoke it
- **7–8**: Clear and mostly correct; misses a few trigger phrases, has minor false-positive risk, or reads slightly like a README
- **5–6**: Too generic (triggers when it shouldn't) or too narrow (misses obvious use cases); or written for humans ("This skill helps you…") not for triggering
- **3–4**: Vague, keyword-only, or passive — Claude is likely to ignore it
- **0–2**: Missing, one sentence with no context, or actively misleading

**2. Instruction Clarity**
Could a fresh Claude instance follow these steps correctly without extra inference?
- **9–10**: Every step is unambiguous; no assumed knowledge; a new Claude gets it right first try
- **7–8**: Mostly clear; one or two steps require reasonable inference
- **5–6**: Some steps are ambiguous or rely on knowledge not provided in the skill
- **3–4**: Significant gaps; the model would frequently have to improvise
- **0–2**: Unclear to the point of being unusable

**3. Structure**
Is the skill well-organized, right-sized, and easy to navigate?
- **9–10**: Logical flow, good headers, appropriate length, uses progressive disclosure if needed
- **7–8**: Good structure with minor issues (slightly long, section order off, missing a header or two)
- **5–6**: Either wall-of-text or too sparse; sections aren't well signposted
- **3–4**: Hard to follow; no clear flow between steps
- **0–2**: No discernible structure; just a dump of text

**4. Edge Case Coverage**
Does the skill handle failure modes, missing inputs, and ambiguous situations?
- **9–10**: Explicit handling for missing files, ambiguous input, empty results, errors, and user misbehavior
- **7–8**: Covers the main failure modes; misses a few less-obvious cases
- **5–6**: Only handles the happy path
- **3–4**: No edge case handling at all
- **0–2**: Actively fails on common edge cases that are clearly in scope

**5. Output Definition**
Is the expected output clearly defined — format, structure, examples?
- **9–10**: Exact template or schema provided; nothing left to interpretation
- **7–8**: Format is described but not fully pinned down
- **5–6**: Vague output description; the model has to guess structure
- **3–4**: No output definition at all
- **0–2**: Contradicts itself on output format, or the format is unsuitable for the task

**6. Writing Style**
Imperative voice, explains *why* not just *what*, minimal MUST-spam, appropriate tone?
- **9–10**: Commands in imperative form, reasoning given for non-obvious choices, MUST/ALWAYS/NEVER used sparingly and only where stakes genuinely require it
- **7–8**: Good style with occasional lapses (a few unexplained MUSTs, one section reads like a spec)
- **5–6**: Noticeably over-reliant on all-caps commands, or reads like a checklist with no reasoning
- **3–4**: Passive voice throughout, no "why" provided, bureaucratic tone
- **0–2**: Hard to parse, contradictory, or machine-generated boilerplate

**7. Dependencies / Compatibility**
Does the skill correctly declare what it needs to work — tools, permissions, platform, bundled files?
- **9–10**: All required tools, MCP servers, platform constraints, and bundled resources are declared and present; the skill is self-contained
- **7–8**: Minor gaps (one undeclared dependency, a referenced file that might not exist everywhere)
- **5–6**: Assumes tools or permissions without declaring them; partially self-contained
- **3–4**: Relies on significant undeclared dependencies that would silently fail
- **0–2**: Completely undeclared dependencies, or references files that don't exist

## Step 5 — Produce the Report

Use exactly this structure:

---

# Skill Review: `<skill-name>`

> **Verdict**: One sentence. The single most important thing about this skill right now. E.g. "Strong instructions but the description won't reliably trigger it — that's the fix." or "Well-rounded skill; edge cases are the only meaningful gap."

## Scorecard

| Category | Score | One-line verdict |
|----------|-------|-----------------|
| Trigger / Description | X/10 | … |
| Instruction Clarity | X/10 | … |
| Structure | X/10 | … |
| Edge Case Coverage | X/10 | … |
| Output Definition | X/10 | … |
| Writing Style | X/10 | … |
| Dependencies / Compatibility | X/10 | … |
| **Overall** | **X.X/10** | … |

> Overall = weighted average. Trigger and Clarity are weighted 1.5×, all others 1×. Formula: (Trigger×1.5 + Clarity×1.5 + Structure + EdgeCases + OutputDef + Style + Deps) ÷ 8. Round to one decimal.

---

## Anti-Patterns Found

List any anti-patterns from Step 3 here. If none, write "None detected." Don't skip this section.

---

## Detailed Findings

### 1. Trigger / Description — X/10
What works, what doesn't. Quote specific phrases from the skill. Call out explicitly if the description reads like a README rather than a trigger.

### 2. Instruction Clarity — X/10
Walk through any steps that would trip up a fresh Claude instance. Name the specific section or line.

### 3. Structure — X/10
Comment on length, heading hierarchy, and flow. If a section is in the wrong place or missing, say so.

### 4. Edge Case Coverage — X/10
List edge cases the skill handles well, then list ones it doesn't that it should.

### 5. Output Definition — X/10
Is the output format pinned? What's underspecified?

### 6. Writing Style — X/10
Point to specific examples of good and bad style. Quote lines that illustrate the issue.

### 7. Dependencies / Compatibility — X/10
What's declared, what's assumed, what's missing or dangling.

---

## Improvement Steps

Ordered by impact (fix highest-impact issues first). Each step is tagged:
- `[Quick win]` — 5 minutes or less, localised change
- `[Major rework]` — requires rethinking a section or restructuring

1. **[Category]** `[Quick win / Major rework]` Specific, actionable instruction. Say *what* to change and *why* it matters.
2. …

Aim for 3–6 steps. Don't pad with low-value suggestions.

---

## Weakest Section — Suggested Rewrite

Pick the single lowest-scoring section (or the one where a concrete example would be most useful). Show a before/after:

**Before** (quote the current text):
```
…
```

**After** (your improved version):
```
…
```

Explain in one sentence why the rewrite is better.

---

## What's Working Well

One short paragraph on the strongest parts — the author needs to know what to keep, not just what to fix.

---

## Edge Cases for the Reviewer Itself

- If the skill path doesn't exist: say clearly which path was checked, don't hallucinate content.
- If the frontmatter is missing or malformed: count it against Trigger/Description and Dependencies scores.
- If the skill file is very short (under 20 lines): flag it — short skills almost always skip output definition and edge cases.
- If no bundled resources are referenced, score Dependencies based on undeclared tool/platform assumptions alone.
