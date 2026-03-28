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

脚本会把源码和项目文档统一为 UTF-8 无 BOM，并跳过 `.venv`、`node_modules`、`.git` 等目录。
