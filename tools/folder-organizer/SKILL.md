---
name: folder-organizer
description: Recursively scans a folder and reorganizes it into a clean semantic structure — by project, topic, or file type — and optionally renames files to follow consistent English naming conventions. Use this skill whenever the user wants to clean up, sort, reorganize, or tidy a directory, or when they want file names standardized or translated to English. Trigger on: "organize my Downloads folder", "clean up this directory", "sort my files", "tidy up ~/Desktop", "my folder is a mess", "reorganize this project", "group these files", "put my files in folders", "I have too many loose files", "clean up my documents", "rename my files to English", "fix my file names", "standardize file names", or any request involving restructuring or renaming files in a folder. Also trigger when the user pastes a file listing and asks what to do with it, or says "help me find structure in this folder".
---

# Folder Organizer

Scan a folder recursively, infer the best grouping for its contents, show a plan, get approval, then execute — no files move until the user says yes.

---

## Step 1 — Resolve the target path

If the user hasn't provided a folder path, ask one question: "Which folder should I organize? Please provide the full path (e.g. ~/Downloads or /Users/you/projects/old)."

Expand tilde and verify the path exists:

```bash
TARGET=$(eval echo "~/Downloads")   # substitute the user's path
[ -d "$TARGET" ] && echo "EXISTS" || echo "NOT FOUND"
```

If NOT FOUND: tell the user "That folder doesn't exist. Please check the path and try again." and stop.

Once the path is confirmed, ask one more question before scanning:

> "Should I also rename files to follow naming conventions — lowercase, hyphen-separated words, English only? (yes / no)"

Store the answer as `RENAME_MODE` (on/off). If the user already mentioned renaming in their original request, default to on and skip asking.

---

## Step 2 — Scan recursively

Collect all non-hidden files and all subdirectories:

```bash
# All non-hidden files, sorted
find "$TARGET" -type f -not -name ".*" | sort

# All subdirectories
find "$TARGET" -mindepth 1 -type d | sort

# File count
find "$TARGET" -type f -not -name ".*" | wc -l
```

**Stop conditions:**
- 0 files → "This folder is empty or contains only hidden files — nothing to organize." Stop.
- >500 files → "This folder has N files. To keep the plan readable I'll work with the 500 most recently modified. Want to proceed?" If they decline, stop.

```bash
# Get 500 most recent if over the cap
find "$TARGET" -type f -not -name ".*" -exec ls -t {} + 2>/dev/null | head -500
```

---

## Step 3 — Build the semantic plan (reasoning only — no file moves yet)

Look at all file names, extensions, and existing folder names. Decide the best grouping, using this priority order:

**1. Semantic prefix / topic** — if multiple files share a name pattern or clear theme, group them into a named folder. Examples: `invoice-jan-2024.pdf`, `invoice-feb-2024.pdf` → `invoices/`; `project-website-mockup.fig`, `project-website-notes.md` → `project-website/`. Prefer meaningful names over generic ones.

**2. File-type family** — when names give no clear semantic signal, fall back to extension buckets:

| Folder | Extensions |
|---|---|
| `images/` | jpg, jpeg, png, gif, webp, heic, raw, svg |
| `videos/` | mp4, mov, avi, mkv, webm |
| `audio/` | mp3, aac, wav, flac, m4a |
| `documents/` | doc, docx, odt, pages |
| `pdfs/` | pdf |
| `spreadsheets/` | xls, xlsx, csv, numbers |
| `presentations/` | ppt, pptx, key |
| `archives/` | zip, tar, gz, bz2, dmg, pkg, iso, rar |
| `code/` | py, js, ts, sh, rb, go, rs, java, c, cpp, h, html, css |
| `notes/` | md, txt, rst |

**3. Preserve sensible existing subfolders** — if `~/Downloads/work/` already exists and its contents clearly belong there, leave it. Move other files around it rather than renaming it.

