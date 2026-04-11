---
name: add-todo
description: Add a task to the "Claude Tasks" Apple Note. Use when the user says "add a todo", "remind me to", "add to my task list", "add this to my tasks", or describes something they want to remember or have Claude do later.
disable-model-invocation: true
---

# Add Todo

Add a task to the "Claude Tasks" Apple Note — the persistent list that `/run-todos` will execute later.

The note lives in the **"Tasks ✅"** folder in Notes.

---

## Step 1 — Split and clean up tasks

First, detect whether the input contains **multiple tasks**. Tasks may be separated by:
- "and" / "also" / "plus" joining distinct actions
- Commas or semicolons between distinct actions
- Numbered or bulleted lists
- Line breaks

Split into individual tasks. Each task becomes its own card. If the input is clearly one task, keep it as one.

Then clean up each task individually:
- Remove filler ("please", "can you", "remind me to", "I need to")
- Start with a verb if not already ("Research...", "Book...", "Check...", "Send...", "Order...")
- Keep it concise — one line, no trailing punctuation

**Examples:**
- "remind me to check if my passport is still valid" → 1 task: `Check passport expiry date`
- "order 2 iPhone 17 cases and 2 screen protectors" → 1 task: `Order 2 iPhone 17 cases and 2 screen protectors` (same purchase, keep together)
- "book a dentist and call the landlord and research flights to Rome" → 3 tasks:
  - `Book dentist appointment`
  - `Call landlord`
  - `Research flights to Rome`

**Rule:** Keep related items that form a single purchase/action together. Split when there are clearly separate, independent actions.

---

## Step 1b — Specificity + Executability Check

For each task, evaluate **two things**:

### A — Specificity check (for 🤖 tasks only)

Ask: *would executing this task right now require making a significant assumption the user would likely care about?*

**Key triggers — always evaluate specificity for:**
- Any "buy/order/get" task → does it need a device model, size, quantity, or budget to buy correctly?
- Any "book/reserve" task → is the venue, date, and party size known?
- Any "email/send/reply/call" task → is the recipient unambiguous and the core ask clear?

**The rule: ask at most 2 questions per task (max), only when the answer would change what gets bought/done and a wrong assumption could waste money or time.**

If a safe default clearly exists and the stakes are low — apply it and note the assumption. Don't ask.

If the task is a 👤 human task regardless of specifics (physical presence required, etc.) — save as-is. No questions.

**Reference table:**

| Task | Action |
|---|---|
| "Buy a case for my phone" | Ask: "Which phone model?" → after answer, ask: "Any colour or budget preference, or just cheapest?" |
| "Buy a case for my iPhone 15 Pro" | Ask: "Any colour preference or budget?" |
| "Buy a black case for my iPhone 15 Pro under £15" | Save — fully specific |
| "Buy headphones" | Ask: "Any budget and use-case (gym, office, commute)?" |
| "Buy a TV" | Ask: "What screen size and rough budget?" |
| "Buy a jacket" | Ask: "What size, and casual or smart?" |
| "Buy iPhone 17 cases" | Ask: "How many?" |
| "Buy a tie" | Ask: "Colour preference, or safe default (navy/white)?" |
| "Buy 2 iPhone 17 cases" | Save — specific |
| "Buy batteries" | Save as "Buy AA batteries (4-pack)" — safe default |
| "Buy a white pocket square" | Save — specific |
| "Order milk and eggs" | Save — food, quantity flexible |
| "Book a restaurant" | Ask: "Which restaurant and for when / how many people?" |
| "Book a dentist appointment" | Save — Claude will assess executability at run time |
| "Email James about the project" | Ask: "Which James?" only if ambiguous — otherwise Save |
| "Send a follow-up to the client" | Ask: "Which client, and about what?" |
| "Email mum to say thanks" | Save — clear enough |
| "Research headphones under £200" | Save — specific enough |
| "Sort out the thing" | Ask: "What thing?" |
| "Pick up dry cleaning" | Save — clearly 👤, no extra info needed |

**After getting answers**: incorporate all clarification into the enriched task text and Notes field. Then stop — do not ask a third question.

