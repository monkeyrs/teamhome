# TeamHome

小团队 / 家庭日程与记账协作工具。

## 目录

- `backend/`：FastAPI + SQLAlchemy + PostgreSQL
- `frontend/`：微信小程序

## 本地运行

### Backend

1. 进入目录：`cd backend`
2. 安装依赖：`pip install -r requirements.txt`
3. 创建环境变量：复制 `.env.example` 为 `.env`
4. 启动服务：`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

### Backend One-Click (Windows + Docker PostgreSQL)

在项目根目录执行：

- 一键启动（自动拉起 `db` + 启动本地 `uvicorn`）  
  `powershell -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1`
- 一键重启  
  `powershell -ExecutionPolicy Bypass -File .\scripts\restart-backend.ps1`
- 跳过数据库，仅启动后端  
  `powershell -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1 -SkipDb`
- 查看状态  
  `powershell -ExecutionPolicy Bypass -File .\scripts\backend-dev.ps1 -Action status`
- 停止后端（不关闭 PostgreSQL 容器）  
  `powershell -ExecutionPolicy Bypass -File .\scripts\backend-dev.ps1 -Action stop`

日志与 PID 文件位于：`backend\.run\`

### Frontend (WeChat Mini Program)

1. 用微信开发者工具打开 `frontend/`
2. 在小程序开发设置中关闭域名校验（开发环境）
3. 确认后端地址为 `http://127.0.0.1:8000`（定义在 `frontend/app.js`）

## 已实现页面

- `pages/schedule`：日程列表 + 自然语言解析创建
- `pages/finance`：记账列表 + 分类统计 + 自然语言解析创建
- `pages/assistant`：财务问答助手
