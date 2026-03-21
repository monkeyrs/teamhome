# 助手页 AI 能力规划

## 1. 当前现状

当前项目已经具备以下基础能力：

- 助手页前端已存在，但目前只支持文本/语音提问和财务问答。
- 后端已有日程 CRUD：
  - `POST /schedules`
  - `PUT /schedules/{schedule_id}`
  - `DELETE /schedules/{schedule_id}`
  - `GET /schedules?team_id=...`
- 后端已有费用 CRUD：
  - `POST /finance`
  - `PUT /finance/{record_id}`
  - `DELETE /finance/{record_id}`
  - `GET /finance?team_id=...`
- 后端已有两个解析入口：
  - `POST /schedules/parse`
  - `POST /finance/parse`

当前缺口不在 CRUD，而在“助手如何理解用户意图并安全调用这些能力”。

## 2. 助手页目标

助手页不应只是问答页，而应是一个“可执行助手”。

建议第一阶段支持 6 类核心意图：

1. 创建日程
2. 修改日程
3. 删除日程
4. 查询费用
5. 创建费用
6. 修改费用

其中创建日程需要额外支持：

- 检查时间冲突
- 冲突时引导用户确认处理方案
- 必要时先修改已有日程，再创建新日程

所有创建/修改动作都要支持：

- 参数缺失时多轮补参
- 执行前确认
- 执行后返回结果摘要

## 3. 建议的整体架构

建议把助手页拆成两层：

### 3.1 Prompt 层

作用：只负责把用户输入识别成结构化意图，不直接落库。

输出统一结构：

```json
{
  "intent": "create_schedule",
  "confidence": 0.96,
  "slots": {
    "title": "明天下午和产品评审",
    "start_time": "2026-03-22T15:00:00+08:00",
    "end_time": "2026-03-22T16:00:00+08:00",
    "location": null
  },
  "missing_slots": ["location"],
  "requires_confirmation": true
}
```

### 3.2 Tool 层

作用：把结构化意图映射到后端业务能力。

建议不要让大模型自由拼接 API，而是由后端提供有限工具：

- `list_schedules`
- `create_schedule`
- `update_schedule`
- `delete_schedule`
- `find_schedule_conflicts`
- `list_finance_records`
- `create_finance_record`
- `update_finance_record`
- `delete_finance_record`
- `summarize_finance`

这样模型负责“理解”，业务代码负责“执行”。

## 4. 意图设计

建议定义如下 intent 枚举：

### 4.1 日程相关

- `create_schedule`
- `update_schedule`
- `delete_schedule`
- `query_schedule`
- `resolve_schedule_conflict`

### 4.2 费用相关

- `create_finance`
- `update_finance`
- `delete_finance`
- `query_finance`

### 4.3 通用控制

- `collect_missing_info`
- `confirm_action`
- `cancel_action`
- `fallback_answer`

其中 `collect_missing_info` 不是单独业务，而是助手在参数不完整时进入的状态。

## 5. 槽位设计

## 5.1 创建日程需要的槽位

必填：

- `title`
- `start_time`

建议必填：

- `end_time`

可选：

- `description`
- `location`
- `location_latitude`
- `location_longitude`
- `is_all_day`

补充规则：

- 若用户只给了开始时间，没有结束时间，助手应主动追问：
  - “这个日程预计几点结束？”
- 若用户说“全天”，则自动设置 `is_all_day=true`
- 若用户说“明天下午开会”，解析出开始时间后仍不够精确，应继续追问具体时间

## 5.2 修改日程需要的槽位

必填：

- `target_schedule_id` 或可唯一定位该日程的查询条件

修改内容至少一项：

- `title`
- `start_time`
- `end_time`
- `location`
- `description`
- `status`

若无法唯一定位目标日程，助手必须先澄清，例如：

- “你是指明天 3 点那场产品评审，还是周三 10 点那场站会？”

## 5.3 创建费用需要的槽位

必填：

- `amount`
- `type`
- `category`

可选：

- `location`
- `note`
- `created_at`

