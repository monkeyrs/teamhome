# TeamHome

团队 / 家庭协作工具，当前主线能力是“时间线 + 助手 + 分析”。

## 当前能力

- 助手页：自然语言创建 / 查询日程与费用
- 时间线页：统一查看日程、收入、支出
- 分析页：展示团队活跃度、费用分布等统计信息
- 数据导出：下载团队相关 Excel 数据
- 团队能力：创建团队、加入团队、团队密码、成员上限控制
- 多语言：中文、English、日本語

## 目录

- `backend/`: FastAPI + SQLAlchemy + Alembic + PostgreSQL
- `frontend/`: 微信小程序
- `docs/`: 规划、部署、调试、迭代文档
- `scripts/`: 启动、重启、编码巡检与运维辅助脚本

## 本地开发

### Backend

1. 进入后端目录：`cd backend`
2. 安装依赖：`pip install -r requirements.txt`
3. 复制配置：把 `.env.example` 复制为 `.env`
4. 执行迁移：`alembic upgrade head`
5. 启动 API：`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

### Docker

在项目根目录运行：

```bash
docker compose up -d --build
```

生产部署使用：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Frontend

1. 用微信开发者工具打开 `frontend/`
2. 本地联调时可用 `frontend/config/local.js` 覆盖 API 地址
3. 若本地调试，开发者工具里关闭域名校验

默认正式配置见 [frontend/config/default.js](C:/Users/monke/Desktop/WeCount/teamhome/frontend/config/default.js)。

## 文档入口

- [docs/README.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/README.md)：统一文档索引
- [docs/iteration-history.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/iteration-history.md)：迭代历史
- [docs/onboarding-content.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/onboarding-content.md)：新手引导内容草案

## 开发约定

- 页面文案统一走 i18n。
- 后端架构变更时，同步更新根目录 `scripts/` 下的启动和重启脚本。
- 前后端源文件统一使用 UTF-8 无 BOM。
- JSON 请求 / 响应显式使用 `charset=UTF-8`。
- 数据库使用 UTF-8 / utf8mb4，不依赖 BOM。
- 正式环境遵循安全预检，按现有脚本先校验再启动。

## 编码巡检

项目内置脚本：

- 检查：`python scripts/ensure_utf8.py --check --root .`
- 修复：`python scripts/ensure_utf8.py --root .`

## 2026-04-04 更新

- 小程序工程根目录继续以 `frontend/` 为准，全局样式入口为 `frontend/app.wxss`。
- 时间线页继续使用统一读模型；删除、批量删除、复制新增后，列表会按最新数据重新吸附并刷新锚点。
- 助手首页底部的 LangGraph 示意图继续作为主展示入口，调试与验证请优先参考 [docs/langgraph-debug.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/langgraph-debug.md)。
- 演示团队 `teamhome开发` 已补充 2026-04-03 与 2026-04-04 的迭代事项，重启后端会自动同步 demo seed。
- Windows 本地启动推荐使用 `scripts/start-backend.ps1`，重启推荐使用 `scripts/restart-backend.ps1`。

## 发版前确认

- `backend/.env` 或服务器上的生产环境变量里，确认 `ASSISTANT_ENGINE=langgraph`。
- 正式环境确认 `ENABLE_DEBUG_ENDPOINTS=false`，不要带这轮临时调试日志和调试入口上线。
- 正式环境确认 `ALLOW_INSECURE_DEV_AUTH=false`、`ENVIRONMENT=production`、`JWT_SECRET` 为非默认强密钥。
- 服务器部署步骤与检查项请直接参考 [docs/deploy-monkeyrs.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/deploy-monkeyrs.md)。

脚本会把源码和项目文档统一为 UTF-8 无 BOM，并跳过 `.venv`、`node_modules`、`.git` 等目录。
