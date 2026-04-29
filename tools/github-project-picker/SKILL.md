---
name: github-project-picker
description: Picks the best GitHub projects to showcase on Yoav's resume for a specific job, and writes tailored resume-ready descriptions for each. Use this skill whenever the user mentions a job, role, or company alongside words like "projects," "GitHub," "showcase," "portfolio," "which projects," or "what to include." Even if they just say "I'm applying to X, what should I put in my projects section" — invoke this skill. Also invoke it when running resume-tailor if the user wants GitHub-fresh project descriptions rather than using the PDF.
---

# GitHub Project Picker

Your job is to figure out which of Yoav's GitHub projects best showcase his skills for a specific role, then write resume-ready descriptions that make a hiring manager immediately understand the value.

---

## Step 1: Get the Job Description

Get the JD from the user (ask them to paste it or provide a URL; if a URL, use WebFetch).

Then extract:

**North Star** — In one sentence: what problem is this company hiring to solve?

**Tech signals** — Top 5–7 technologies or domains mentioned (exact words from the JD: "React," "distributed systems," "mobile," "ML pipeline," etc.)

**Seniority signal** — Junior/Mid lead with execution and delivery; Senior/Staff+ lead with architecture, scale, and multiplier effects.

---

## Step 2: Fetch and Read All Repos

Run this to get Yoav's full repo list:
```bash
gh api users/Yoavsb25/repos --paginate -q '.[].name'
```

Skip these non-project repos: `Yoavsb25` (profile README), `private-website` (personal site), `wedding-website`, `Advanced_Programing_HW` (coursework homework), `RealtyCompanyListing` (minimal HTML listing).

For each remaining repo, fetch its README:
```bash
gh api repos/Yoavsb25/<repo-name>/readme -q '.content' | base64 -d
```

Also grab the repo metadata (description, language, topics) for context:
```bash
gh api repos/Yoavsb25/<repo-name> -q '{description: .description, language: .language, topics: .topics}'
```

---

## Step 3: Score and Select

Score each repo against three dimensions:

**Tech stack match** — How directly does the repo's stack overlap with the JD's tech signals? Direct overlap (same framework/language) scores higher than domain overlap (e.g., "also a web app").

**Architectural depth** — Does the repo show real engineering decisions? Look for: multi-module architecture, algorithm design, observability/telemetry, OAuth/auth flows, API integration, deployment configuration. A single-file script scores low; a layered system with clear separation of concerns scores high.

**Domain relevance** — Does the project solve a problem adjacent to what this company does? A fintech JD values the billing/reporting angle of calendar-analytics. A mobile JD values fifa-songs-app. A developer-tools JD values claude-code-tools.

**Select at least 3, up to 5.** More is fine if there are genuinely strong fits. Fewer than 3 only if the portfolio clearly doesn't match the domain — and in that case, say so honestly and recommend leading with the most transferable projects.

---

## Step 4: Write Resume-Ready Descriptions

For each selected project, produce a block like this:

```
**[Project Name]** | [Comma-separated tech stack, most JD-relevant first] | github.com/Yoavsb25/<repo>
- [Lead bullet: the most JD-relevant thing about this project, X-Y-Z format, metric near front]
- [Second bullet: key engineering decision, architecture choice, or scale/complexity detail]
- [Optional third bullet: only if it adds distinct signal — deployment, observability, algorithm, etc.]
```

**Bullet rules:**
- X-Y-Z formula: "Accomplished [X] as measured by [Y], by doing [Z]." Put the impact near the front.
- Power verbs: Built, Architected, Designed, Shipped, Implemented, Automated, Integrated — never "Helped," "Worked on," "Contributed to."
- Keyword integration: Weave the Step 1 tech signals naturally. One mention per bullet is enough.
- Signal-to-noise: Cut anything that doesn't serve the role's North Star. Two sharp bullets beat three diluted ones.
- Honest: Don't invent metrics. If there's no clear measurable outcome, lead with scope or complexity instead ("...handling X data models across Y modules").

**Ordering:** List the projects in descending relevance to the JD — strongest fit first.

---

## Step 5: Output

Print a brief selection rationale (3–5 lines max) explaining which repos made the cut and why, and which you excluded and why — so Yoav can sanity-check your reasoning.

Then print the ready-to-paste Projects section:

```markdown
## Projects

[blocks from Step 4, strongest first]
```

End with one sentence: "Drop this into your resume above Education, or after Experience for senior roles."

No trailing summary of what you did. Just the output.
