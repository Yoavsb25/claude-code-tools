# github-project-picker

Analyzes a job description and selects the most relevant GitHub projects to showcase on a resume, then writes tailored, resume-ready descriptions for each one.

## How it works

1. **JD deconstruction** — extracts the north star, top tech signals, and seniority level from the job description.
2. **Repo audit** — fetches the full repo list via the GitHub CLI and reads each README and metadata.
3. **Scoring** — scores repos across three dimensions: tech stack match, architectural depth, and domain relevance.
4. **Resume-ready output** — writes 2–3 bullets per project in X-Y-Z impact format, with tech stack and a GitHub link.
5. **Selection rationale** — explains which repos made the cut and why, so you can sanity-check the choices.

## Usage

Copy `SKILL.md` into `~/.claude/skills/github-project-picker.md` (or install via the registry), then say:

> "I'm applying to [Company] for [Role], pick my best GitHub projects"
> "Which of my projects should I put on my resume for this JD? [paste]"
> "Help me write my projects section for [role]"

## Output format

```
## Projects

**[Project Name]** | [Tech stack, JD-relevant first] | github.com/user/repo
- [Lead bullet: most JD-relevant thing, metric near front, X-Y-Z format]
- [Second bullet: key engineering decision or scale/complexity detail]
```

## Requirements

- [GitHub CLI (`gh`)](https://cli.github.com/) installed and authenticated

> **Note:** The SKILL.md references a specific GitHub username and a curated skip-list of non-project repos. Adapt these to your own account before use.
