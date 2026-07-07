# claude-code-tools

A curated registry of Claude Code skills and automation tools — browsable, installable, and production-grade.

```bash
npx @yoavsb25/claude-tools list
npx @yoavsb25/claude-tools install ocado-shopper
```

Built for **[Claude Code](https://claude.ai/code)** users who want AI that does things, not just talks about them.

---

## What's inside

| Name | Type | Category | Complexity | Description |
|------|------|----------|------------|-------------|
| [add-todo](./tools/add-todo/) | skill | productivity | simple | Adds tasks to your Apple Reminders app via natural language directly from Claude Code |
| [ibkr-setup](./tools/ibkr-setup/) | skill | finance | simple | One-time setup for your IBKR investment profile — captures risk tolerance, time horizon, sector preferences, and target allocation. |
| [linkedin-experience-writer](./tools/linkedin-experience-writer/) | skill | career | simple | Writes polished LinkedIn experience bullets for a single project a tech professional worked on, with 2 alternative phrasings per bullet so the user can choose the best fit |
| [ocado-deals](./tools/ocado-deals/) | skill | shopping | simple | Scans Ocado's Fresh & Chilled, Food Cupboard, and Bakery offer pages and ranks the best deals by absolute £ saving per item. |
| [run-todos](./tools/run-todos/) | skill | productivity | simple | Fetches your Apple Reminders todo list and runs them as Claude Code tasks automatically |
| [tfl-refund](./tools/tfl-refund/) | skill | finance | simple | Guides you through claiming a TfL refund for overcharges, incomplete journeys, or maximum fares |
| [amazon-shopper](./tools/amazon-shopper/) | skill | shopping | intermediate | Searches Amazon for products, compares options, and adds the best match to your basket using Claude Code and Playwright |
| [expense-analyzer](./tools/expense-analyzer/) | skill | finance | intermediate | Analyzes Wise/Revolut CSV transaction exports and produces a detailed markdown expense report with category totals, top transactions, and flagged unusual spends |
| [flight-finder](./tools/flight-finder/) | skill | productivity | intermediate | Searches and compares flights across Expedia and Kiwi.com, ranking results by price, speed, and stops to surface the cheapest, fastest, and best-overall options. |
| [folder-organizer](./tools/folder-organizer/) | skill | productivity | intermediate | Recursively scans a folder, proposes a semantic reorganization plan by project/topic/type, waits for approval, then executes moves with bash. |
| [github-profile-refactor](./tools/github-profile-refactor/) | skill | developer-tools | intermediate | Refactors and elevates a GitHub profile README — improving readability, personal brand, and content quality |
| [github-project-picker](./tools/github-project-picker/) | skill | career | intermediate | Picks the best GitHub projects to showcase on a resume for a specific job and writes tailored, resume-ready descriptions for each |
| [ibkr-buy-advisor](./tools/ibkr-buy-advisor/) | skill | finance | intermediate | Gives a specific, profile-matched buy recommendation for a given cash amount using IBKR data, S&P Global ratings, Canary Data signals, and credibility-filtered research. |
| [ibkr-portfolio-review](./tools/ibkr-portfolio-review/) | skill | finance | intermediate | Professional portfolio analysis using live IBKR data, S&P Global ratings, Moody's credit ratings, Canary Data signals, and credibility-filtered web research. |
| [ibkr-stock-finder](./tools/ibkr-stock-finder/) | skill | finance | intermediate | Discovers 3–5 investment candidates matched to your profile using IBKR themes, S&P Global screening, Canary Data signals, and credibility-filtered web research. |
| [linkedin-project-adder](./tools/linkedin-project-adder/) | skill | career | intermediate | Adds a LinkedIn Projects entry from a GitHub URL or description, then fills the form via a headed Playwright browser |
| [ocado-shopper](./tools/ocado-shopper/) | skill | shopping | intermediate | Smart Ocado grocery shopper — reads a weekly list from Apple Notes, finds best-value products, and fills the trolley |
| [oyster-audit](./tools/oyster-audit/) | skill | finance | intermediate | Audits TfL Oyster card travel history against correct fares and detects potential refunds |
| [process-emails](./tools/process-emails/) | skill | productivity | intermediate | Fully-automatic email-to-todo pipeline — reads unread Gmail, extracts action items, and writes them to the Claude Tasks Apple Note |
| [product-manager](./tools/product-manager/) | skill | productivity | intermediate | Product thinking partner for PRDs, user stories, roadmaps, and feature prioritization |
| [repo-guardian](./tools/repo-guardian/) | skill | developer-tools | intermediate | Staff-level repo governance for Python/GitHub projects — generates a tiered, actionable checklist covering pre-commit hooks, CI quality gates, PR templates, and security scanning |
| [resume-tailor](./tools/resume-tailor/) | skill | career | intermediate | Tailors a resume to a specific job posting by pulling from work documentation and saving a polished markdown output |
| [skill-reviewer](./tools/skill-reviewer/) | skill | developer-tools | intermediate | Audits a Claude Code skill file and produces a scored report with detailed findings and improvement steps |
| [stay-finder](./tools/stay-finder/) | skill | productivity | intermediate | Searches and compares hotels, apartments, villas, and all accommodation types across Booking.com and Expedia, ranking by budget fit, rating, and location. |
| [tech-stack-selector](./tools/tech-stack-selector/) | skill | developer-tools | intermediate | Opinionated tech stack advisor for new projects — picks language, framework, database, ORM, test runner, linter, and tooling with concrete justification |
| [trip-expense-report](./tools/trip-expense-report/) | skill | finance | intermediate | Generates a structured expense report from trip receipts and bank statements using Claude Code |
| [ui-ux-expert](./tools/ui-ux-expert/) | skill | developer-tools | intermediate | Opinionated UI/UX design consultant for specs, style guides, and layout decisions |
| [devops-engineer](./tools/devops-engineer/) | skill | developer-tools | advanced | Senior DevOps engineer for CI/CD pipelines, deployment architecture, containerization, observability, and infrastructure as code |
| [grocery](./tools/grocery/) | tool | shopping | advanced | Basket price comparator — scrapes Tesco, Ocado, and Waitrose and uses Claude to match items to their best-value equivalent |
| [job-search](./tools/job-search/) | skill | career | advanced | Runs the end-to-end job hunt: finds and ranks matching openings, tracks applications in a local tracker file, and kicks off resume-tailor for shortlisted roles |
| [security-architect](./tools/security-architect/) | skill | developer-tools | advanced | Proactive security-by-design skill for threat modeling, auth architecture, data security, and compliance planning (GDPR, SOC2, HIPAA) |
| [software-architect](./tools/software-architect/) | skill | developer-tools | advanced | Senior software architect for system design and architectural decision records (ADRs) |
| [testing-strategist](./tools/testing-strategist/) | skill | developer-tools | advanced | Scans codebase architecture and existing tests to produce a tailored testing strategy with gap analysis, framework recommendations, and prioritized action plan. |
| [tube-fare-auditor](./tools/tube-fare-auditor/) | tool | finance | advanced | Advanced TfL Oyster card auditor — verifies railcard discounts, detects maximum fare charges, and produces a refund report |

---

## Quick start

**Browse the registry:**
```bash
npx @yoavsb25/claude-tools list
npx @yoavsb25/claude-tools list --category finance
npx @yoavsb25/claude-tools list --complexity simple
```

**Get details on a tool:**
```bash
npx @yoavsb25/claude-tools info tube-fare-auditor
```

**Install a skill into Claude Code:**
```bash
npx @yoavsb25/claude-tools install ocado-shopper
# → copies SKILL.md to ~/.claude/skills/ocado-shopper.md
```

Once installed, trigger the skill by phrase or slash command inside Claude Code:
```
/ocado-shopper
"do my Ocado shop"
```

---

## How it works

```mermaid
graph LR
    A[tools/<name>/manifest.json] -->|generate-registry.ts| B[registry.json]
    B -->|npx @yoavsb25/claude-tools| C[CLI]
    C -->|install| D[~/.claude/skills/]
    D -->|trigger phrase| E[Claude Code]
```

Each tool has a `manifest.json` that declares its type, category, complexity, install targets, and requirements (platform, MCP servers, env vars). The CLI reads the registry and handles installation with pre-flight checks.

---

## Architecture

```
claude-code-tools/
├── tools/                    ← all skills and tools
│   └── <name>/
│       ├── manifest.json     ← structured metadata
│       ├── SKILL.md          ← Claude Code skill definition
│       └── README.md         ← usage documentation
├── cli/                      ← @yoavsb25/claude-tools npm package
│   └── src/
│       ├── commands/         ← list, info, install
│       └── registry.ts       ← fetches registry.json from GitHub
├── scripts/
│   └── generate-registry.ts  ← regenerates registry.json from manifests
├── registry.json             ← auto-generated index of all tools
├── manifest.schema.json      ← JSON Schema for manifest validation
└── .github/workflows/
    ├── validate.yml          ← validates manifests + builds CLI on every PR
    └── update-registry.yml   ← auto-updates registry.json on manifest changes
```

---

## Contributing

Want to add a skill? See [CONTRIBUTING.md](./CONTRIBUTING.md).

---

## License

MIT
