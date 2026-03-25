---
name: run-todos
description: Execute all pending tasks in the "Claude Tasks" Apple Note using available tools, then update the note and create a Task Report note. Use when the user says "run my todos", "execute my tasks", "work through my task list", "run todos", or "do my pending tasks".
disable-model-invocation: true
---

# Run Todos

Read all pending tasks from the "Claude Tasks" Apple Note, assess each one before touching anything, execute the ones Claude can handle, then update the note and write a Task Report.

---

## Step 1 — Read the "Claude Tasks" note

The note lives in the **"Tasks ✅"** folder in Notes. Search only within that folder:

```bash
osascript -e '
tell application "Notes"
  repeat with a in accounts
    repeat with f in folders of a
      if name of f is "Tasks ✅" then
        repeat with n in notes of f
          if name of n is "📝 Claude Tasks" or name of n is "Claude Tasks" then
            return body of n
          end if
        end repeat
      end if
    end repeat
  end repeat
  return "NOT FOUND"
end tell' | python3 -c "
import sys, re
html = sys.stdin.read()
if html.strip() == 'NOT FOUND':
    print('NOT FOUND')
else:
    text = html.replace('<br>', '\n').replace('<br/>', '\n').replace('</div>', '\n').replace('</p>', '\n')
    text = re.sub('<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    print(text)
"
```

If output is `NOT FOUND`: tell the user "No Claude Tasks note found. Add tasks with /add-todo first." and stop.

---

## Step 2 — Parse pending tasks

Extract all pending tasks from the `🤖 Claude` and `👤 Human` sections (stop at `✅ Completed`).

**Detect format per task:**

- **Card format**: a line starting with `📌` followed by up to 3 metadata lines (`Due:`, `Context:`, `Notes:`). Extract all fields.
- **Legacy format**: a line starting with `- [ ]`. Extract task text only; set Due/Context/Notes to `—`.

Build a list of task objects:
```
{task: "Buy black iPhone 15 Pro case — under £20", due: "—", context: "User's device, colour and budget specified", notes: "budget: under £20, colour: black", classification: "🤖", raw_format: "card"}
```

The `classification` comes from which section the task was in (`🤖 Claude` → 🤖, `👤 Human` → 👤).

If there are no pending tasks: tell the user "No pending tasks found in Claude Tasks." and stop.

---

## Step 3 — Pre-flight assessment (DO THIS BEFORE EXECUTING ANYTHING)

For each pending task, reason carefully using all available metadata (task text, context, notes) about the likelihood of completing it end-to-end.

Consider:
- What tools would be needed? (Playwright browser, web search, AppleScript, bash, existing skills, Gmail MCP, file operations)
- Are there likely blockers? (login walls, missing credentials, physical presence required, ambiguous task)
- Does the card's `Notes` field remove ambiguity that would otherwise block execution?

Assign a confidence percentage and classify:

| Confidence | Classification | Action |
|---|---|---|
| >85% | 🤖 Claude task | Will attempt |
| 70–85% | 🤔 Maybe | Will attempt, show risk reason |
| <70% | 👤 Human task | Skip, leave pending |

**Shopping tasks — check available skills first:**
- Food/grocery items → `ocado-shopper` skill
- Physical goods, electronics, clothing, accessories, home items → `amazon-shopper` skill
- Flights, restaurant bookings, professional services → no skill available → 👤 human task

---

## Step 4 — Show classification and wait for confirmation

Present the pre-flight results clearly, using card metadata to explain how each task will be executed. Then wait for the user to say "yes" (or adjust):

```
📋 Pre-flight check — N pending tasks

🤖 Claude tasks (N):
- Buy black iPhone 15 Pro case — under £20
  → Amazon search: iPhone 15 Pro case, black, ≤£20
  Context: User's device · Notes: budget £20, colour black

- Reply to Sarah Chen (sarah@acme.com) — draft consulting contract  (Due: 28 Mar)
  → Draft reply via Gmail MCP, CC James
  Context: Consulting contract attached, needs sign-off

🤔 Maybe — will attempt, potential failure point (N):
- Book dentist appointment  (85%) — may hit login wall on booking site

👤 Human tasks — staying pending (N):
- Pick up dry cleaning → physical presence required

Proceed with 🤖 + 🤔 tasks? (yes / adjust the list)
```

