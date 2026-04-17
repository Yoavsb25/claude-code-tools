# process-emails — Email to Todo Pipeline (macOS + Gmail)

Fully automatic pipeline: reads unread Gmail from the last 24h, runs a single Claude reasoning pass to extract action items, deduplicates against existing todos, and writes rich cards to your "Claude Tasks" Apple Note.

## What it does

1. Fetches up to 30 unread emails via Gmail MCP
2. Fetches full body for emails where the snippet is too thin (e.g. "see attached")
3. Single Claude pass filters noise (newsletters, digests, automated alerts) and extracts structured action items
4. Deduplicates against existing pending tasks in the Apple Note
5. Writes new tasks as rich cards with Due, Context, and Notes fields
6. Classifies each as 🤖 (Claude can execute) or 👤 (human required)

## Card format

```
📌 Reply to Sarah Chen (sarah@acme.com) — approve draft contract, sign-off by 28 Mar
   Due: 28 Mar
   Context: Consulting contract attached, needs sign-off
   Notes: CC James on the reply
```

## Requirements

- macOS (uses AppleScript to write to Notes)
- Gmail MCP server configured
- Apple Notes app with a **"Tasks ✅"** folder

## Usage

```
/process-emails
process my emails
check my emails
```

Run `/run-todos` afterwards to execute the 🤖 tasks.
