# Claude Code Web Agent (Workspace Restricted)

This project provides a web chat UI that routes prompts to Claude Code SDK.

## Docs

- `docs/AGENT_IMPLEMENTATION_PROMPT.md`
- `docs/开发总结.md`
- `docs/开发问题与解决记录.md`
- `docs/claude agent sdk使用文档.md`

## Scope Restriction

- Workspace root is fixed to the current folder: `D:\develop\test`
- Tool inputs with paths outside workspace are denied
- `Bash` is restricted by a safe-command allowlist and workspace-path checks

## Quick Start

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Open: `http://127.0.0.1:8000`

## Example Prompt

```text
看下当前文件夹的主要文件内容
```

## Test

```bash
pytest -q tests
```
