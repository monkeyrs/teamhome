# Docs Index

`docs/` 目录用于存放 TeamHome 的规划、部署、调试和迭代资料。

## 推荐阅读顺序

1. [README.md](C:/Users/monke/Desktop/WeCount/teamhome/README.md)
2. [iteration-history.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/iteration-history.md)
3. [onboarding-content.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/onboarding-content.md)
4. [deploy-monkeyrs.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/deploy-monkeyrs.md)
5. [langgraph-debug.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/langgraph-debug.md)

## 文档索引

### 项目理解

- [iteration-history.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/iteration-history.md)
  用途：查看项目从 2026-03-19 到 2026-03-28 的主要演进脉络。
- [onboarding-content.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/onboarding-content.md)
  用途：为新手引导、示例团队、种子日历准备简版时间线和经验总结。

### 产品与架构

- [assistant-ai-plan.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/assistant-ai-plan.md)
  用途：查看助手从问答页演进为可执行编排层的早期设计思路。
  备注：这是规划基线，不完全等同于当前实现。

### 部署与运维

- [deploy-monkeyrs.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/deploy-monkeyrs.md)
  用途：正式部署 `your-domain.example`、配置 HTTPS、运行生产容器，并包含发版前配置检查与发版后验证清单。
- [nginx-monkeyrs.conf](C:/Users/monke/Desktop/WeCount/teamhome/docs/nginx-monkeyrs.conf)
  用途：Nginx 参考配置，配合部署文档一起使用。

### 调试与联调

- [langgraph-debug.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/langgraph-debug.md)
  用途：配置 LangGraph / LangSmith，检查 trace 和本地调试链路。

## 维护约定

- `docs/` 下的项目自有文档统一保存为 UTF-8 无 BOM。
- 文档要优先反映当前仓库现状，历史草案需明确标注“规划基线”。
- 如果新增后端架构、部署链路或调试方式，除了改代码，也要同步更新这里的索引和对应文档。

## 最新同步

- 2026-04-03 至 2026-04-04 的最新收口已同步到 [iteration-history.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/iteration-history.md)。
- 助手首页 LangGraph 示意图的当前验证入口与排障方式已同步到 [langgraph-debug.md](C:/Users/monke/Desktop/WeCount/teamhome/docs/langgraph-debug.md)。
- 小程序当前全局样式基座以 `frontend/app.wxss` 为准，README 已补充说明。