补充规则：

- 未明确 `type` 时，可根据语义猜测，但执行前仍建议向用户确认
- 未明确 `category` 且无法可靠推断时，要追问
- 若金额缺失，不能创建，必须追问

示例追问：

- “这笔费用金额是多少？”
- “这是支出还是收入？”
- “这笔钱记到什么分类里？”

## 5.4 修改费用需要的槽位

必填：

- `target_record_id` 或可唯一定位该记录的查询条件

至少一项更新字段：

- `amount`
- `type`
- `category`
- `location`
- `note`

## 6. 多轮补参流程

建议助手页维护一个临时会话状态 `pending_action`，直到完成或取消。

结构建议：

```json
{
  "intent": "create_finance",
  "team_id": "xxx",
  "slots": {
    "amount": 32,
    "type": "expense",
    "category": null,
    "location": "公司楼下"
  },
  "missing_slots": ["category"],
  "candidate_records": [],
  "status": "collecting"
}
```

流程如下：

1. 用户输入自然语言
2. LLM 识别 intent 和已知 slots
3. 后端校验必填项
4. 如有缺失，返回 `missing_slots`
5. 前端助手页用追问文案继续向用户收集
6. 用户补充后，与 `pending_action` 合并
7. 所有必填满足后，再进入确认或执行

建议后端返回统一状态：

- `status = collecting`
- `status = awaiting_confirmation`
- `status = executed`
- `status = blocked`

## 7. 日程冲突处理

这是你这个助手页里最关键的差异化能力，建议单独设计。

### 7.1 冲突检测规则

创建或修改日程前，调用 `find_schedule_conflicts(team_id, start_time, end_time, exclude_schedule_id)`。

冲突判断：

- 新日程开始时间落在已有日程区间内
- 新日程结束时间落在已有日程区间内
- 新日程完整覆盖已有日程
- 全天日程与当天已有日程冲突

### 7.2 冲突后的系统行为

若发现冲突，不要直接失败，返回：

```json
{
  "status": "blocked",
  "reason": "schedule_conflict",
  "conflicts": [
    {
      "id": "schedule_1",
      "title": "产品评审",
      "start_time": "2026-03-22T15:00:00+08:00",
      "end_time": "2026-03-22T16:00:00+08:00"
    }
  ],
  "options": [
    "update_existing",
    "create_anyway",
    "cancel"
  ]
}
```

### 7.3 推荐交互文案

例如用户说：

- “明天下午 3 点加一个客户会”

系统发现冲突后应回复：

- “明天 15:00-16:00 已有 ‘产品评审’。你要我怎么处理？”
- “我可以帮你：修改原日程时间、直接创建新日程、或者取消这次操作。”

### 7.4 支持“先改旧日程，再建新日程”

这是你明确提出的需求，建议做成串联事务：

1. 找到冲突日程
2. 询问用户如何调整旧日程
3. 用户给出新时间后，先更新旧日程
4. 再次检查冲突
5. 若无冲突，再创建新日程

建议后端支持一个组合动作：

- `resolve_conflict_and_create_schedule`

输入：

```json
{
  "conflict_schedule_id": "xxx",
  "conflict_schedule_updates": {
    "start_time": "2026-03-22T16:00:00+08:00",
    "end_time": "2026-03-22T17:00:00+08:00"
  },
  "new_schedule": {
    "title": "客户会",
    "start_time": "2026-03-22T15:00:00+08:00",
    "end_time": "2026-03-22T16:00:00+08:00"
  }
}
```

这样能避免前端拼两次接口导致状态不一致。

## 8. 建议新增的后端能力

基于现有代码，建议新增一个统一助手编排接口，而不是继续把能力挂在 `finance/assistant` 下。

建议新增：

- `POST /assistant/execute`

请求：

```json
{
  "team_id": "xxx",
  "message": "把明天下午三点的客户会加上，如果冲突就把原来的评审挪到四点",
  "session_id": "optional"
}
```

响应建议：