### B — Classification

After enrichment, classify each task:
- `🤖` — Claude can complete end-to-end using available tools (Amazon/Ocado shopper skills, Gmail MCP, web search, browser, file ops)
- `👤` — requires physical presence, a phone call, or context Claude cannot resolve

---

## Step 2 — Check if "Claude Tasks" note exists in the "Tasks ✅" folder

```bash
osascript -e '
tell application "Notes"
  repeat with a in accounts
    repeat with f in folders of a
      if name of f is "Tasks ✅" then
        repeat with n in notes of f
          if name of n is "📝 Claude Tasks" or name of n is "Claude Tasks" then
            return "EXISTS"
          end if
        end repeat
        return "FOLDER_EXISTS_NO_NOTE"
      end if
    end repeat
  end repeat
  return "NOT FOUND"
end tell'
```

---

## Step 3a — If note does NOT exist: create it with new structure

```bash
osascript -e '
tell application "Notes"
  repeat with a in accounts
    repeat with f in folders of a
      if name of f is "Tasks ✅" then
        set noteBody to "<div><b>📝 Claude Tasks</b></div><div><br></div><div><b>🤖 Claude</b></div><div><br></div><div><b>👤 Human</b></div><div><br></div><div><b>✅ Completed</b></div>"
        make new note at f with properties {name:"📝 Claude Tasks", body:noteBody}
        return
      end if
    end repeat
  end repeat
end tell'
```

Treat the note body as:
```
📝 Claude Tasks

🤖 Claude

👤 Human

✅ Completed
```

Proceed to Step 4.

---

## Step 3b — If note exists: read the body

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
text = html.replace('<br>', '\n').replace('<br/>', '\n').replace('</div>', '\n').replace('</p>', '\n')
text = re.sub('<[^>]+>', '', text)
text = re.sub(r'\n{3,}', '\n\n', text).strip()
print(text)
"
```

---

## Step 4 — Build card blocks and insert into note

You now have the note as plain text and the list of enriched, classified tasks.

### Card format

Each task becomes a 4-line card block:
```
📌 <enriched task — specific enough to execute>
   Due: <extracted date (e.g. 28 Mar) or —>
   Context: <one sentence: why this task exists, any background>
   Notes: <execution constraints: device model, budget, quantity, recipient email, etc. — or —>
```

### Insertion rules

- Detect note structure: if the note has `🤖 Claude` and `👤 Human` headers → new structure. If it only has `⏳ Pending` → old structure, migrate first (rename `⏳ Pending` → `🤖 Claude`, insert `👤 Human` block before `✅ Completed`).
- Insert 🤖 cards after the last card in the `🤖 Claude` section (or immediately after the `🤖 Claude` header if empty).
- Insert 👤 cards after the last card in the `👤 Human` section.
- Never insert into or after the `✅ Completed` section.

---

## Step 5 — Write back to the note

Build the HTML and write using a temp AppleScript file:

```bash
python3 -c "
import subprocess, os, tempfile

# Substitute the full updated note as plain text before running
note_text = '''FULL_NOTE_TEXT_HERE'''

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

## Step 6 — Confirm to the user

If one task was added:
```
Added to Claude Tasks (🤖):
📌 Buy black iPhone 15 Pro case — under £20
   Context: User's device, colour and budget specified
```

If multiple tasks were added:
```
Added 3 tasks to Claude Tasks:

🤖 📌 Buy black iPhone 15 Pro case — under £20
      Context: User's device, colour and budget specified

👤 📌 Pick up dry cleaning
      Context: —

🤖 📌 Research flights to Rome — economy, flexible dates
      Context: User planning a trip
```

---

## Edge cases

- **`osascript` read returns an error or NOT FOUND**: stop and tell the user. Do not overwrite.
- **Task input is empty or too vague** (e.g. just "todo"): ask "What task should I add?"
- **"Tasks ✅" folder not found**: tell the user the folder is missing and ask them to create it in Notes.
- **Old `⏳ Pending` structure detected**: migrate before inserting (rename header, add `👤 Human` block).
