---
name: memory-capture
description: Capture new personal memory into memory/00_Inbox. Use when user asks to record, save, jot, capture, add a memory note, or store a thought for later.
---

# Memory Capture

Use `memory/` as the memory root.

## Workflow

1. Normalize the user input into a short note title and body.
2. Write the note to `memory/00_Inbox/` first.
3. Add YAML frontmatter:
   - `title`
   - `type: inbox`
   - `tags`
   - `source`
   - `updated_at`
   - `confidence`
4. Confirm created file path and summarize what was saved in 1-2 lines.

## Rules

- Never write a new note directly into `10_Growth`, `20_Connections`, `30_Wealth`, or `40_ProductMind`.
- Keep raw user wording in the body whenever possible.
- If user gives no tags, use a minimal default tag list.
- **Before creating a new note, check if similar content already exists in memory/ (search by title/tags/keywords). If found, ask user whether to update existing note or create new one.**

