import datetime as dt
import unittest
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
        self.assertEqual(visual_state["highlighted_stages"], ["loop_queue", "schedule_subgraph"])

    def test_attach_langgraph_visual_state_falls_back_to_response_status(self):
        response = {
            "reply": "done",
            "status": assistant_orchestrator.STATUS_EXECUTED,
            "data": {"can_undo": True},
        }

        with patch("app.services.assistant_orchestrator._get_langgraph_visual_state", side_effect=RuntimeError("offline")):
            enriched = assistant_orchestrator._attach_langgraph_visual_state(response, thread_id="thread-2")

        self.assertFalse(enriched["data"]["graph_state"]["available"])
        self.assertEqual(enriched["data"]["graph_state"]["thread_id"], "thread-2")
        self.assertEqual(enriched["data"]["graph_state"]["highlighted_stages"], ["commit_batch"])


if __name__ == "__main__":
    unittest.main()
