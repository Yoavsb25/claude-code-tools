# SysAid Source Guide

Reference this file to decide which source files to load. Files are grouped by type, with a noise level and "best for" column so you load only what moves the needle for a given JD.

---

## Profile Summaries
*Noise level: Low — pre-processed narratives, already in professional voice.*

| File | Contains | Best for |
|---|---|---|
| `~/Desktop/Work/SysAid/profile-summaries/overall-profile.md` | Full career narrative across all quarters. Impact metrics (75% faster, 7 languages, 29 components, 88% completion rate). LinkedIn-style highlights. The highest-signal file in the archive. | Always load first — gives the full picture |
| `~/Desktop/Work/SysAid/profile-summaries/2025-Q3-profile.md` | Q3 2025 narrative: release automation foundation, translation tooling genesis, deployment utilities | Roles where "greenfield ownership" or "building from scratch" is valued |
| `~/Desktop/Work/SysAid/profile-summaries/2025-Q4-profile.md` | Q4 2025 narrative: translation tools at scale, CSV/analytics/E2E tests, Kargo adoption begins, deployment workflow overhaul | Roles emphasizing scaling systems or GitOps migration |
| `~/Desktop/Work/SysAid/profile-summaries/2026-Q1-profile.md` | Q1 2026 narrative: Kargo migration completion, translation UX polish, Claude Code skills, deployment safety | Roles emphasizing AI tooling, delivery maturity, or cross-team infrastructure |
| `~/Desktop/Work/SysAid/profile-summaries/2026-Q2-profile.md` | Q2 2026 narrative: code architecture refactoring (dependency injection, lazy initialization) | Roles emphasizing code quality, refactoring, or engineering standards |

---

## Project Context Files
*Noise level: Medium — detailed technical deep-dives with What/Why/How/Role/Impact/State sections.*

| File | Contains | Best for |
|---|---|---|
| `~/Desktop/Work/SysAid/projects-context/translation-tools.md` | Full-stack React + Express + Node.js 24 platform. Google Gemini integration. GitHub App auth. Kubernetes + Docker. 80% backend test coverage (Jest + Vitest + Playwright). Solo ownership from scratch. Impact: 7 languages supported, 75% faster workflow. | Full-stack, frontend, React, TypeScript, testing-heavy, or AI integration roles |
| `~/Desktop/Work/SysAid/projects-context/deployment-workflows.md` | GitHub Actions CI/CD system. 15 workflows, 24 composite actions, component registry (29 components). CSMP → Kargo/ArgoCD migration (3-phase). Quality gates, full audit trail, zero manual steps. Solo ownership from scratch. | DevOps, Platform Engineering, CI/CD, GitOps, Kubernetes, or infrastructure roles |
| `~/Desktop/Work/SysAid/projects-context/release-automation.md` | GitHub Actions + Python + Jira API + Slack webhooks. Covers 14 repos + 1 monorepo (6–8 services). Replaced a dedicated release coordinator role. Solo implementation. | Roles emphasizing automation, cross-team impact, process ownership, or reducing operational burden |
| `~/Desktop/Work/SysAid/projects-context/developer-tooling.md` | Claude Code skills (Slack investigation, deployment diagnostics, E2E test triage). TypeScript report parser, Playwright HTML parsing. Parallel execution (40% wall-clock improvement). | DX, tooling, AI integration, or developer productivity roles |

---

## Jira Reports
*Noise level: High — raw ticket data. Filter aggressively. Only use when you need specific dates, ticket volumes, or epic-level scope evidence.*

| File | Contains | When to pull |
|---|---|---|
| `~/Desktop/Work/SysAid/jira-reports/summary.md` | Cross-quarter summary: 88/100 tickets done, 5 in progress, breakdowns by type and epic | When you need a single-line scope stat ("delivered 88 tickets across 4 initiatives") |
| `~/Desktop/Work/SysAid/jira-reports/Q3-2025.md` | 25–40 tickets from Q3 2025 with epic tags | When you need Q3 dates or greenfield project evidence |
| `~/Desktop/Work/SysAid/jira-reports/Q4-2025.md` | 25–40 tickets from Q4 2025; heavy Kargo + translation content | When you need Q4 scale evidence |
| `~/Desktop/Work/SysAid/jira-reports/Q1-2026.md` | 25–40 tickets from Q1 2026; Kargo completion, translation UX, AI tooling | When you need Q1 specific dates or Kargo completion evidence |
| `~/Desktop/Work/SysAid/jira-reports/Q2-2026.md` | 25–40 tickets from Q2 2026; architecture refactoring | When the role specifically values recent refactoring work |

**Noise filter rule:** From any Jira report, skip: routine CI fixes, documentation updates, minor bug fixes, test maintenance. Surface only: epics, architecture decisions, migrations, new system launches, and tickets with measurable scope (components, services, languages, time).
