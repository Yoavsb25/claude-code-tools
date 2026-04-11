# software-architect

A Claude Code skill that makes Claude act as a senior software architect.

## What it does

- **System design** — given a description of what you want to build, produces a structured architecture document with Mermaid/C4 diagrams, component breakdown, data flow, and a proactive bottleneck analysis
- **ADR writing** — guides writing Architecture Decision Records that capture not just what was decided, but why, what alternatives were considered, and what trade-offs were accepted

## When it triggers

- Designing a new system, service, or feature
- Asking "how should I build/structure X"
- Choosing between architectural approaches
- Documenting a significant technical decision

## Output format

- Mermaid diagrams (C4 context, container, sequence)
- Structured markdown architecture documents
- ADRs in standard format (context → options → decision → consequences)
