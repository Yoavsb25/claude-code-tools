# R&D title taxonomy — Engineering / Product / Data

Used as a **fallback only** by Catalogue mode's Stage 2 (see `../SKILL.md`) — department data
(`references/rnd-departments.md`) is the primary R&D filter now. This file only applies when a
posting's `tags` is empty or a generic, company-specific label that carries no meaning on its
own; see `rnd-departments.md`'s "Fallback trigger" section for exactly when that is.

## Include — title contains any of

**Engineering**
Software Engineer, Software Developer, Backend Engineer, Front End / Frontend Engineer, Full
Stack Engineer, Platform Engineer, Infrastructure Engineer, DevOps Engineer, Site Reliability
Engineer / SRE, Systems Engineer, Cloud Engineer, Security Engineer, QA Engineer, Test Engineer,
Automation Engineer, Embedded Engineer, Firmware Engineer, Mobile Engineer, iOS Engineer, Android
Engineer, ML Engineer, Machine Learning Engineer, AI Engineer, Data Engineer, Release Engineer,
Build Engineer, Tools Engineer, Developer Experience Engineer, Internal Tools Engineer,
Engineering Manager, Head of Engineering, VP Engineering, Director of Engineering, Staff
Engineer, Principal Engineer.

**Product**
Product Manager, Technical Product Manager, Senior/Staff/Principal Product Manager, Technical
Program Manager, Technical Project Manager, Group Product Manager, Head of Product, VP Product,
Director of Product.

**Data**
Data Scientist, Data Analyst, Data Engineer (also listed under Engineering — same role, matches
either way), Analytics Engineer, Research Scientist, Applied Scientist, Research Engineer, ML
Scientist.

## Exclude — title contains any of, even if it also matches an include term above

Sales Engineer, Solutions Engineer (pre-sales flavor — check the JD if ambiguous; a posting
reporting into a Sales/Customer Success org is pre-sales even with "Engineer" in the title),
Sales Development, Customer Success Engineer, Support Engineer (unless clearly an internal
platform/tools role, not customer-facing support), Field Engineer (construction/industrial
sense), Recruiting/Talent, Marketing, Business Development, Account Manager/Executive, Finance,
Legal, HR/People, Office/Facilities.

## Department-tag veto

Superseded by `references/rnd-departments.md`, which is now the primary filter whenever a
posting's `tags` has a usable value — this file only runs at all when `tags` is empty/generic
(see the note above), so there's nothing left here to veto against.

## Ambiguous — use judgment, don't auto-exclude

- "Analyst" alone (could be Data Analyst, Business Analyst, Security Analyst) — check the JD.
- "Automation Engineer" (could be software test automation, or industrial/PLC automation) — the
  same ambiguity `job-search`'s own SKILL.md documents; check the JD before deciding.
- "Program Manager" without "Technical" — often non-R&D (e.g. a marketing/ops program manager);
  only include if the JD is clearly engineering/product-scoped.
