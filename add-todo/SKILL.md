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

Split into individual tasks. Each task becomes its own `- [ ]` line. If the input is clearly one task, keep it as one.

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
- "add: buy milk, call mum, renew passport" → 3 tasks:
  - `Buy milk`
  - `Call mum`
  - `Renew passport`

**Rule:** Keep related items that form a single purchase/action together (e.g. "2 cases and 2 screen protectors" = one task). Split when there are clearly separate, independent actions.

---

## Step 1b — Executability check

For each task, ask: does Claude have enough information to either execute it OR correctly identify it as a human task?

**The rule: ask at most ONE question per task, only if the answer changes whether Claude can execute it or would cause a clearly wrong outcome. Default to saving.**

If the task is clearly a 👤 human task regardless of detail (physical presence, services, etc.) — save it as-is. Don't ask.

**When to ask vs save:**

| Task | Action |
|---|---|
| "Buy a TV" | Ask: "What size and rough budget?" |
| "Buy a jacket" | Ask: "What size, and casual or smart?" |
| "Buy iPhone 17 cases" | Ask: "How many?" |
| "Buy a tie" | Ask: "Colour preference, or safe default (navy/white)?" |
| "Buy 2 iPhone 17 cases" | Save — specific |
| "Buy batteries" | Save as "Buy AA batteries (4-pack)" — safe default, note it |
| "Buy a white pocket square" | Save — specific |
| "Order milk and eggs" | Save — food, quantity flexible |
| "Email James about the meeting" | Ask: "Which James?" only if multiple in contacts — otherwise save |
| "Send a follow-up to the client" | Ask: "Which client, and about what?" — unexecutable otherwise |
| "Email mum to say thanks" | Save — clear enough |
| "Book a table for dinner" | Ask: "Where and for how many?" |
| "Book a dentist appointment" | Save — Claude will assess executability in pre-flight |
| "Research headphones" | Save — broad enough to execute |
| "Sort out the thing" | Ask: "What thing?" |
| "Pick up dry cleaning" | Save — clearly a 👤 task, no extra info needed |

**Never ask:**
- More than one question at a time
- If the task is unambiguously a 👤 human task (physical presence, no relevant skill)
- If a safe default exists and the stakes are low — just apply it and note the assumption

Once clarified, update the task text with the enriched detail before proceeding to Step 2.

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

## Step 3a — If note does NOT exist: create it in the "Tasks ✅" folder

```bash
osascript -e '
tell application "Notes"
  repeat with a in accounts
    repeat with f in folders of a
      if name of f is "Tasks ✅" then
        set noteBody to "<div><b>📝 Claude Tasks</b></div><div><br></div><div><b>⏳ Pending</b></div><div><br></div><div><b>✅ Completed</b></div>"
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

⏳ Pending

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

## Step 4 — Insert tasks into the note text

You now have the note as plain text and a list of one or more cleaned tasks. Rules:
- Find the line containing `⏳ Pending`
- Insert all `- [ ] <task>` lines immediately after it (or after the last existing `- [ ]` line in that section, whichever comes last)
- Insert each task on its own line
- Never insert into or after the `✅ Completed` section
- If the `⏳ Pending` header is missing, add it before the tasks at the top of the note

---

## Step 5 — Write back to the note

Build the HTML and write using a temp AppleScript file (this avoids shell-quoting issues when task text contains single quotes or apostrophes):

```bash
python3 -c "
import subprocess, os, tempfile

# Substitute the full updated note as plain text before running
note_text = '''FULL_NOTE_TEXT_HERE'''

def to_html(text):
    lines = text.split('\n')
    parts = []
    for line in lines:
        if line.strip() == '':
            parts.append('<div><br></div>')
        elif any(line.startswith(e) for e in ('📝', '⏳', '✅')):
            parts.append(f'<div><b>{line}</b></div>')
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
Added: "<task>" to Claude Tasks
```

If multiple tasks were added:
```
Added 3 tasks to Claude Tasks:
- <task 1>
- <task 2>
- <task 3>
```

---

## Edge cases

- **`osascript` read returns an error or NOT FOUND**: stop and tell the user. Do not overwrite.
- **Task input is empty or too vague** (e.g. just "todo"): ask "What task should I add?"
- **`⏳ Pending` header is missing from the note**: add it before inserting the task rather than failing.
- **"Tasks ✅" folder not found**: tell the user the folder is missing and ask them to create it in Notes.