**4. `_unsorted/`** — every file that doesn't fit anything goes here. No file is ever dropped or skipped (except dotfiles and symlinks — see edge cases).

For each file, decide: `source` path, `dest` path, and a one-word `reason` (e.g. "invoice", "screenshot", "project-website"). Files whose source dirname already equals their proposed dest dirname are marked `unchanged`.

**Conflict detection:** if two files would land at the same destination path, rename the second one by appending `_2` before the extension (e.g. `report.pdf` → `report_2.pdf`). Keep incrementing (`_3`, `_4`) until the name is unique.

### Renaming rules (only when RENAME_MODE is on)

For each file, derive a clean destination filename by applying these rules in order to the stem (everything before the last `.`), then re-attach the lowercased extension:

1. **Translate to English** — if the name (or recognizable words in it) is not English, translate those words to their English equivalent. Use your knowledge of common languages. Example: `Foto vacanza mare` → `beach-vacation-photo`, `rapport-mensuel` → `monthly-report`, `사진` → `photo`.

2. **Normalize accented / non-ASCII characters** — map to their closest ASCII equivalent: `é → e`, `ü → u`, `ñ → n`, `ç → c`, `ø → o`, `ß → ss`, etc.

3. **Lowercase everything.**

4. **Replace separators with hyphens** — spaces, underscores, dots inside the stem, and camelCase word boundaries all become single hyphens. `MyReport_Final v2` → `my-report-final-v2`.

5. **Strip remaining special characters** — keep only `a-z`, `0-9`, and `-`. Remove anything else.

6. **Collapse and trim hyphens** — replace consecutive hyphens with one; remove leading and trailing hyphens.

7. **Preserve meaningful numeric suffixes** — if the stem ends with a date or version (e.g. `2024-01`, `v2`, `final`), keep it.

If the computed clean name equals the original stem (already clean), mark the file as `unchanged` for renaming — don't show it as a rename in the plan.

The extension is always kept as-is (lowercased only): `.JPG → .jpg`, `.PDF → .pdf`.

Renaming is combined with moving: the destination path in the `mv` command uses the new filename, so both happen in a single operation.

---

## Step 4 — Present the plan

Show the full reorganization plan before doing anything. Format:

```
Reorganization plan for ~/Downloads
────────────────────────────────────────
47 files · 42 to move · 5 already in place
Rename mode: on  (or "off" if RENAME_MODE is off)

Proposed structure:

  invoices/         (12 files)
    Fattura-gennaio-2024.pdf  →  invoice-january-2024.pdf
    Fattura-febbraio-2024.pdf  →  invoice-february-2024.pdf
    invoice-mar-2024.pdf  (name unchanged)
    ... [+9 more]

  images/           (22 files)
    Foto vacanza.JPG  →  vacation-photo.jpg
    screenshot-2024-01-15.png  (name unchanged)
    banner.svg  (name unchanged)
    ... [+19 more]

  code/             (5 files)
    setup.py  (name unchanged)
    config.sh  (name unchanged)
    ... [+3 more]

  _unsorted/        (3 files)
    random-notes.txt  (name unchanged)
    untitled.doc  (name unchanged)
    weird-file.xyz  (name unchanged)

────────────────────────────────────────
Folders to create: invoices/, images/, code/, _unsorted/
Files to rename: 3
Dotfiles skipped: 2 (never moved)
Empty folders to remove after moves: old/, temp/
Conflicts: image.png → images/image_2.png

Proceed? (yes / no / edit)
```

When RENAME_MODE is off, omit the `→ new-name` annotations entirely and show filenames as-is.

Truncate each group at 3 filenames, then `[+N more]`. The user can ask "show me everything in images/" to see the full list before deciding.

**If the user says "edit" or wants changes:** adjust the affected groupings or rename proposals, re-present only the changed sections, and stay in this step until they approve.

Truncate each group at 3 filenames, then `[+N more]`. The user can ask "show me everything in images/" to see the full list before deciding.

