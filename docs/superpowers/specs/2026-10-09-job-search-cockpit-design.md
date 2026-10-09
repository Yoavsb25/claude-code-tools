# Job Search Cockpit — Design

Agreed with Yoav 2026-10-09. Extends the Job Radar (`tools/job-search/scripts/radar.py`) into the single
place the job search is run from. Nothing ever applies to a job or sends a message on Yoav's behalf.

## Why
41 applications went out between 2026-09-29 and 2026-10-08 (mostly LinkedIn Easy Apply / agencies, none
with a tailored CV). Volume is no longer the bottleneck; knowing what converts is. The tracker only gets
outcomes when Yoav hand-edits it, and records nothing about *how* each application was made, so nothing
can be learned from it.

## The flow
- **07:00, unattended** (launchd, plain Python, no LLM): radar refresh → inbox sync (IMAP, read-only) →
  ghosting pass.
- **Daily session, ~20–30 min, one local page**: Today (actions → review queue → follow-ups due) → Radar
  triage with tier choice → apply (Tier 1: warm-path check + tailored CV, ~2–3/week; Tier 2: standard CV,
  fast path). Yoav submits every application himself.
- **Weekly, ~30 min**: Insights tab — funnel and response rates by channel / positioning / tier, 3/2/1 KPIs.
  Make 1–2 adjustments.

## Components
1. **Tracker v2** (`job_tool.py`): statuses `Shortlisted → Applied → Responded → Phone Screen →
   Interviewing → Offer`, plus `Rejected`, `Ghosted`, `Withdrawn`. New fields `channel`
   (easy_apply | ats | agency | referral | other), `tier` (1 | 2), `positioning` (P1–P4), `events`
   (dated history: status changes and matched emails). Existing rows backfilled from notes/links.
   Applied rows with no reply for 21 days become `Ghosted` (only after a successful inbox sync).
2. **Inbox sync** (`inbox.py`): Gmail over IMAP with an app password from the macOS Keychain. Mailbox
   opened read-only, bodies fetched with `BODY.PEEK` — nothing marked read, moved, deleted or sent.
   Rule-based classifier (confirmation / rejection / interview / reply / viewed). Unambiguous matches
   update the tracker automatically (undoable); interview invites and replies become action items; anything
   uncertain goes to a review queue — never guessed.
3. **Cockpit page** (`radar.html` + `radar.py serve`): tabs Today, Radar, Pipeline, Insights. Pipeline
   replaces `~/Desktop/Job-Search/london-role-tracker.html`.
4. **Tier-1 helpers**: connections at the company inline (existing `connections.json` match), a
   "copy tailor command" button for `/resume-tailor`.

## Decisions
- Local page, not Claude sessions, is the home. Claude does the heavy, judgement steps on request.
- IMAP + app password, not Gmail API OAuth (testing-mode refresh tokens expire after 7 days — the same
  unattended-auth failure that killed the `claude -p` run).
- Auto-apply clear confirmations/rejections with undo; everything else surfaces for Yoav.
- Build order: tracker v2 → inbox sync → Today + Pipeline → Insights → Tier-1 helpers.