```json
{
  "reply": "明天 15:00-16:00 与“产品评审”冲突。我可以把产品评审改到 16:00-17:00，并创建客户会。是否确认？",
  "status": "awaiting_confirmation",
  "intent": "resolve_schedule_conflict",
  "pending_action": {
    "type": "resolve_conflict_and_create_schedule",
    "payload": {}
  },
  "cards": [
    {
      "type": "schedule_conflict",
      "title": "发现时间冲突"
    }
  ]
}
```

后端内部建议拆成：

- `assistant_orchestrator.py`
- `assistant_tools.py`
- `assistant_session_service.py`

职责：

- `orchestrator`: 意图识别、追问、确认、执行编排
- `tools`: 对现有 schedule/finance CRUD 的受控封装
- `session_service`: 管理 pending_action

## 9. 建议新增的工具函数

### 9.1 日程工具

- `find_schedule_candidates(team_id, query_text)`
- `find_schedule_conflicts(team_id, start_time, end_time, exclude_schedule_id=None)`
- `create_schedule_with_validation(payload)`
- `update_schedule_with_validation(schedule_id, payload)`

### 9.2 费用工具

- `find_finance_candidates(team_id, query_text)`
- `create_finance_with_validation(payload)`
- `update_finance_with_validation(record_id, payload)`
- `query_finance_summary(team_id, filters)`

### 9.3 通用工具

- `collect_missing_slots(intent, slots)`
- `build_confirmation_message(action)`
- `execute_pending_action(session_id, confirmed)`

## 10. 前端助手页建议

助手页建议从“一个输入框 + 一段答案”升级成“对话流 + 状态卡片”。

至少应有以下展示层：

- 用户消息
- 助手消息
- 待补参提示
- 冲突卡片
- 确认卡片
- 执行结果卡片

建议前端状态增加：

- `messages`
- `pendingAction`
- `assistantStatus`
- `quickReplies`

### 10.1 对话中的快速操作

例如冲突时直接展示按钮：

- “改原日程”
- “直接创建”
- “取消”

参数缺失时展示快捷项：

- “支出”
- “收入”
- “餐饮”
- “交通”

这样可以减少纯文本输入。

## 11. 执行安全规则

为避免误操作，建议定以下规则：

- 删除类操作默认二次确认
- 修改类操作在目标不唯一时必须先澄清
- 自动推断出的关键字段在置信度低时必须确认
- 查询操作可直接执行
- 创建操作在缺少必要参数时绝不落库

## 12. 第一阶段实施顺序

建议按下面顺序开发：

### Phase 1

- 把 `finance/assistant` 升级为统一 `assistant/execute`
- 接入意图识别
- 接入 `pending_action`
- 跑通创建费用、查询费用

### Phase 2

- 跑通创建日程
- 增加缺参追问
- 增加日程冲突检测

### Phase 3

- 跑通修改日程、删除日程、修改费用
- 增加候选记录澄清
- 增加确认卡片

### Phase 4

- 支持“先改旧日程，再建新日程”
- 优化语音输入后的多轮会话
- 增加更多统计类财务问答

## 13. 与现有代码的直接映射

基于当前仓库，建议这样落地：

- 保留现有 `schedule` 和 `finance` CRUD，不重写。
- 新增统一助手编排层，不把 LLM 逻辑散落在各业务接口里。
- 现有 `parse_schedule_text` 和 `parse_finance_text` 可以作为第一层轻量解析器。
- 现有 `answer_finance_question` 可下沉为 `query_finance` 的一个子工具，而不是独立助手入口。

## 14. 最终建议

这页的核心不是“聊天”，而是“把用户的话安全地变成结构化操作”。

所以设计重点应当放在：

1. 明确意图分类
2. 封装受控工具
3. 维护多轮补参状态
4. 做好日程冲突处理
5. 所有写操作都经过确认和校验

如果后续继续开发，我建议下一步直接做两件事：

1. 先新增 `POST /assistant/execute` 的统一编排接口
2. 先打通“创建费用 + 缺参追问”这条最短链路，再复制到日程场景
