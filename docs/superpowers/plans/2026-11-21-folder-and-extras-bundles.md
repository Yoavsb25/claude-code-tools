# Folder and Extras Bundles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `life`/`build` bundles with `home`, `money` (folder-scoped) and `extras` (installed, off), and delete three obsolete skills.

**Architecture:** Config only: `.claude-plugin/marketplace.json` in this repo, `claude plugin` installs, one line in `~/.claude/CLAUDE.md`. No code.

**Tech Stack:** Claude Code plugin marketplace, npm scripts (`generate-registry`, `validate`).

**Spec:** `docs/superpowers/specs/2026-11-21-everyday-extras-bundles-design.md`

## Global Constraints
- Nothing pushed. New commits only.
- Folder installs: `--scope local` in `~/Documents/3 Homes/London` (home) and `~/Documents/2 Money` (money).
- extras installed at user scope, then disabled.

## Review Focus
- amazon-shopper's description only triggers "from a run-todos task"; with run-todos gone it would never trigger. Make it standalone (Task 1).
- Stale installs: `life@yoav-tools` and `build@yoav-tools` must be uninstalled, or deleted skills keep loading from cache (Task 2 verify).
- tidy watches `~/Documents/0 Inbox` only, so the `.claude/` folders created in `2 Money` and `3 Homes/London` are not moved (Task 2 verify: still there after install).

---

### Task 1: Repo changes

**Files:**
- Delete: `tools/add-todo/`, `tools/run-todos/`, `tools/process-emails/`
- Modify: `.claude-plugin/marketplace.json`, `tools/amazon-shopper/SKILL.md:3,136`, `tools/amazon-shopper/README.md:11`
- Regenerated: `registry.json`, `README.md`

- [ ] **Step 1:** `git rm -r tools/add-todo tools/run-todos tools/process-emails`
- [ ] **Step 2:** amazon-shopper: description → "Use when the user wants to buy a physical item on Amazon (electronics, clothing, accessories, home items; not groceries, flights or services)."; line 136 → "One item per invocation."; README drops the run-todos clause.
- [ ] **Step 3:** marketplace.json plugins: `home` [ocado-shopper, ocado-deals], `money` [expense-analyzer, trip-expense-report], `extras` [flight-finder, stay-finder, amazon-shopper, tube-fare-auditor, tfl-refund, folder-organizer, software-architect, product-manager, ui-ux-expert, security-architect, testing-strategist, tech-stack-selector], `career` unchanged. Remove `life` and `build`.
- [ ] **Step 4:** Run `npm run generate-registry && npm run validate && claude plugin validate .` — expect no errors; `grep -rE 'add-todo|run-todos|process-emails' README.md registry.json .claude-plugin` returns nothing.
- [ ] **Step 5:** Commit `refactor: folder and extras bundles; drop todo and email skills` with the spec and this plan.

### Task 2: Installs and the CLAUDE.md hint

**Files:**
- Modify: `~/.claude/CLAUDE.md` (claude-config repo)

- [ ] **Step 1:** `claude plugin marketplace update yoav-tools`; `claude plugin uninstall life@yoav-tools build@yoav-tools` (user scope).
- [ ] **Step 2:** `claude plugin install extras@yoav-tools --scope user` then `claude plugin disable extras@yoav-tools`.
- [ ] **Step 3:** In `~/Documents/3 Homes/London`: `claude plugin install home@yoav-tools --scope local`. In `~/Documents/2 Money`: `claude plugin install money@yoav-tools --scope local`.
- [ ] **Step 4:** Add to `~/.claude/CLAUDE.md` under a `## Skills not loaded` heading: "The `extras@yoav-tools` bundle is installed but off: flight-finder, stay-finder, amazon-shopper, tube-fare-auditor, tfl-refund, folder-organizer, and the build skills (software-architect, product-manager, ui-ux-expert, security-architect, testing-strategist, tech-stack-selector). If a request matches one, offer to run `claude plugin enable extras@yoav-tools` (needs a restart). `home` is on in ~/Documents/3 Homes/London, `money` in ~/Documents/2 Money."
- [ ] **Step 5:** Verify `claude plugin list` from `~` (extras disabled; no life/build; no home/money), from each folder (its bundle enabled), and from `~/GitHub/job-search` (career enabled). `ls -a` both folders still show `.claude/`.
- [ ] **Step 6:** Commit in `~/.claude`: `docs: note the extras skill bundle`.
