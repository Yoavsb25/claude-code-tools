# run-todos — Execute Apple Notes Tasks (macOS)

Reads all pending tasks from your "Claude Tasks" Apple Note, classifies each as 🤖 Claude / 🤔 Maybe / 👤 Human, and executes the ones Claude can handle using available tools (browser, web search, Gmail, skills, etc.).

## Requirements
- macOS only (uses AppleScript)
- Apple Notes app with "Claude Tasks" note (created by `add-todo` skill)
- Relevant MCP tools available (Playwright, Gmail) for best coverage

## Usage (via Claude skill)

Copy `SKILL.md` into your project's `.claude/skills/run-todos/` and say "run my todos" in Claude Code.

After execution, Claude updates the note and writes a Task Report note with a summary of what was done.