**If the user says "edit" or wants changes:** adjust the affected groupings, re-present only the changed sections, and stay in this step until they approve.

---

## Step 5 — Confirmation gate

**Do not run any command that moves, renames, or deletes files until the user explicitly says yes, go ahead, do it, or equivalent.**

If the user says anything else, treat it as a request to clarify or modify the plan and loop back to Step 4.

---

## Step 6 — Execute

Run in three phases, in order.

**Phase A — Create destination directories:**

```bash
mkdir -p "$TARGET/invoices"
mkdir -p "$TARGET/images"
# one mkdir -p per proposed folder
```

**Phase B — Move files (one at a time, absolute paths):**

```bash
# Check for conflict, resolve if needed, then move
SRC="/full/path/to/source.pdf"
DEST="/full/path/to/dest/source.pdf"

if [ -f "$DEST" ]; then
  BASE="${DEST%.*}"
  EXT="${DEST##*.}"
  N=2
  while [ -f "${BASE}_${N}.${EXT}" ]; do N=$((N+1)); done
  DEST="${BASE}_${N}.${EXT}"
fi

mv -- "$SRC" "$DEST"
```

Always use `mv --` (double-dash) so filenames starting with `-` are handled safely. Always use the absolute expanded `$TARGET` path — never `cd`.

**Phase C — Remove empty source folders:**

```bash
find "$TARGET" -mindepth 1 -type d -empty -delete
```

`-mindepth 1` ensures `$TARGET` itself is never deleted.

---

## Step 7 — Print summary

```
Done. ~/Downloads reorganized.
────────────────────────────────────────
Moved:     42 files
Renamed:    3 files  (shown only when RENAME_MODE was on)
Skipped:   5 (already in place)
Conflicts: 2 (deduplicated with _2 suffix)
Removed:   2 empty folders (old/, temp/)

New structure:
  invoices/    12 files
  images/      22 files
  code/         5 files
  _unsorted/    3 files
```

If renaming was on, list all files that were renamed:
```
Files renamed:
  Fattura-gennaio-2024.pdf  →  invoice-january-2024.pdf
  Foto vacanza.JPG          →  vacation-photo.jpg
  rapport mensuel.docx      →  monthly-report.docx
```

If any conflict deduplication happened, list those too:
```
Deduplicated (name already existed at destination):
  image.png → images/image_2.png
```

---

## Edge cases

| Situation | Behavior |
|---|---|
| Path doesn't exist | Stop at Step 1 with "Folder not found" |
| Folder is empty / dotfiles only | Stop at Step 2 with "Nothing to organize" |
| More than 500 files | Warn, ask to cap at 500 most-recently-modified |
| File has no extension | Try name heuristics first; fall through to `_unsorted/` |
| Dotfiles (`.hidden`, `.DS_Store`) | Skip entirely; mention count in plan |
| Symlinks | Skip (`find -type f` excludes symlinks); mention in plan |
| Filename has spaces | Safe via double-quoted `"$SRC"` / `"$DEST"` |
| Filename starts with `-` | Safe via `mv --` |
| Source file disappears mid-run | Catch the mv error; report as skipped in summary |
| User says no at confirmation | "Cancelled. No files were moved." Stop. |
| User asks to undo after execution | "Undo requires reversing the moves manually. I can help — let me know which files to put back." |
| All files already in place | "Everything looks good — no files need to be moved." Stop. |
| File name is purely numeric (e.g. `20240115.jpg`) | Keep numbers as-is; don't translate them |
| Non-English name that can't be confidently translated | Keep the original transliterated/ASCII version rather than guessing; flag it in the plan with `(kept — translation unclear)` |
| Clean name collides with another file's clean name | Apply the `_2` deduplication suffix to the later file |
| Extension is uppercase (`.JPG`, `.PDF`) | Lowercase the extension in the clean name regardless of RENAME_MODE |
