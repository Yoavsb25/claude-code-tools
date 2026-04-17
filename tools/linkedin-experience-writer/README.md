# linkedin-experience-writer

Turns a description of one project into 1–3 polished LinkedIn experience bullets that a tech professional would be proud to post. Each bullet covers a distinct aspect of the work, and every bullet comes with two alternative phrasings so you can pick the one that reads better.

## How it works

1. **Targeting question** — asks what type of role you're targeting (senior IC, lead, startup generalist, etc.) and tailors framing accordingly.
2. **Source check** — accepts raw notes, a ticket log, a doc, or a verbal description; asks up to two follow-up questions to fill gaps.
3. **Aspect extraction** — identifies 1–3 concrete domains of work (e.g. API design, deployment, data modelling) and writes one bullet per domain.
4. **Two phrasings per bullet** — same angle, different sentence structure. Label Option A and Option B.
5. **Best-pick recommendation** — highlights the single strongest bullet for your target role.

## Usage

Copy `SKILL.md` into `~/.claude/skills/linkedin-experience-writer.md` (or install via the registry), then say:

> "Help me write my LinkedIn experience bullets for [project]"
> "Rewrite my LinkedIn work history for [role]"
> "Write experience bullets — here are my notes: [paste]"

## Output format

```
**Deployment**

Option A: Migrated CI/CD pipeline to GitHub Actions, cutting release cycle from [X days] to [Y hours] across a team of [N] engineers.

Option B: Rebuilt the release pipeline on GitHub Actions, reducing deploy time by [add metric] and eliminating manual handoffs.

---
⭐ If you only add one bullet: [strongest option] — leads with the highest-signal detail for a [targeting role].
```

## Requirements

No external tools or API keys required — works with any Claude Code setup.
