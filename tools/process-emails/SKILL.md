---
name: process-emails
description: Fully-automatic email-to-todo pipeline. Reads unread Gmail from the last 24h, extracts context-rich action items using a single Claude reasoning pass, pre-classifies each as 🤖 (Claude can execute) or 👤 (human required), deduplicates against existing todos, and writes everything to the "Claude Tasks" Apple Note in one shot. Use whenever the user says "process my emails", "check my emails", "email todos", "what do I need to do from my emails", or invokes /process-emails. Designed to minimise token usage: snippets-first, one batch Claude call, one Notes write.
---

# Process Emails

Read unread Gmail from the last 24h, extract action items, and add them to the "Claude Tasks" Apple Note — no confirmation needed.

---

## Step 1 — Fetch unread emails

Use `gmail_search_messages` with query `is:unread newer_than:1d`. Cap results at 30.

If 0 results: print `No unread emails in the last 24h.` and stop.

---

## Step 2 — Read snippets (with full-body fallback)

For each message, call `gmail_read_message` to get: `subject`, `from` (name + email), `snippet`.

**Full-body fallback:** if a message's snippet contains any of `"see attached"`, `"please find"`, `"as discussed"`, `"see below"`, `"per our conversation"`, or is under 40 characters — fetch the full body for that message only. Replace the snippet with the first 800 chars of the body. This handles the common case where the snippet gives zero actionable context.

---

## Step 3 — Single Claude reasoning pass

Build one prompt with all messages as compact JSON:

```json
[
  {"from_name": "Sarah Chen", "from_email": "sarah@acme.com", "subject": "Draft contract", "content": "<snippet or body excerpt>"},
  ...
]
```

Instruct Claude to:

1. **Filter out** FYI/automated emails: newsletters, marketing, GitHub/Jira/Slack digests, shipping notifications, bank transaction alerts, calendar invites with no required action, automated receipts.

2. **For each actionable email**, extract a structured card:
   - `task`: one-line action starting with a strong verb (Reply, Review, Book, Call, Pay, etc.). Include who is involved + their email if it's needed to execute.
     - Good: `Reply to Sarah Chen (sarah@acme.com) — draft consulting contract`
     - Bad: `Reply to Sarah about contract`
   - `classification`: `"🤖"` if Claude can complete end-to-end (send/draft email via Gmail MCP, web search, research, file ops); `"👤"` if it requires physical presence, a phone call, or context Claude can't resolve from the email alone
   - `due`: extract from email if a deadline is mentioned (format as `DD Mon`, e.g. `28 Mar`). Otherwise `"—"`.
   - `context`: the key background detail in one sentence — sender relationship + email subject essence (e.g. `"Consulting contract from Sarah Chen needs sign-off"`). Otherwise `"—"`.
   - `notes`: anything needed to execute that isn't in the task line — email address if not already there, attachment note, CC instructions. Otherwise `"—"`.

3. Return **only** a JSON array, no explanation:
   ```json
   [
     {
       "task": "Reply to Sarah Chen (sarah@acme.com) — draft consulting contract",
       "classification": "🤖",
       "due": "28 Mar",
       "context": "Consulting contract attached, needs sign-off",
       "notes": "CC James on the reply"
     }
   ]
   ```
   Return `[]` if nothing is actionable.

If Claude returns `[]`: print `Processed N emails — nothing actionable found.` and stop.

---

## Step 4 — Deduplicate against existing todos

Read the current "Claude Tasks" note:

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
        return "FOLDER_EXISTS_NO_NOTE"
      end if
    end repeat
  end repeat
  return "NOT FOUND"
end tell' | python3 -c "
import sys, re
html = sys.stdin.read()
if html.strip() in ('NOT FOUND', 'FOLDER_EXISTS_NO_NOTE'):
    print('')
else:
    text = html.replace('<br>', '\n').replace('<br/>', '\n').replace('</div>', '\n').replace('</p>', '\n')
    text = re.sub('<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ').replace('&#160;', ' ')
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    # Extract pending task names from card format (📌 lines) and old - [ ] format
    in_pending = False
    for line in text.split('\n'):
        stripped = line.strip()
        if '🤖 Claude' in stripped or '👤 Human' in stripped or '⏳ Pending' in stripped:
            in_pending = True
        elif '✅ Completed' in stripped:
            in_pending = False
        elif in_pending and stripped.startswith('📌 '):
            print(stripped[2:].strip())
        elif in_pending and stripped.startswith('- [ ] '):
            print(stripped[6:].strip())
"
```

For each extracted todo from Step 3, skip it if there is a semantically similar existing task — match on the key person/entity name AND the core action. Don't require exact text match.

If all todos are duplicates: print `All extracted todos already exist in Claude Tasks.` and stop.

---

## Step 5 — Write new todos to Apple Notes

Insert all non-duplicate tasks as card blocks into the "Claude Tasks" note. Use the temp AppleScript file pattern:

```bash
python3 -c "
import subprocess, os, tempfile

