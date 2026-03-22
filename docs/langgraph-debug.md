# LangGraph 官方调试链路（LangSmith）

## 1. 配置环境变量（backend/.env）

```env
ASSISTANT_ENGINE=langgraph
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=你的_langsmith_key
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=teamhome-assistant
# LANGSMITH_WORKSPACE_ID=可选，多 workspace key 时建议填写
```

## 2. 启动（Docker，含 Agent Server）

```bash
docker compose up -d --build
```

启动后会有两个服务端口：
- 业务 API: `8000`
- LangGraph Agent Server: `2024`

## 3. 验证

1. 打开助手页 -> `LangGraph UI`。
2. 确认：
   - `Engine = langgraph`
   - `LangSmith Tracing = On`
   - `LangSmith API Key = Configured`
3. 本地可先看 Agent Server 文档页：`http://127.0.0.1:2024/docs`
4. 发送一条助手消息后，在 LangSmith 项目中查看 trace。
