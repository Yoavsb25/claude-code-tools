# folder-organizer

A Claude Code skill that recursively scans any folder, proposes a semantic reorganization plan, and executes it only after you approve.

## What it does

1. Scans all files and subfolders recursively
2. Groups them intelligently — by project/topic first, then by file type as a fallback
3. Shows you exactly what will move before touching anything
4. Executes the moves with standard bash (`mv`, `mkdir`, `find`)

## How to use it

Just tell Claude what you want to clean up:

- "Organize my Downloads folder"
- "My ~/Desktop is a mess, can you sort it out?"
- "Clean up /Users/me/projects/old"
- "Tidy up this directory: /tmp/work"

Claude will scan the folder, propose a structure, and wait for your go-ahead.

## Grouping logic

Files are grouped in priority order:

1. **Semantic theme** — shared name patterns become named folders (`invoice-*.pdf` → `invoices/`)
2. **File type** — images, videos, documents, code, archives, etc.
3. **`_unsorted/`** — catch-all so nothing is ever dropped

## Safety

- Nothing moves until you explicitly approve the plan
- Dotfiles and symlinks are never touched
- Name conflicts are resolved by appending `_2`, `_3`, etc. — files are never overwritten
- Empty folders are cleaned up after moves

## Requirements

- macOS or Linux (uses standard POSIX tools: `find`, `mv`, `mkdir`)
- No Python, no dependencies