# --- SUBSTITUTE the variables below before running ---
# existing_note_text: full plain-text body of the note (or empty string if note doesn't exist yet)
# claude_cards: list of dicts {task, due, context, notes} for 🤖 tasks
# human_cards: list of dicts {task, due, context, notes} for 👤 tasks

existing_note_text = '''EXISTING_NOTE_TEXT_HERE'''
claude_cards = [{'task': '...', 'due': '—', 'context': '—', 'notes': '—'}]  # substitute
human_cards  = [{'task': '...', 'due': '—', 'context': '—', 'notes': '—'}]  # substitute

def card_lines(c):
    return [
        f'📌 {c[\"task\"]}',
        f'   Due: {c[\"due\"]}',
        f'   Context: {c[\"context\"]}',
        f'   Notes: {c[\"notes\"]}',
        '',
    ]

def insert_cards(note_text, claude_cards, human_cards):
    lines = note_text.split('\n') if note_text.strip() else []

    # Migrate old ⏳ Pending → 🤖 Claude structure
    has_new_structure = any('🤖 Claude' in l or '👤 Human' in l for l in lines)
    if not has_new_structure:
        for i, line in enumerate(lines):
            if '⏳ Pending' in line:
                lines[i] = '🤖 Claude'
                completed_idx = next((j for j, l in enumerate(lines) if '✅ Completed' in l), len(lines))
                lines.insert(completed_idx, '')
                lines.insert(completed_idx, '👤 Human')
                break

    def find_insert_point(lines, header):
        insert_at = None
        in_section = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if header in stripped:
                in_section = True
                insert_at = i + 1
            elif in_section and any(h in stripped for h in ('🤖', '👤', '✅') if h not in header):
                in_section = False
            elif in_section and (stripped.startswith('📌') or stripped.startswith('✅ ')):
                # Skip past the 4-line card block
                insert_at = min(i + 4, len(lines))
        return insert_at

    for cards, header in [(claude_cards, '🤖 Claude'), (human_cards, '👤 Human')]:
        if not cards:
            continue
        idx = find_insert_point(lines, header)
        if idx is None:
            completed_idx = next((j for j, l in enumerate(lines) if '✅ Completed' in l), len(lines))
            lines.insert(completed_idx, '')
            lines.insert(completed_idx, header)
            idx = completed_idx + 1
        new_lines = []
        for c in cards:
            new_lines.extend(card_lines(c))
        for j, l in enumerate(new_lines):
            lines.insert(idx + j, l)

    return '\n'.join(lines)

def to_html(text):
    lines = text.split('\n')
    parts = []
    for line in lines:
        stripped = line.strip()
        if stripped == '':
            parts.append('<div><br></div>')
        elif any(stripped.startswith(e) for e in ('📝', '🤖', '👤', '✅ C')):
            parts.append(f'<div><b>{stripped}</b></div>')
        elif stripped.startswith('📌'):
            parts.append(f'<div><b>{stripped}</b></div>')
        elif stripped.startswith('✅ ') and not stripped.startswith('✅ C'):
            parts.append(f'<div><b>{stripped}</b></div>')
        elif stripped.startswith('Due:') or stripped.startswith('Context:') or stripped.startswith('Notes:'):
            parts.append(f'<div>&nbsp;&nbsp;&nbsp;{stripped}</div>')
        else:
            parts.append(f'<div>{line}</div>')
    return ''.join(parts)

updated_text = insert_cards(existing_note_text, claude_cards, human_cards)
html = to_html(updated_text)
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
        -- Note does not exist yet: create it
        set noteBody to \"{escaped}\"
        make new note at f with properties {{name:\"📝 Claude Tasks\", body:noteBody}}
        return
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

## Step 6 — Print summary

```
Processed 18 emails (12 filtered as noise, 1 skipped duplicate) → 4 action items added to Claude Tasks:

🤖 Reply to Sarah Chen — draft consulting contract, sign-off by 28 Mar
   Due: 28 Mar  ·  Context: Consulting contract attached, needs sign-off
🤖 Book car service at Kwik Fit — quote expires 31 Mar
   Due: 31 Mar  ·  Context: —
👤 Call landlord about boiler inspection
   Due: —  ·  Context: —
👤 Renew home insurance — reminder from Direct Line
   Due: —  ·  Context: Renewal reminder from Direct Line

Run /run-todos when ready to execute the 🤖 ones.
```

Counts to include: total emails fetched, filtered as noise, skipped as duplicates, added.

---

## Edge cases

- **0 emails fetched**: `No unread emails in the last 24h.` — stop.
- **0 actionable after Claude pass**: `Processed N emails — nothing actionable found.` — stop.
- **0 new after dedup**: `All extracted todos already exist in Claude Tasks.` — stop.
- **Notes app not running or "Tasks ✅" folder missing**: report the error clearly; do not attempt to write.
- **AppleScript write fails**: print the extracted todos to chat as fallback so nothing is lost.
