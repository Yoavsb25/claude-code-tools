# resume-tailor

Tailors a resume to a specific job posting by pulling from structured work documentation, applying X-Y-Z impact framing to every bullet, and saving the result as a polished markdown file.

## How it works

1. **JD deconstruction** — extracts the north star, top 7 technical keywords, top 3 soft skills, and seniority signal.
2. **Source retrieval** — loads only the work documentation files that are relevant to this specific role (profile summaries, project context, Jira reports) using `references/source-guide.md` as a routing table.
3. **Transformation** — rewrites every bullet in X-Y-Z format with power verbs and JD keywords woven in naturally; sorts bullets by relevance to the role.
4. **Baseline merger** — reads the current resume PDF to extract Education, Military Service, Projects, and Extras — then adapts each section to the JD.
5. **Output** — saves to `~/Desktop/Resume-[Company]-[Role].md` and gives a 3-bullet summary of the tailoring decisions.

## Usage

Copy `SKILL.md` into `~/.claude/skills/resume-tailor.md` (or install via the registry), then say:

> "Tailor my resume for [Company] — [Role]"
> "I'm applying to [Company], help me customize my CV"
> "Prep my resume for this JD: [paste or URL]"

## Output format

A single markdown file saved to `~/Desktop/Resume-[Company]-[Role].md` with sections: Summary, Skills, Experience, Education, Military Service, Projects, Volunteering.

## Requirements

No external tools or API keys required. Requires local work documentation files structured as described in `references/source-guide.md`.

> **Note:** The SKILL.md references specific local file paths and personal work history. Adapt `references/source-guide.md` and the file paths in Step 2 to point to your own documentation before use.
