# claude-code-tools

A registry of Claude Code skills and automation tools. Each tool lives in `tools/<name>/` and has a `manifest.json` + `SKILL.md` (and optionally a `README.md`).

## Commands

```bash
npm run generate-registry   # Rebuild registry.json and update README.md from all manifests
npm run validate            # Validate all tools/*/manifest.json against manifest.schema.json
```

Website (separate package in `website/`):
```bash
cd website && npm run dev   # Dev server
cd website && npm run build # tsc + vite build
cd website && npm run lint  # ESLint, zero warnings
```

## Tool Structure

```
tools/<name>/
  manifest.json   # Required — metadata, install paths, requirements
  SKILL.md        # Required — the skill content Claude loads
  README.md       # Optional — human-facing docs
```

## Manifest Rules

Valid enum values (enforced by schema):
- `type`: `"skill"` (SKILL.md only) | `"tool"` (Python code + skill)
- `category`: `productivity` | `shopping` | `finance` | `developer-tools` | `automation`
- `complexity`: `simple` | `intermediate` | `advanced`

Install `dest` paths use `~/.claude/skills/<name>.md` convention.

## Skills

Before modifying any skill in `tools/`, check `docs/superpowers/specs/` for the relevant design spec.
