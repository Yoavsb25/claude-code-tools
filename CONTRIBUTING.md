# Contributing

Want to add a skill or tool to the registry? Here's how.

## Structure

Every contribution lives in `tools/<name>/` and needs at minimum:

```
tools/<name>/
├── manifest.json   ← required: structured metadata (see schema)
├── SKILL.md        ← required: Claude Code skill definition
└── README.md       ← required: user-facing documentation
```

For tools with Python code, also include:
```
tools/<name>/
├── requirements.txt
├── <script>.py
└── tests/          ← optional but encouraged
    └── test_<name>.py
```

## manifest.json

Your manifest must validate against [`manifest.schema.json`](./manifest.schema.json). Here's a minimal example:

```json
{
  "name": "my-skill",
  "version": "1.0.0",
  "description": "One sentence describing what this skill does for the user",
  "type": "skill",
  "category": "productivity",
  "complexity": "simple",
  "tags": ["macos", "automation"],
  "install": {
    "files": [
      { "src": "SKILL.md", "dest": "~/.claude/skills/my-skill.md" }
    ]
  },
  "requirements": {
    "platform": "any",
    "mcp_servers": [],
    "env_vars": []
  }
}
```

**`type`** — `skill` (SKILL.md only) or `tool` (Python code + skill)
**`category`** — one of: `productivity`, `shopping`, `finance`, `developer-tools`, `automation`
**`complexity`** — `simple` (5-min setup), `intermediate` (requires MCP/config), `advanced` (Python + dependencies)
**`platform`** — `any`, `macos`, `linux`, or `windows`

## README.md template

```markdown
# <name>

One-sentence description.

## Usage

Trigger phrase or slash command in Claude Code.

## Requirements

- Platform: macOS / any
- MCP servers: playwright (if needed)
- Environment variables: (if any)

## How it works

Short explanation of what Claude does step by step.
```

## CI checks

Pull requests automatically run:
- JSON Schema validation of your `manifest.json`
- File reference checks (all `install.files` must exist)
- `pytest` if a `tests/` directory is present
- CLI build verification

Fix any failures before requesting review.

## Updating the registry

The registry regenerates automatically when manifests change on `main`. You don't need to run `generate-registry.ts` manually.
