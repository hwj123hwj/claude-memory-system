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
uv sync --dev
uv run uvicorn app:app --reload --port 8000
```

Open: `http://127.0.0.1:8000`

## Feishu (Local, No Public URL)

This project supports Feishu long-connection mode (websocket), which does not require exposing your local server to the public internet.

```bash
uv run python feishu_ws_bridge.py
```

Requirements:
- Configure `FEISHU_APP_ID` and `FEISHU_APP_SECRET` in `.env`
- Enable Feishu event delivery in long-connection mode for your app

Note:
- HTTP webhook mode has been removed from backend routes.
- Feishu messages are handled only by `feishu_ws_bridge.py`.

## Example Prompt

```text
看下当前文件夹的主要文件内容
```

## Test

```bash
uv run pytest
```
