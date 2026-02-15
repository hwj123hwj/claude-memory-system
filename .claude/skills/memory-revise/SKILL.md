---
name: memory-revise
description: Revise or refine existing memory notes while preserving intent. Use when user asks to rewrite, edit, merge, split, update tags, or improve clarity of memory files.
---

# Memory Revise

Use `memory/` as the memory root.

## Workflow

1. Locate target memory files.
2. Show a concise change preview before applying edits.
3. Apply minimal edits that satisfy the request.
4. Update frontmatter `updated_at`.
5. Summarize what changed and why.

## Rules

- Keep original meaning unless user asks for semantic changes.
- Avoid large rewrites when small edits are enough.
- For destructive changes (merge/split/remove), ask explicit confirmation first.

