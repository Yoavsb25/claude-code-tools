# Stage 1 — Intake details

Read from SKILL.md Stage 1 when `roles` isn't set, a role title is ambiguous, or `salary_floor`/`seniority` were just set or changed.

**Role discovery.** Run this when `roles` isn't set yet (first run and the user hasn't already
named a role) or whenever the user explicitly asks for help figuring out what to search for
("what roles should I look at", "suggest some titles", "I'm not sure what I want next").

1. **Ask about direction before assuming continuity.** Don't default to "more of the same" just
   because a resume shows a long history in one field — ask directly: *"Are you looking to
   continue in your current field, or make a change? (Someone with 30 years as a software
   engineer might now want something totally different — like becoming a pilot. Tell me if
   that's the kind of shift you're making.)"* Take whatever direction the user states at face
   value; it overrides anything the resume implies.
2. **If they name a clear pivot or a specific role themselves:** use that directly as `roles` —
   skip resume-based suggestions entirely. The resume can still inform Stage 3's requirements-fit
   scoring (transferable skills), but it must never override a direction the user explicitly
   stated.
3. **If they're continuing in their field, or ask for suggestions:** use the profile's `skills`,
   `education`, and `experience_summary` (from `profile show` in Stage 0) to propose exactly 5
   candidate role titles that fit their background and stated direction. If those fields aren't
   set yet, ask for them first (see Stage 1's field table) rather than guessing from `roles` alone.
   Present the 5 titles as a numbered list with a one-line rationale each, and ask which (if any)
   to add. **Never add a suggested title to `roles` without explicit confirmation** — this is a
   suggestion, not a decision the skill gets to make. Once confirmed, save via `profile set` like
   any other Stage 1 change.

**Ambiguous role titles.** Some titles carry more than one industry meaning — e.g. "Automation
Engineer" can mean industrial/PLC/manufacturing automation *or* software test/process automation;
"Analyst" can mean business, data, or security analyst. **Being adjacent to another role in the
`roles` list does not by itself resolve the ambiguity** — a "Software Engineer" entry sitting next
to "Automation Engineer" is not sufficient context to assume the software-automation reading; that
inference has been wrong in practice. Only treat an ambiguous title as resolved if the stored role
string itself already carries an explicit qualifier (e.g. "Software Automation Engineer," "QA
Automation Engineer," "Test Automation Engineer," "Industrial Automation Engineer"). Otherwise, ask
a one-line clarifying question during Stage 1 intake — before Stage 2 runs any search for that
role — rather than discovering the mismatch mid-search after already spending calls on the wrong
industry's postings.

**Salary floor vs. seniority sanity check.** Whenever `salary_floor` and `seniority` are both set
(on profile creation or edit) and `seniority` reads as junior/entry-level, run one `WebSearch` for
typical market salary at that role/seniority/location combination — e.g. `"[role] [seniority]
salary [location]"` — before running the full multi-source search. If the floor looks materially
above what the search turns up, flag it to the user up front, e.g.: *"Your £60k floor is well
above typical London junior rates (~£35–49k) — want to adjust it, or proceed knowing most matches
may fall short?"* Let them adjust or explicitly proceed before spending the full search budget,
rather than only discovering the mismatch after several rounds of per-posting salary enrichment in
Stage 3. This matters more than it used to: a floor set too high no longer just produces
low-lighted postings, it can silently exclude most or all disclosed-salary results outright (see
Stage 3's Constraint fit rule below), so catching a mismatch here before running the full search is
worth the one extra `WebSearch` call. This is a single check at intake time — distinct from, and in addition to, the per-posting
salary enrichment in Stage 3 for the near-final shortlist.
