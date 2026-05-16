---
name: linkedin-project-adder
description: >
  Adds a new entry to the LinkedIn Projects section with full detail: title, description,
  skills/technologies, dates, project URL, contributors, and optional company/education association.
  Generates polished, recruiter-optimised content following LinkedIn best practices, then automates
  filling it into LinkedIn using a headed Playwright browser.
  Use this skill whenever the user wants to add, create, or post a project to LinkedIn — even if
  they just say "add this to LinkedIn", "put this on my LinkedIn projects", "update my LinkedIn
  projects", "add my GitHub project to LinkedIn", "add project to LinkedIn profile",
  "I want to showcase this project on LinkedIn", or "post this project". Trigger for informal
  inputs too — if the user mentions a project and LinkedIn in the same breath, this is the skill.
---

# LinkedIn Project Adder

Turn raw project information into a polished, complete LinkedIn project entry, then automate
adding every field to the user's LinkedIn profile via a headed browser.

## Step 1: Gather the project information

Ask the user for whatever they haven't already provided. Keep it conversational — ask multiple
questions in one message rather than firing them one at a time.

1. **Source** — GitHub repo URL, README text, or a free-text description. If they give a GitHub
   URL, use WebFetch to read the README.
2. **Dates** — Start month/year. Still ongoing, or is there an end date?
3. **Skills / technologies** — What are the main technologies, frameworks, or languages used?
   (e.g. "Python, FastAPI, PostgreSQL, React"). You can infer obvious ones from the README, but
   confirm with the user — recruiter-searchability depends on getting these right.
4. **Contributors** — Did anyone else work on this? If so, their names or LinkedIn profile URLs
   (optional — skip gracefully if it was a solo project).
5. **Association** — Should it link to a job or education entry? (e.g. "built at Acme Corp" or
   "university capstone"). Optional — skip if it's clearly a personal project.

Don't ask for things you can infer (e.g. the project URL is usually the GitHub URL). If a README
is provided, extract tech stack from it and propose it to the user for confirmation rather than
asking from scratch.

## Step 2: Generate the LinkedIn content

Produce a structured block for the user to review and edit before anything is automated.

```
TITLE: <project name, ≤100 chars — concise, keyword-rich, action-oriented>
URL: <GitHub or live demo URL — live demo preferred>
START: <Month YYYY>
END: <Month YYYY or "Present">
ASSOCIATED WITH: <job/education name or "none">
SKILLS: <up to 5, comma-separated — pick the most recruiter-searchable ones>
CONTRIBUTORS: <LinkedIn names or profile URLs, comma-separated, or "none">
DESCRIPTION:
<2–5 sentences. Lead with the outcome or problem solved, not the process. Include at least one
 quantifiable detail if possible (users, speed improvement, scale). Name the core technologies.
 Max 2000 chars. Write in third-person implied — no "I built…"; use "A system that…" or start
 with a strong verb ("Designed…", "Built…", "Automated…").>
```

**LinkedIn best practices to follow when writing the content:**
- **Title**: Think like a recruiter searching for your skill. "Real-Time AI Trading Signal System"
  beats "Trading Bot".
- **Description**: Impact first, implementation second. If you can say "reduced X by Y%" or
  "used by N users", say it. End with the problem domain or business value.
- **Skills**: Choose 3–5 skills that are searchable and meaningful. Avoid overly generic terms
  like "Programming" — pick specific languages, frameworks, or platforms.
- **URL**: A live demo link is stronger than GitHub alone. If both exist, use the live URL and
  mention GitHub in the description.
- **Contributors**: Adding teammates signals collaboration skills — encourage the user to include
  them if relevant.

Show the full block to the user and ask: **"Does this look right? Edit anything before I open LinkedIn."**

Wait for the user to confirm or edit before proceeding.

## Step 3: Automate adding it to LinkedIn

Once the user confirms the content, run the automation script. Ensure dependencies are installed
first (this only needs to happen once — subsequent runs skip it):

```bash
cd ~/.claude/skills/linkedin-project-adder/scripts && npm install --silent 2>/dev/null; node add_project.js '<JSON>'
```

Where `<JSON>` is a single-line JSON string with these fields:

```json
{
  "title": "Project Title",
  "description": "Project description text",
  "url": "https://github.com/...",
  "startMonth": "January",
  "startYear": "2024",
  "endMonth": "March",
  "endYear": "2025",
  "currentlyWorking": false,
  "associatedWith": "Acme Corp",
  "skills": ["Python", "FastAPI", "PostgreSQL"],
  "contributors": ["Jane Smith", "https://linkedin.com/in/johndoe"]
}
```

Field notes:
- For `currentlyWorking: true`, omit `endMonth` and `endYear`.
- For no association, use `""` for `associatedWith`.
- `skills` can be an empty array `[]` if none provided.
- `contributors` can be an empty array `[]` for solo projects.
- Skills are entered via LinkedIn's typeahead — the script selects the first matching suggestion.
  If a skill isn't found in LinkedIn's ontology the script will log a warning and move on.
- Contributors are searched by name or LinkedIn URL — the script picks the first result. If the
  person doesn't appear, log it and continue.

Warn the user upfront: *"A browser window will open. If you're not logged in to LinkedIn, please
log in — your session will be saved for next time."*

After the script exits (exit code 0), confirm to the user that the project was added.
If it exits with a non-zero code, read stderr and report what went wrong with a suggestion.

## Notes on edge cases

- If the README is very long, focus on the first 500 words — don't dump everything.
- If there's no clear impact metric, focus on the technical depth and the problem it solves.
- If the user says "just write the content, I'll add it myself", skip Step 3 and output the
  formatted block only.
- If the browser can't find a field (LinkedIn's UI changes), tell the user exactly where to find
  it manually and paste the content for them to copy-paste.
- Skills that aren't in LinkedIn's ontology won't be auto-added; list them in the description
  instead.
