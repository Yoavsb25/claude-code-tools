# R&D title taxonomy — Engineering / Product / Data

Used by catalogue mode's Stage 2 (see `../SKILL.md`) to decide whether a posting counts as
"R&D" for the inventory. Match against the posting's **title** first; where a `tags`/department
field is available (Greenhouse and Lever both expose one), use it as a corroborating veto, not
the primary signal — see "Department-tag veto" below.

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

## Department-tag veto (when available)

If the posting's `tags` list includes any of: Sales, Marketing, Business Development, Customer
Success, Finance, Legal, People/HR, G&A — exclude it regardless of title match. Greenhouse/Lever
populate `tags` from the board's own department field; treat it as more reliable than the title
alone when present.

## Ambiguous — use judgment, don't auto-exclude

- "Analyst" alone (could be Data Analyst, Business Analyst, Security Analyst) — check the JD.
- "Automation Engineer" (could be software test automation, or industrial/PLC automation) — the
  same ambiguity `job-search`'s own SKILL.md documents; check the JD before deciding.
- "Program Manager" without "Technical" — often non-R&D (e.g. a marketing/ops program manager);
  only include if the JD is clearly engineering/product-scoped.
