# add-todo — Add Tasks to Apple Notes (macOS)

Adds tasks to your "Claude Tasks" Apple Note via natural language. Enforces specificity before saving — asks up to 2 clarifying questions for vague tasks (e.g. "buy a case for my phone" → asks which model, then budget/colour). Saves each task as a rich card with Due, Context, and Notes fields so `/run-todos` has full context at execution time.

## What it does

- Splits multi-task input into individual cards
- Evaluates whether each task is specific enough to execute — asks targeted questions if not
- Classifies as 🤖 (Claude can execute) or 👤 (human required)
- Writes a 4-line card block into the Apple Note under the correct section

## Card format

```
📌 Buy black iPhone 15 Pro case — under £20
   Due: —
   Context: User's device, colour and budget specified
   Notes: budget: under £20, colour: black
```

## Requirements

- macOS (uses AppleScript)
- Apple Notes app with a **"Tasks ✅"** folder

## Usage

```
add a todo: buy a case for my phone
remind me to email James about the renewal
add: call landlord, book dentist, research flights to Rome
```

Works best paired with `/run-todos` to execute the saved tasks.
