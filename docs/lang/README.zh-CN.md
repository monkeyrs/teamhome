<h1 align="center">TeamHome</h1>

<h3 align="center">让团队与家庭，在一处协作。</h3>
<p align="center">用自然语言创建与查询日程、记录收支，并在微信小程序里查看统一时间线。</p>

<p align="center">
  <a href="#features">功能</a> · <a href="#assistant"><b>助手</b></a> ·
  <a href="#install"><b>安装</b></a> · <a href="#docs">文档</a> ·
  <a href="#support-teamhome">支持</a>
</p>

<p align="center">
  <a href="../../LICENSE"><img src="https://img.shields.io/github/license/monkeyrs/teamhome" alt="GPL-3.0 license"></a>
  <a href="https://github.com/monkeyrs/teamhome/commits/main"><img src="https://img.shields.io/github/commit-activity/m/monkeyrs/teamhome" alt="Commit activity"></a>
  <a href="https://github.com/monkeyrs/teamhome/stargazers"><img src="https://img.shields.io/github/stars/monkeyrs/teamhome" alt="Stars"></a>
  <a href="https://github.com/monkeyrs/teamhome/issues"><img src="https://img.shields.io/github/issues/monkeyrs/teamhome" alt="Issues"></a>
</p>

<div align="center" dir="auto">
<a href="https://ko-fi.com/monkeyrs" rel="nofollow"><img src="https://img.shields.io/badge/Support_me_on_Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Ko-fi" style="max-width: 100%;"></a>
</div>

<p align="center"><sub><a href="../../README.md">English</a> · <b>简体中文</b> · <a href="README.ja.md">日本語</a></sub></p>

**免费、开源，并且由你自己掌控。** TeamHome 是面向团队与家庭的协作工具：共享时间线、自然语言助手、收支记录与分析、Excel 导出。后端基于 FastAPI，可自行部署；前端是微信小程序，没有厂商锁定。

<a id="features"></a>

## 功能

| 能力 | 说明 |
| --- | --- |
| **助手** | 用自然语言创建、查询日程与费用。 |
| **时间线** | 在一个视图里统一查看日程、收入与支出。 |
| **分析** | 团队活跃度、费用分布等统计信息。 |
| **导出** | 下载团队相关的 Excel 数据。 |
| **团队** | 创建与加入团队，支持团队密码和成员上限。 |
| **多语言** | 中文、English、日本語，文案统一走 i18n。 |

<a id="assistant"></a>

## 助手

助手是当前主线能力。它可以选择 legacy 引擎或 **LangGraph**，并支持接入 **OpenAI 兼容**的模型端点做自然语言解析。模型选择、故障切换与 LangSmith 链路追踪都通过环境变量配置。

不确定从哪里开始？Docker 配置会同时拉起 API、PostgreSQL 和 LangGraph 开发服务。链路调试见 [LangGraph 调试文档](../langgraph-debug.md)。

<a id="install"></a>

## 安装

### Docker

在项目根目录运行：

```bash
docker compose up -d --build
```

生产环境使用：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

<details open>
<summary><b>本地运行后端</b></summary>

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

使用前请在 `backend/.env` 中设置 `DATABASE_URL`、`JWT_SECRET` 等配置。示例文件列出了所有支持的选项。

</details>

<details>
<summary><b>连接微信小程序</b></summary>

1. 用微信开发者工具打开 `frontend/`。
2. 本地联调时在 `frontend/config/local.js` 覆盖 API 地址。
3. 本地调试时在开发者工具里关闭域名校验。

仓库里是占位配置：[frontend/config/default.js](../../frontend/config/default.js) 的 API 地址是 `https://your-domain.example/xcx`，`project.config.json` / `frontend/project.config.json` 的 AppID 是 `touristappid`。构建或上传前请替换成你自己的值。

</details>

Windows 本地启动推荐使用 `scripts/start-backend.ps1`，重启推荐使用 `scripts/restart-backend.ps1`。

<a id="docs"></a>

## 文档

- [文档索引](../README.md)
- [迭代历史](../iteration-history.md)
- [新手引导内容](../onboarding-content.md)
- [助手设计基线](../assistant-ai-plan.md)
- [LangGraph 调试](../langgraph-debug.md)
- [部署指南](../deployment.md)

## 项目结构

- `backend/` — FastAPI、SQLAlchemy、Alembic 与 PostgreSQL。
- `frontend/` — 微信小程序。
- `docs/` — 规划、部署、调试与迭代文档。
- `scripts/` — 启动、重启、编码巡检与运维辅助脚本。

## 开发约定

- 页面文案统一走 i18n。
- 后端架构变更时，同步更新 `scripts/` 下的启动和重启脚本。
- 源文件统一使用 UTF-8 无 BOM；JSON 请求 / 响应显式声明 `charset=UTF-8`。
- 用 `python scripts/ensure_utf8.py --check --root .` 做编码巡检，用 `python scripts/ensure_utf8.py --root .` 修复。
- 生产环境请确认 `ASSISTANT_ENGINE=langgraph`、`ENABLE_DEBUG_ENDPOINTS=false`、`ALLOW_INSECURE_DEV_AUTH=false`、`ENVIRONMENT=production`，并使用非默认的强 `JWT_SECRET`。

<a id="support-teamhome"></a>

## 支持 TeamHome

如果 TeamHome 对你有帮助，可以用一杯咖啡支持开发。

<a href="https://ko-fi.com/monkeyrs" rel="nofollow"><img src="https://img.shields.io/badge/Support_me_on_Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Support me on Ko-fi"></a>

[GPL-3.0 许可证](../../LICENSE) · [反馈问题](https://github.com/monkeyrs/teamhome/issues)
