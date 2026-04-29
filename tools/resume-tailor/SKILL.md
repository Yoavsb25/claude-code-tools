---
name: resume-tailor
description: Tailors Yoav's resume to a specific job posting and saves it as a markdown file. Use this skill whenever the user mentions a job, role, company, or application alongside words like "resume," "CV," "apply," "interview prep," or "customize." Even if they just say "I'm applying to X" or "help me prep for Y" — invoke this skill. It pulls from SysAid work documentation to produce a fully tailored, narrative-driven resume with every bullet following the X-Y-Z impact formula.
---

# Resume Tailor

Your job is to architect a tailored resume — not fill a template. The goal is a single, dense narrative that makes a hiring manager immediately see why Yoav is the answer to the problem they're trying to solve.

---

## Step 1: JD Deconstruction

Get the job description from the user (ask them to paste it or provide a URL). If a URL, use WebFetch to retrieve it.

Then extract:

**North Star** — In one sentence: what is the #1 problem this company is trying to solve by making this hire? Everything in the resume should ladder up to solving that problem.

**Keywords**
- Top 7 technical skills (tools, languages, frameworks, platforms — use exact words from the JD)
- Top 3 soft skills (leadership style, collaboration mode, communication expectations)

**Seniority signal**
- Junior/Mid: lead with execution, delivery speed, scope of ownership
- Senior/Staff+: lead with strategy, system-level thinking, cross-team impact, multiplier effects

---

## Step 2: Strategic Source Retrieval

Read `references/source-guide.md` first to understand what each file contains and its noise level. Then load only the files that move the needle for this specific role.

**Always load:**
- `~/Desktop/Work/SysAid/profile-summaries/overall-profile.md` — overall narrative + impact metrics

**Load based on JD emphasis:**
| JD emphasis | Load these files |
|---|---|
| CI/CD, GitOps, Kubernetes, GitHub Actions, deployment | `deployment-workflows.md`, `release-automation.md` |
| React, Node.js, TypeScript, frontend, full-stack, testing | `translation-tools.md` |
| Developer experience, tooling, AI, productivity, DX | `developer-tooling.md` |
| Need specific metrics, dates, or ticket counts | Relevant quarterly Jira report |

**Noise filter for Jira reports:** Skip routine maintenance, minor bug fixes, and process tickets. Only surface tickets that demonstrate a skill explicitly listed in the JD or that have measurable outcomes (%, time saved, users impacted, components shipped).

---

## Step 3: The Transformation

Apply these rules to every bullet point you write:

**X-Y-Z Formula** — "Accomplished [X] as measured by [Y], by doing [Z]." Every bullet must have all three elements. Put the metric (Y) near the front so it's visible at a glance.

**Power verbs** — Never use: Managed, Helped, Assisted, Worked on, Contributed to, Participated in. Always use: Orchestrated, Spearheaded, Architected, Refactored, Drove, Shipped, Owned, Reduced, Accelerated, Designed, Built, Migrated, Automated.

**Keyword integration** — Weave the Step 1 keywords naturally into the Summary and Experience sections. Don't stuff — one mention in a bullet is usually enough. The Summary should read like it was written for this specific role.

**Signal-to-noise** — If a SysAid accomplishment doesn't serve the role's North Star, cut it. Three laser-focused bullets beat five diluted ones.

**Relevance ordering** — Within each job entry, sort bullets by relevance to the JD (most relevant first), not by chronology.

---

## Step 4: Baseline Merger

Read the current resume PDF:
`~/Documents/GitHub/private-website/src/assets/CV/cv.pdf`

Extract: Education, Military Service, Projects, Volunteering & Extracurricular.

**Do not copy blindly.** If the JD emphasizes a technology or trait that can be honestly surfaced from these sections with a slight reword, make the change. Examples:
- JD emphasizes leadership at scale → reframe military service around span of command and high-stakes decision-making
- JD emphasizes cloud/distributed systems → surface any relevant project tech stack details
- JD doesn't value a section at all → trim or omit it to keep the page tight

---

## Output Format

Save the final file to: `~/Desktop/Resume-[Company]-[Role].md`

Use this exact structure:

```markdown
# Yoav Sborovsky
+972-52-465-4302 · yoavsb25@gmail.com · [LinkedIn] · [GitHub] · [Website]

## Summary
[2-3 sentences. Who you are + the specific value you bring for THIS role. Keywords from Step 1 woven in naturally. Confident, not generic.]

## Skills
[Grouped by category, pruned to what's relevant for this role. Remove anything that doesn't reinforce the narrative.]

## Experience

### [Job Title] · SysAid Technologies · [dates]
- [Most relevant bullet, X-Y-Z format, metric near front]
- [Second most relevant bullet]
- [3-5 bullets total, ordered by JD relevance]

### Data Analyst · AFFILOMANIA · 2020–2021
- [Include if role values data/analytics background; otherwise omit]

## Education
[From PDF — rephrase only if a JD keyword or trait can be surfaced more clearly]

## Military Service
[From PDF — emphasize leadership scope if JD values it; trim if not]

## Projects
[From PDF — rephrase tech details to highlight JD-relevant stack where honest]

## Volunteering & Extracurricular
[Include only if it adds signal; omit if the page is already dense]
```

**Style constraints:**
- Strict markdown: `##` for sections, `###` for job titles
- Target: ~500–700 words (one dense page); a second page is justified only for Senior/Staff+ roles
- Tone: professional, confident, data-driven — no fluff, no filler phrases like "passionate about" or "strong communication skills"
- After saving, tell the user the file path and give a brief 3-bullet summary of the tailoring decisions you made (which sections you emphasized, which you trimmed, any keywords you wove in)
