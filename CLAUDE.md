# Project Claude Code Rules

This project uses project-level skills under `.claude/skills`.

## Memory Root

- The personal memory root is `memory/`.
- Standard folders:
  - `memory/00_Inbox`
  - `memory/10_Growth`
  - `memory/20_Connections`
  - `memory/30_Wealth`
  - `memory/40_ProductMind`

## Skill Routing Priority

When user intent matches, prioritize these skills:

1. `memory-capture`
2. `memory-summarize`
3. `memory-organize`
4. `memory-revise`

## Operational Rules

- New memory entries must be written to `memory/00_Inbox` first.
- Reorganization from inbox into category folders requires a clear move plan.
- Destructive changes require explicit confirmation.
- Use concise responses and include touched file paths when edits happen.

