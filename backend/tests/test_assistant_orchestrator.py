import datetime as dt
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.services import assistant_orchestrator


class _FakePlannerClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def chat_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


class AssistantOrchestratorTests(unittest.TestCase):
    def test_plan_intents_uses_single_fast_planner_call(self):
        client = _FakePlannerClient({"steps": [{"intent": assistant_orchestrator.INTENT_QUERY_FINANCE}], "need_split": False})

        with patch("app.services.assistant_orchestrator.get_llm_client", return_value=client):
            intents, need_split = assistant_orchestrator._plan_intents("本月花了多少钱")

        self.assertFalse(need_split)
        self.assertEqual(intents, [assistant_orchestrator.INTENT_QUERY_FINANCE])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["max_tokens"], 120)
        self.assertFalse(client.calls[0]["allow_auto_switch"])

    def test_extract_query_finance_slots_for_this_month(self):
        now = dt.datetime(2026, 3, 29, 10, 30, tzinfo=dt.timezone(dt.timedelta(hours=8)))
        with patch("app.services.assistant_orchestrator._local_now", return_value=now):
            slots = assistant_orchestrator._extract_slots_for_intent(
                assistant_orchestrator.INTENT_QUERY_FINANCE,
                "本月花了多少钱",
                "zh-CN",
            )

        self.assertEqual(slots["label"], "本月")
        self.assertEqual(slots["window_start"], dt.datetime(2026, 3, 1, 0, 0, tzinfo=now.tzinfo))
        self.assertEqual(slots["window_end"], dt.datetime(2026, 4, 1, 0, 0, tzinfo=now.tzinfo))

    def test_extract_query_finance_slots_for_last_month(self):
        now = dt.datetime(2026, 3, 29, 10, 30, tzinfo=dt.timezone(dt.timedelta(hours=8)))
        with patch("app.services.assistant_orchestrator._local_now", return_value=now):
            slots = assistant_orchestrator._extract_slots_for_intent(
                assistant_orchestrator.INTENT_QUERY_FINANCE,
                "上月花了多少钱",
                "zh-CN",
            )

        self.assertEqual(slots["label"], "上月")
        self.assertEqual(slots["window_start"], dt.datetime(2026, 2, 1, 0, 0, tzinfo=now.tzinfo))
        self.assertEqual(slots["window_end"], dt.datetime(2026, 3, 1, 0, 0, tzinfo=now.tzinfo))

    def test_execute_step_reuses_recent_duplicate_finance_record(self):
        occurred_at = dt.datetime(2026, 3, 31, 12, 0, tzinfo=dt.timezone.utc)
        duplicate = SimpleNamespace(
            id=uuid.uuid4(),
            amount=assistant_orchestrator.decimal.Decimal("5.40"),
            type="expense",
            category="餐费",
            occurred_at=occurred_at,
            location=None,
            note="昨天买菜，西红柿花了5块4",
        )
        step = {
            "intent": assistant_orchestrator.INTENT_CREATE_FINANCE,
            "slots": {
                "amount": 5.4,
                "type": "expense",
                "category": "餐费",
                "occurred_at": occurred_at.isoformat(),
                "note": "昨天买菜，西红柿花了5块4",
            },
            "source_text": "昨天买菜，西红柿花了5块4",
        }

        with (
            patch("app.services.assistant_orchestrator.find_recent_duplicate_finance_record", return_value=duplicate) as find_mock,
            patch("app.services.assistant_orchestrator.create_finance_record") as create_mock,
        ):
            result = assistant_orchestrator._execute_step(
                object(),
                step=step,
                team_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                locale="zh-CN",
            )

        self.assertEqual(result["status"], assistant_orchestrator.STATUS_EXECUTED)
        self.assertEqual(result["data"]["record_id"], str(duplicate.id))
        self.assertTrue(result["data"]["deduplicated"])
        find_mock.assert_called_once()
        create_mock.assert_not_called()


    def test_build_langgraph_visual_state_maps_writes_and_next_nodes(self):
        visual_state = assistant_orchestrator._build_langgraph_visual_state(
            thread_id="thread-1",
            thread={"status": "busy", "updated_at": "2026-03-29T12:00:00Z"},
            state={
                "next": ["schedule_subgraph"],
                "metadata": {"writes": {"route_subgraph": {"route": "schedule"}}},
                "tasks": [],
            },
        )

        self.assertEqual(visual_state["thread_id"], "thread-1")
        self.assertEqual(visual_state["thread_status"], "busy")
        self.assertEqual(visual_state["next_nodes"], ["schedule_subgraph"])
        self.assertEqual(visual_state["highlighted_stages"], ["prepare", "loop_guard", "schedule_subgraph"])

    def test_build_langgraph_visual_state_uses_history_nodes_for_completed_path(self):
        visual_state = assistant_orchestrator._build_langgraph_visual_state(
            thread_id="thread-1",
            thread={"status": "idle", "updated_at": "2026-03-29T12:00:00Z"},
            state={
                "next": [],
                "history": [
                    {"next": ["expense_subgraph"]},
                    {"next": ["collect_result"]},
                    {"next": ["commit_batch"]},
                ],
            },
        )

        self.assertEqual(
            visual_state["highlighted_stages"],
            ["prepare", "loop_guard", "expense_subgraph", "collect_result", "commit_batch"],
        )

    def test_attach_langgraph_visual_state_falls_back_to_response_status(self):
        response = {
            "reply": "done",
            "status": assistant_orchestrator.STATUS_EXECUTED,
            "intent": assistant_orchestrator.INTENT_CREATE_FINANCE,
            "data": {"can_undo": True},
        }

        with patch("app.services.assistant_orchestrator._get_langgraph_visual_state", side_effect=RuntimeError("offline")):
            enriched = assistant_orchestrator._attach_langgraph_visual_state(response, thread_id="thread-2")

        self.assertFalse(enriched["data"]["graph_state"]["available"])
        self.assertEqual(enriched["data"]["graph_state"]["thread_id"], "thread-2")
        self.assertEqual(
            enriched["data"]["graph_state"]["highlighted_stages"],
            ["prepare", "loop_guard", "expense_subgraph", "collect_result", "commit_batch"],
        )

    def test_graph_stage_fallback_from_query_response_keeps_query_path(self):
        stages = assistant_orchestrator._graph_stage_fallback_from_response(
            {
                "status": assistant_orchestrator.STATUS_EXECUTED,
                "intent": assistant_orchestrator.INTENT_QUERY_FINANCE,
                "data": {
                    "results": [
                        {
                            "intent": assistant_orchestrator.INTENT_QUERY_FINANCE,
                            "status": assistant_orchestrator.STATUS_EXECUTED,
                        }
                    ]
                },
            }
        )

        self.assertEqual(stages, ["prepare", "loop_guard", "expense_subgraph", "collect_result"])

    def test_graph_prepare_clears_stale_thread_response(self):
        session_state = assistant_orchestrator._new_graph_session_state(
            steps=[],
            mode=assistant_orchestrator.SESSION_MODE_CONVERSATION,
        )
        state = {
            "team_id": "00000000-0000-0000-0000-000000000001",
            "user_id": "00000000-0000-0000-0000-000000000002",
            "locale": "zh-CN",
            "message": "昨天去太平洋市场买菜花了6块，停车花了十块",
            "session_id": "session-1",
            "response": {"reply": "旧结果"},
            "step_result": {"status": "stale"},
            "route": "done",
            "incoming_message": "昨天花了多少钱",
        }

        with patch(
            "app.services.assistant_orchestrator._load_or_initialize_graph_session",
            return_value=("session-2", session_state, None),
        ):
            prepared = assistant_orchestrator._graph_prepare(state)

        self.assertIsNone(prepared["response"])
        self.assertEqual(prepared["session_id"], "session-2")
        self.assertEqual(prepared["incoming_message"], "昨天去太平洋市场买菜花了6块，停车花了十块")
        self.assertEqual(prepared["route"], "loop_guard")

    def test_get_assistant_graph_state_returns_empty_payload_without_session(self):
        payload = assistant_orchestrator.get_assistant_graph_state(session_id=None)

        self.assertFalse(payload["available"])
        self.assertEqual(payload["thread_id"], "")
        self.assertEqual(payload["highlighted_stages"], [])

    def test_split_message_fragments_keeps_multiple_actionable_items(self):
        with patch("app.services.assistant_orchestrator.get_llm_client", return_value=None):
            fragments = assistant_orchestrator._split_message_fragments("记账 餐费 30，记一笔交通费 20；创建日程 明天晚上八点排练")

        self.assertEqual(fragments, ["记账 餐费 30", "记一笔交通费 20", "创建日程 明天晚上八点排练"])

    def test_plan_graph_steps_builds_multiple_loop_tasks(self):
        client = _FakePlannerClient(
            {
                "steps": [
                    {"intent": assistant_orchestrator.INTENT_CREATE_FINANCE, "source_text": "记账 餐费 30"},
                    {"intent": assistant_orchestrator.INTENT_CREATE_FINANCE, "source_text": "记一笔交通费 20"},
                    {"intent": assistant_orchestrator.INTENT_CREATE_SCHEDULE, "source_text": "创建日程 明天晚上八点排练"},
                ],
                "need_split": False,
            }
        )
        with patch("app.services.assistant_orchestrator.get_llm_client", return_value=client):
            steps, response = assistant_orchestrator._plan_graph_steps("记账餐费30再记一笔交通费20然后创建日程明天晚上八点排练", locale="zh-CN")

        self.assertIsNone(response)
        self.assertEqual([step["intent"] for step in steps], [
            assistant_orchestrator.INTENT_CREATE_FINANCE,
            assistant_orchestrator.INTENT_CREATE_FINANCE,
            assistant_orchestrator.INTENT_CREATE_SCHEDULE,
        ])
        self.assertEqual(steps[0]["source_text"], "记账 餐费 30")
        self.assertEqual(steps[1]["source_text"], "记一笔交通费 20")
        self.assertEqual(steps[2]["source_text"], "创建日程 明天晚上八点排练")

    def test_plan_graph_steps_uses_llm_structured_slots_with_temporal_inheritance(self):
        client = _FakePlannerClient(
            {
                "steps": [
                    {
                        "intent": assistant_orchestrator.INTENT_CREATE_FINANCE,
                        "source_text": "昨天去太平洋市场买菜花了6块",
                        "amount": 6,
                        "type": "expense",
                        "category": "餐费",
                        "occurred_at": "2026-03-28T12:00:00+08:00",
                        "note": "昨天去太平洋市场买菜花了6块",
                    },
                    {
                        "intent": assistant_orchestrator.INTENT_CREATE_FINANCE,
                        "source_text": "停车花了十块",
                        "amount": 10,
                        "type": "expense",
                        "category": "交通",
                        "occurred_at": "2026-03-28T12:00:00+08:00",
                        "note": "停车花了十块",
                    },
                ],
                "need_split": False,
            }
        )

        with patch("app.services.assistant_orchestrator.get_llm_client", return_value=client):
            steps, response = assistant_orchestrator._plan_steps_from_text("昨天去太平洋市场买菜花了6块停车花了十块", locale="zh-CN")

        self.assertIsNone(response)
        self.assertEqual(len(steps), 2)
        first_slots = steps[0]["slots"]
        second_slots = steps[1]["slots"]
        self.assertEqual(first_slots["amount"], 6)
        self.assertEqual(second_slots["amount"], 10)
        self.assertEqual(first_slots["category"], "餐费")
        self.assertEqual(second_slots["category"], "交通")
        self.assertEqual(first_slots["occurred_at"].isoformat(), "2026-03-28T12:00:00+08:00")
        self.assertEqual(second_slots["occurred_at"].isoformat(), "2026-03-28T12:00:00+08:00")
        self.assertEqual(second_slots["note"], "停车花了十块")

    def test_plan_steps_from_text_propagates_adjacent_finance_time_context(self):
        client = _FakePlannerClient(
            {
                "steps": [
                    {
                        "intent": assistant_orchestrator.INTENT_CREATE_FINANCE,
                        "source_text": "昨天去太平洋市场买菜花了6块",
                        "amount": 6,
                        "type": "expense",
                        "category": "餐费",
                        "occurred_at": "2026-03-28T12:00:00+08:00",
                        "note": "昨天去太平洋市场买菜花了6块",
                    },
                    {
                        "intent": assistant_orchestrator.INTENT_CREATE_FINANCE,
                        "source_text": "停车花了十块",
                        "amount": 10,
                        "type": "expense",
                        "category": "交通",
                        "note": "停车花了十块",
                    },
                ],
                "need_split": False,
            }
        )

        with patch("app.services.assistant_orchestrator.get_llm_client", return_value=client):
            steps, response = assistant_orchestrator._plan_steps_from_text("昨天去太平洋市场买菜花了6块，停车花了十块", locale="zh-CN")

        self.assertIsNone(response)
        self.assertEqual(steps[1]["slots"]["occurred_at"].isoformat(), "2026-03-28T12:00:00+08:00")

    def test_plan_graph_steps_propagates_time_context_across_fragments(self):
        first_step = {
            "intent": assistant_orchestrator.INTENT_CREATE_FINANCE,
            "slots": {
                "amount": 6,
                "type": "expense",
                "category": "餐费",
                "occurred_at": dt.datetime.fromisoformat("2026-03-28T12:00:00+08:00"),
                "note": "昨天去太平洋市场买菜花了6块",
            },
            "source_text": "昨天去太平洋市场买菜花了6块",
        }
        second_step = {
            "intent": assistant_orchestrator.INTENT_CREATE_FINANCE,
            "slots": {
                "amount": 10,
                "type": "expense",
                "category": "交通",
                "occurred_at": dt.datetime.fromisoformat("2026-03-29T15:45:00+08:00"),
                "note": "停车花了十块",
            },
            "source_text": "停车花了十块",
        }

        with patch(
            "app.services.assistant_orchestrator._plan_steps_from_text",
            side_effect=[([first_step], None), ([second_step], None)],
        ):
            steps, response = assistant_orchestrator._plan_graph_steps("昨天去太平洋市场买菜花了6块，停车花了十块", locale="zh-CN")

        self.assertIsNone(response)
        self.assertEqual(steps[1]["slots"]["occurred_at"].isoformat(), "2026-03-28T12:00:00+08:00")


if __name__ == "__main__":
    unittest.main()
