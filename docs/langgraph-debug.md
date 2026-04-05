# LangGraph 官方调试链路（LangSmith）

> 状态说明：当前项目已经保留 LangGraph / LangSmith 调试能力，但前端不再依赖早期的 `assistant-graph` 演示页作为主要入口。应优先按本文档中的环境变量、服务端口和 LangSmith trace 来排查。

## 1. 配置环境变量（backend/.env）

```env
ASSISTANT_ENGINE=langgraph
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=你的_langsmith_key
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=teamhome-assistant
# LANGSMITH_WORKSPACE_ID=可选，多 workspace key 时建议填写
```

## 2. 启动（Docker，含 LangGraph 服务）

```bash
docker compose up -d --build
```

启动后会有两个服务端口：
- 业务 API: `8000`
- LangGraph 服务: `22024`

## 3. 验证

1. 确认 `backend/.env` 已启用 `ASSISTANT_ENGINE=langgraph`
2. 访问业务 API：`http://127.0.0.1:8000/openapi.json`
3. 检查 LangGraph 服务：`http://127.0.0.1:22024/docs`
4. 发送一条助手消息后，在 LangSmith 项目中查看 trace

## 4. 排障要点

- 如果 API 正常但没有 trace，优先检查 `LANGSMITH_TRACING`、`LANGSMITH_API_KEY` 和项目名。
- 如果 API 起不来，先看 `docker compose logs api` 和 Alembic 迁移状态。
- 如果 LangGraph 服务起不来，检查 `backend/langgraph.json`、依赖安装和 `langgraph` 容器日志。
- 正式环境若关闭调试端点，前端不应再依赖旧的调试 UI 路径。

## 5. 2026-04-04 UI 自测关注点

1. 进入助手首页，观察底部 LangGraph 示意图是否按“光点先到位，再亮灯，再移动到下一节点”的节奏循环。
2. 六个节点的高亮应与光点驻留窗口同步，第二行说明文字在亮灯时应切到白色。
3. 若要验证最新 demo 数据，先运行 `scripts/restart-backend.ps1`，确认 demo seed 已同步，再查看 `teamhome开发` 团队。