Omit any category that has zero tasks. Show `Due:` inline when present. Show Context/Notes only for 🤖 tasks. Wait for user reply before proceeding.

---

## Step 5 — Execute confirmed tasks

Work through each confirmed task one at a time. Use card metadata to inform execution:
- Use the `Notes` field for specific constraints (budget, model, colour, quantity)
- Use the `Context` field for background understanding
- Use the `Due` field to flag urgency

Use the most appropriate tools:
- **Existing skills** (e.g. invoke `/oyster-audit`, `/compare-basket`, `/ocado-shopper`, `/amazon-shopper` if relevant)
- **Playwright browser** for websites (booking, ordering, searching, checking availability)
- **Web search** for research, fact-finding, current information
- **AppleScript / bash** for macOS app interactions
- **Gmail MCP** for email-related tasks
- **File operations** for local file tasks

For each task: execute it fully, then record:
- **Done** `{task, outcome_summary}`
- **Failed** `{task, reason}` — attempted but could not complete

If one task fails: catch the error, record it as Failed, continue to the next task. Never abort the entire run.

---

## Step 6 — Update the "Claude Tasks" note

Get today's date:
```bash
python3 -c "from datetime import date; d=date.today(); print(d.strftime('%d %b %Y'))"
```

Re-read the note body (same method as Step 1). Then update completed/failed tasks:

**For card format tasks** (`📌` lines):
- Find the `📌 <task>` line for each Done/Failed task
- Replace the entire card block (the `📌` line + the 3 metadata lines that follow) with a single completion line:
  - Done: `✅ <task> — <today's date>`
  - Failed: `❌ <task> — <today's date> (failed: <reason>)`
- Move that line into the `✅ Completed` section

**For legacy format tasks** (`- [ ]` lines):
- Change `- [ ] <task>` to `- [x] <task> — <today's date>` for Done tasks
- Change to `- [x] <task> — <today's date> (failed: <reason>)` for Failed tasks
- Move all `- [x]` lines under `✅ Completed`

Leave 👤 Human tasks as-is (pending).

Write back using the temp AppleScript file pattern:

```bash
python3 -c "
import subprocess, os, tempfile

note_text = '''UPDATED_NOTE_TEXT'''

def to_html(text):
    lines = text.split('\n')
    parts = []
    for line in lines:
        stripped = line.strip()
        if stripped == '':
            parts.append('<div><br></div>')
        elif any(stripped.startswith(e) for e in ('📝', '🤖 C', '👤', '✅ C', '⏳')):
            parts.append(f'<div><b>{stripped}</b></div>')
        elif stripped.startswith('📌'):
            parts.append(f'<div><b>{stripped}</b></div>')
        elif stripped.startswith('Due:') or stripped.startswith('Context:') or stripped.startswith('Notes:'):
            parts.append(f'<div>&nbsp;&nbsp;&nbsp;{stripped}</div>')
        elif stripped.startswith('✅ ') or stripped.startswith('❌ '):
            parts.append(f'<div>{stripped}</div>')
        else:
            parts.append(f'<div>{line}</div>')
    return ''.join(parts)

html = to_html(note_text)
escaped = html.replace('\\\\', '\\\\\\\\').replace('\"', '\\\\\"')

script = f'''tell application \"Notes\"
  repeat with a in accounts
    repeat with f in folders of a
      if name of f is \"Tasks ✅\" then
        repeat with n in notes of f
          if name of n is \"📝 Claude Tasks\" or name of n is \"Claude Tasks\" then
            set body of n to \"{escaped}\"
            return
          end if
        end repeat
      end if
    end repeat
  end repeat
end tell'''

with tempfile.NamedTemporaryFile(mode='w', suffix='.scpt', delete=False) as f:
    f.write(script)
    tmp = f.name

subprocess.run(['osascript', tmp])
os.unlink(tmp)
"
```

---

## Step 7 — Create or update the Task Report note

The report title is always `📋 Task Report — DD Mon YYYY` (e.g. `📋 Task Report — 23 Mar 2026`).

**Check if a note with this exact title already exists** across all accounts — if yes, update its body. If no, create it. Never create duplicates.

### Report format — Apple-style

