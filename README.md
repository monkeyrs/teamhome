<h1 align="center">TeamHome</h1>

<h3 align="center">Bring your team and home together.</h3>
<p align="center">Plan schedules, track income and expenses, and ask an assistant in natural language — all from a WeChat Mini Program.</p>

<p align="center">
  <a href="#features">Features</a> · <a href="#assistant"><b>Assistant</b></a> ·
  <a href="#install"><b>Install</b></a> · <a href="#docs">Docs</a> ·
  <a href="#support-teamhome">Support</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/monkeyrs/teamhome" alt="GPL-3.0 license"></a>
  <a href="https://github.com/monkeyrs/teamhome/commits/main"><img src="https://img.shields.io/github/commit-activity/m/monkeyrs/teamhome" alt="Commit activity"></a>
  <a href="https://github.com/monkeyrs/teamhome/stargazers"><img src="https://img.shields.io/github/stars/monkeyrs/teamhome" alt="Stars"></a>
  <a href="https://github.com/monkeyrs/teamhome/issues"><img src="https://img.shields.io/github/issues/monkeyrs/teamhome" alt="Issues"></a>
</p>

<div align="center" dir="auto">
<a href="https://ko-fi.com/monkeyrs" rel="nofollow"><img src="https://img.shields.io/badge/Support_me_on_Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Ko-fi" style="max-width: 100%;"></a>
</div>

<p align="center"><sub><b>English</b> · <a href="docs/lang/README.zh-CN.md">简体中文</a> · <a href="docs/lang/README.ja.md">日本語</a></sub></p>

**Free, open source, and yours to host.** TeamHome is a collaboration tool for teams and families: a shared timeline, an assistant that understands natural language, expense tracking and analysis, and Excel export. Run the FastAPI backend yourself and connect a WeChat Mini Program frontend — no vendor lock-in.

<a id="features"></a>

## Features

| What you get | What it does |
| --- | --- |
| **Assistant** | Create and query schedules and expenses in natural language. |
| **Timeline** | See schedules, income and expenses together in one unified view. |
| **Analysis** | Team activity, expense distribution and other statistics. |
| **Export** | Download team data as Excel workbooks. |
| **Teams** | Create and join teams, with team passwords and member limits. |
| **Languages** | Chinese, English and Japanese UI copy, routed through i18n. |

<a id="assistant"></a>

## Assistant

The assistant is the main line of development. It can run through the legacy engine or through **LangGraph**, and supports an **OpenAI-compatible** endpoint for natural-language parsing. Model selection, failover and LangSmith tracing are configured through environment variables.

Not sure where to start? The Docker setup runs the API, PostgreSQL and a LangGraph dev server together. See [assistant debugging](docs/langgraph-debug.md) for the tracing chain.

<a id="install"></a>

## Install

### Docker

From the repository root:

```bash
docker compose up -d --build
```

For production:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

<details open>
<summary><b>Run the backend locally</b></summary>

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Set `DATABASE_URL`, `JWT_SECRET` and the other values in `backend/.env` before using it. The example file documents every supported option.

</details>

<details>
<summary><b>Connect the WeChat Mini Program</b></summary>

1. Open `frontend/` with WeChat DevTools.
2. Override the API address in `frontend/config/local.js` for local development.
3. Disable domain-name checking in DevTools while debugging locally.

The repository uses placeholder values: the API address in [frontend/config/default.js](frontend/config/default.js) is `https://your-domain.example/xcx`, and the AppID in `project.config.json` / `frontend/project.config.json` is `touristappid`. Replace both with your own values before building or uploading.

</details>

On Windows, `scripts/start-backend.ps1` and `scripts/restart-backend.ps1` are the recommended local helpers.

<a id="docs"></a>

## Docs

- [Documentation index](docs/README.md)
- [Iteration history](docs/iteration-history.md)
- [Onboarding content](docs/onboarding-content.md)
- [Assistant design baseline](docs/assistant-ai-plan.md)
- [LangGraph debugging](docs/langgraph-debug.md)
- [Deployment guide](docs/deployment.md)

## Project layout

- `backend/` — FastAPI, SQLAlchemy, Alembic and PostgreSQL.
- `frontend/` — WeChat Mini Program.
- `docs/` — Planning, deployment, debugging and iteration notes.
- `scripts/` — Startup, restart, encoding checks and operations helpers.

## Development notes

- All UI copy goes through i18n.
- Backend architecture changes also require updating the startup and restart scripts under `scripts/`.
- Source files use UTF-8 without BOM; JSON responses and requests declare `charset=UTF-8`.
- Run the encoding check with `python scripts/ensure_utf8.py --check --root .`, and fix with `python scripts/ensure_utf8.py --root .`.
- For production, set `ASSISTANT_ENGINE=langgraph`, `ENABLE_DEBUG_ENDPOINTS=false`, `ALLOW_INSECURE_DEV_AUTH=false`, `ENVIRONMENT=production`, and a strong non-default `JWT_SECRET`.

<a id="support-teamhome"></a>

## Support TeamHome

If TeamHome is useful to you, you can support development with a coffee.

<a href="https://ko-fi.com/monkeyrs" rel="nofollow"><img src="https://img.shields.io/badge/Support_me_on_Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Support me on Ko-fi"></a>

[GPL-3.0 license](LICENSE) · [Report an issue](https://github.com/monkeyrs/teamhome/issues)
