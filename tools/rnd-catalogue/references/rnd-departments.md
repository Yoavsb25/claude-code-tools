# R&D department taxonomy — Engineering / Product / Data

Used by Catalogue mode's Stage 2 (see `../SKILL.md`) as the **primary** filter: if a posting's
`tags` (its department/category, as returned by `job_tool.py`) has a usable value, match it
against this file and stop there — the title is never consulted for these. Title-matching
(`rnd-titles.md`) only runs as a fallback when `tags` is empty or a known-generic bucket (e.g.
`"Other"`).

Match against each `tags` entry as a whole value, case-insensitively — not a title-style
substring search. A posting can have multiple tags (rare, but some sources allow it); it counts
as a match if *any* tag is in Include and *none* is in Exclude.

## Include

Engineering, R&D, Research, Research & Development, Product, Product Management, Data,
Data Science, Data & Analytics, AI, AI/ML, Machine Learning, Software Engineering,
Hardware Engineering.

## Exclude — takes priority over an Include match on another tag from the same posting

Sales, GTM, Marketing, Business Development, Customer Success, Delivery, Services,
Professional Services, Finance, Legal, Human Resources, People, Facilities, Administration,
Corporate Strategy.

## Ambiguous — use judgment, don't auto-include or auto-exclude

- **Security** — Cybersecurity/Information Security engineering is R&D; Corporate/Physical
  Security isn't. A bucket named bare `"Security"` (no further qualifier) needs a look at the
  posting itself before deciding either way.
- **Operations** — Engineering Ops / DevOps-adjacent buckets are R&D; general business
  Operations isn't. Same "look before deciding" rule as Security.
- **IT - Information Technology** — internal IT support usually isn't R&D; some companies fold
  platform engineering into an "IT" bucket instead of "Engineering". Check the posting.
- **Program Manager** — same caveat `rnd-titles.md` already documents for the title case: only
  R&D-scoped if the posting itself makes that clear, not by department label alone.

## Fallback trigger

Treat a posting's department data as unusable (fall through to `rnd-titles.md`'s title-matching
instead) when `tags` is empty, or every tag present is a company-specific label that carries no
generic meaning on its own (e.g. `"ORCAserv Technologies"` — a department tag that's really just
the company's own name, seen live on ORCA's Greenhouse board).