Design the report to look native to Apple Notes: clean hierarchy, generous whitespace, emoji as visual anchors, dividers for structure, bold for headings and task names, indented details. Think of it as a polished notification card, not a text dump.

**Template:**

```
📋  Task Report
DD Month YYYY  ·  N completed · N need you

━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅  Done  ·  N

   [emoji]  Task name
            → key finding or outcome line 1
            → key finding or outcome line 2
            💡 Recommendation: one-line call to action

━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌  Failed  ·  N

   ⚠️  Task name
            Reason: why it failed

━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤  Needs You  ·  N

   • Task name

━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Formatting rules:**
- Each task result gets its own block with a meaningful emoji (🛍 for shopping, 💰 for money/finance, ✈️ for travel, etc.)
- Use `→` for each key finding, max 2–4 bullets per task — distil, don't dump
- Add a `💡 Recommendation:` line when there's a clear action to take
- Use `━━━` dividers between sections (copy exact character)
- Omit sections with zero items
- The subtitle line (`DD Month YYYY · N completed · N need you`) uses a `·` (middle dot, option+shift+9 on Mac)

### HTML rendering

```bash
python3 -c "
import subprocess, os, tempfile
from datetime import date

today = date.today().strftime('%d %b %Y')
month_year = date.today().strftime('%d %B %Y')
title = f'📋 Task Report — {today}'

# Substitute the full report body as plain text before running
note_text = '''REPORT_TEXT'''

def to_html(text):
    lines = text.split('\n')
    parts = []
    for line in lines:
        stripped = line.strip()
        if stripped == '':
            parts.append('<div><br></div>')
        elif stripped.startswith('━'):
            parts.append(f'<div>{line}</div>')
        elif stripped.startswith('📋'):
            # Main title — bold and large feel
            parts.append(f'<div><b>{line}</b></div>')
        elif any(stripped.startswith(e) for e in ('✅', '❌', '👤')):
            # Section headers — bold
            parts.append(f'<div><br></div><div><b>{line}</b></div>')
        elif stripped and not stripped.startswith('→') and not stripped.startswith('•') and not stripped.startswith('💡') and line.startswith('   ') and not line.startswith('      '):
            # Task name line (single indent) — bold
            parts.append(f'<div><b>{line}</b></div>')
        else:
            parts.append(f'<div>{line}</div>')
    return ''.join(parts)

html = to_html(note_text)
escaped_html = html.replace('\\\\', '\\\\\\\\').replace('\"', '\\\\\"')
escaped_title = title.replace('\"', '\\\\\"')

# Update existing note if found in Tasks ✅ folder, otherwise create it there
script = f'''tell application \"Notes\"
  set found to false
  repeat with a in accounts
    repeat with f in folders of a
      if name of f is \"Tasks ✅\" then
        repeat with n in notes of f
          if name of n is \"{escaped_title}\" then
            set body of n to \"{escaped_html}\"
            set found to true
            exit repeat
          end if
        end repeat
        if not found then
          make new note at f with properties {{name:\"{escaped_title}\", body:\"{escaped_html}\"}}
          set found to true
        end if
        exit repeat
      end if
    end repeat
    if found then exit repeat
  end repeat
end tell'''

with tempfile.NamedTemporaryFile(mode='w', suffix='.scpt', delete=False) as f:
    f.write(script)
    tmp = f.name

subprocess.run(['osascript', tmp])
os.unlink(tmp)
"
```

---

## Step 8 — Print final summary

```
Run complete. ✅ Done: N | ❌ Failed: N | 👤 Needs you: N

Task report saved to Apple Notes: "📋 Task Report — DD Mon YYYY"
```

---

## Edge cases

- **Note missing**: stop early at Step 1 with clear message.
- **No pending tasks**: stop early at Step 2.
- **Note write fails after execution**: print the full results to chat as fallback so nothing is lost.
- **Running twice same day**: the report note is updated in-place, not duplicated.
- **Report note accumulation**: if the user asks to clean them up, delete all notes whose name matches `📋 Task Report —` via AppleScript.
- **Task invokes another skill**: invoke the skill normally; its output counts as the outcome summary.
- **Mixed formats in note**: handle both card (`📌`) and legacy (`- [ ]`) formats gracefully in the same run.
