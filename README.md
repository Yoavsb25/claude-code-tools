# claude-code-tools

My collection of Claude Code skills and automation tools.

---

## Tools (with runnable code)

### [grocery](./grocery/) — Basket Price Comparator
Compare grocery prices across Tesco, Ocado, and Waitrose for any shopping list. Playwright scrapes live prices; Claude matches each item to the best product per retailer.

**Requirements:** Python 3.9+, Playwright, `ANTHROPIC_API_KEY`

---

## Skills (Claude Code skill files)

Copy a skill folder into your project's `.claude/skills/<skill-name>/` to use it.

| Skill | What it does |
|-------|-------------|
| [oyster-audit](./oyster-audit/) | Audit TfL Oyster card charges against correct fares, detect overcharges |
| [tfl-refund](./tfl-refund/) | Generate a ready-to-send TfL refund claim email from an audit report |
| [trip-expense-report](./trip-expense-report/) | Spending breakdown for any trip or date range from a Wise CSV |
| [add-todo](./add-todo/) *(macOS)* | Add tasks to an Apple Notes task list |
| [run-todos](./run-todos/) *(macOS)* | Execute pending tasks from Apple Notes using Claude's tools |
| [amazon-shopper](./amazon-shopper/) *(macOS)* | Search Amazon UK, pick best match, add to basket — never checks out |

---

## How to use a skill

1. Copy the skill folder into your project's `.claude/skills/` directory:
   ```bash
   cp -r oyster-audit /path/to/your-project/.claude/skills/
   ```
2. In Claude Code, say the trigger phrase (e.g. "audit my Oyster card") or invoke with `/oyster-audit`
3. Claude will pick up the skill automatically

> **Tools with runnable code** (like `grocery`) have additional setup — see the tool's `README.md`.

---

## License

MIT
