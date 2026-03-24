# add-todo — Apple Notes Task Manager (macOS)

Adds tasks to a "Claude Tasks" note in Apple Notes. Works alongside `run-todos` to create a persistent task queue that Claude can execute later.

## Requirements
- macOS only (uses AppleScript)
- Apple Notes app
- A folder called "Tasks ✅" in Notes

## Usage (via Claude skill)

Copy `SKILL.md` into your project's `.claude/skills/add-todo/` and say "add a todo: [task]" in Claude Code.

Claude handles splitting multiple tasks, cleaning up phrasing, and asking clarifying questions only when needed.
