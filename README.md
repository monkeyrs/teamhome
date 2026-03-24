# TeamHome

团队/家庭日程与记账协作工具。

## 目录

- `backend/`: FastAPI + SQLAlchemy + PostgreSQL
- `frontend/`: 微信小程序
- `scripts/`: 启停脚本与工程辅助脚本

## 本地运行

### Backend

1. `cd backend`
2. `pip install -r requirements.txt`
3. 复制 `.env.example` 为 `.env` 并填写配置
4. `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

### Frontend（微信小程序）

1. 用微信开发者工具打开 `frontend/`
2. 开发环境关闭域名校验
3. 确认后端地址为 `http://127.0.0.1:8000`（见 `frontend/app.js`）

## 开发约定（必须遵守）

- 用 i18n 解决页面上的任何文案。
- 每次做后端架构修改，都更新根目录 `scripts/` 下的启动脚本、重启脚本。
- 前后端通信的中文乱码问题：由编码不一致链条导致，解决办法是：
  - 前端文件：JavaScript、JSON、Vue/WeChat 小程序 JS/JSON 文件，保存为 UTF-8 无 BOM。
  - 后端源代码：Python、Java、Node.js 也使用 UTF-8 无 BOM，保证请求/响应一致。
  - JSON 传输：`JSON.stringify` + `Content-Type: application/json; charset=UTF-8`，不会引入 BOM。
  - 数据库：UTF-8/utf8mb4，不要依赖 BOM。

## 编码巡检脚本

项目内置脚本：`scripts/ensure_utf8.py`

- 检查模式：`python scripts/ensure_utf8.py --check --root .`
- 修复模式：`python scripts/ensure_utf8.py --root .`

脚本会把源码文件统一为 UTF-8 无 BOM，并跳过 `.venv/node_modules/.git` 等目录。
