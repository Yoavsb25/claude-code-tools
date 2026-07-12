# Network — Warm Intros at Target Companies

Conditional detail for the "Network — warm intros" section of `job-search`'s SKILL.md. Only read
this file once you've determined the user's request is a warm-intro lookup, not a job search.

## One-time setup: exporting connections

`network list`/`network match` read from a local `connections.json`, built from LinkedIn's own
data export — no live scraping, no session cookie, no account risk. If a connections file doesn't
exist yet, walk the user through:

1. On LinkedIn: **Settings & Privacy → Data privacy → Get a copy of your data**.
2. Request the **"Connections"** archive (or "The works" for everything).
3. LinkedIn emails a download link once ready — this can take anywhere from a few minutes to
   ~24 hours, so it isn't instant; tell the user to come back once they have the file.
4. Import it:
   ```bash
   python3 ~/.claude/skills/job-search/scripts/job_tool.py network import --csv "<path to Connections.csv>"
   ```
   Safe to re-run whenever they refresh the export — it merges by profile URL (or by name if no
   URL is in the export) rather than duplicating or wiping existing entries.

## Commands

```bash
python3 ~/.claude/skills/job-search/scripts/job_tool.py network import --csv "<path>"
python3 ~/.claude/skills/job-search/scripts/job_tool.py network list [--company "<name>"]
python3 ~/.claude/skills/job-search/scripts/job_tool.py network match [--company "<name>"]
```

- **`network import`** parses the export (skipping LinkedIn's preamble lines to find the real
  header row) into `connections.json`, reporting counts added/updated/unchanged.
- **`network list`** is for general browsing ("show me my network"), with an optional filter on
  Company. Still useful for eyeballing the network, but treat `match` as the source of truth for
  intro-suggestion precision.
- **`network match`** is the precision tool for intro suggestions:
  - With no `--company`, checks every entry in the profile's `target_companies` watchlist and
    returns per-company matches plus a `no_match_companies` list.
  - With `--company "<name>"`, checks one name ad hoc — for "who do I know at Anthropic" even if
    it isn't on the watchlist yet.
  - Matching normalizes both sides (strips legal suffixes like Inc/LLC/Ltd, lowercases) and
    requires a whole-word match/prefix, never a loose substring — so "Google" catches "Google
    Ireland Limited" but never falsely catches "Metabase" for a "Meta" target or "DeepMind" for a
    "Google" target. If you suspect a real match was missed due to a subsidiary/stale company
    name, suggest the user double-check with `network list --company <broader term>`.

## Presenting results

Group by target company, most-matches-first. Show name, position, connected-on date, and profile
URL (if present) for each match:

```
## 🤝 Warm intros at your target companies

**Google** — 2 connections
- Jane Doe — Senior PM (connected 01 Mar 2022) — linkedin.com/in/janedoe

No connections found at: Anthropic, DeepMind

Want a short referral-request message drafted for reaching out to Jane?
```

Offer to draft a short, specific referral/intro-request message on request — reference the
connection's actual role and how long you've been connected, not a generic template. Never send
anything on the user's behalf — draft only.
