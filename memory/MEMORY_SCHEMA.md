# Memory Schema (Stage 1)

## Root

- `memory/` is the memory system root.

## Buckets

1. `memory/00_Inbox`
2. `memory/10_Growth`
3. `memory/20_Connections`
4. `memory/30_Wealth`
5. `memory/40_ProductMind`

## Rule

- New memory must be written to `memory/00_Inbox` first.
- Archive to `10/20/30/40` only after explicit review/confirmation.

## Frontmatter Standard

Each `.md` memory note should start with:

```yaml
---
title: <note_title>
type: inbox|growth|connections|wealth|product
tags: [tag1, tag2]
source: chat|manual|import
updated_at: 2026-02-14T23:30:00
confidence: low|medium|high
---
```

