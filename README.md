# claude-code-tools

Practical Claude Code skills for daily life — grocery shopping, London transit, personal finance, and task automation. Drop a skill into any project and say the trigger phrase. That's it.

Built for **[Claude Code](https://claude.ai/code)** users who want AI that does things, not just talks about them.

---

## Skills

Copy any skill folder into `.claude/skills/<skill-name>/` in your project, then trigger it by phrase or `/command`.

| Skill | Trigger | What it does |
|-------|---------|-------------|
| [tube-fare-auditor](./tube-fare-auditor/) | *"audit my Oyster card"* | Full TfL fare audit — checks every journey against the correct fare, flags railcard discount failures, surfaces refund opportunities |
| [tfl-refund](./tfl-refund/) | *"file a TfL refund"* | Turns an audit report into a ready-to-send TfL refund claim email |
| [ocado-shopper](./ocado-shopper/) *(macOS)* | *"do my Ocado shop"* | Reads your weekly list from Apple Notes, finds best-value Ocado products, adds to trolley |
| [amazon-shopper](./amazon-shopper/) *(macOS)* | *"order X on Amazon"* | Searches Amazon UK, picks the best match, adds to basket — never checks out without you |
| [trip-expense-report](./trip-expense-report/) | *"expense report for my trip"* | Spending breakdown for any trip or date range from a Wise CSV |
| [github-profile-refactor](./github-profile-refactor/) | *"refactor my GitHub profile"* | Audits and rewrites a GitHub profile README — stronger hook, better brand, curated skills |
| [add-todo](./add-todo/) *(macOS)* | *"add todo: X"* | Adds a task to an Apple Notes task list |
| [run-todos](./run-todos/) *(macOS)* | *"run my todos"* | Executes pending tasks from Apple Notes using Claude's tools |
| [oyster-audit](./oyster-audit/) | *"audit my Oyster"* | Lightweight Oyster charge audit (see `tube-fare-auditor` for the full version with railcard checking) |

---

## Tools

Tools are standalone scripts with their own setup. Unlike skills, they run Python code directly.

### [grocery](./grocery/) — Basket Price Comparator

Compare live grocery prices across Tesco, Ocado, and Waitrose for any shopping list. Playwright scrapes prices in real time; Claude matches each item to the best product per retailer and highlights the cheapest basket.

```bash
# First-time setup
cd grocery && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && playwright install chromium

# Run a comparison
source grocery/.venv/bin/activate
python grocery/basket_compare.py --file /tmp/basket-list.txt
```

**Requires:** Python 3.9+, `ANTHROPIC_API_KEY`

---

## Quick start

```bash
# Copy a skill into your project
cp -r tube-fare-auditor /path/to/your-project/.claude/skills/

# Then in Claude Code, just say the trigger phrase
# e.g. "audit my Oyster card" or /tube-fare-auditor
```

Skills are picked up automatically — no configuration needed beyond the copy.

---

## License

MIT
