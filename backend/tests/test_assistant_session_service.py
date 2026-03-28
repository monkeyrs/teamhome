import datetime as dt
import unittest
from unittest.mock import patch

from app.services import assistant_session_service


class _SessionContext:
    def __init__(self, db):
        self._db = db

    def __enter__(self):
        return self._db

    def __exit__(self, exc_type, exc, tb):
        return False


class _AssistantSessionRow:
    def __init__(self, state):
        self.state = state


class AssistantSessionServiceTests(unittest.TestCase):
    def test_get_session_returns_deep_copy(self):
        db = object()
        stored_state = {"nested": {"count": 1}}

        with (
            patch.object(assistant_session_service, "SessionLocal", return_value=_SessionContext(db)),
            patch.object(
                assistant_session_service,
                "get_assistant_session",
                return_value=_AssistantSessionRow(stored_state),
            ) as get_mock,
        ):
            result = assistant_session_service.get_session("session-1")

        self.assertEqual(result, stored_state)
        result["nested"]["count"] = 9
        self.assertEqual(stored_state["nested"]["count"], 1)
        get_mock.assert_called_once_with(db, session_id="session-1")

    def test_save_session_passes_deep_copy_to_crud(self):
        db = object()
        state = {"items": [{"value": 1}]}

        with (
            patch.object(assistant_session_service, "SessionLocal", return_value=_SessionContext(db)),
            patch.object(assistant_session_service, "create_or_replace_assistant_session") as create_mock,
        ):
            assistant_session_service.save_session("session-2", state)
            captured_state = create_mock.call_args.kwargs["state"]

        state["items"][0]["value"] = 7
        self.assertEqual(captured_state["items"][0]["value"], 1)
        create_mock.assert_called_once_with(
            db,
            session_id="session-2",
            state=captured_state,
        )

    def test_save_session_serializes_datetime_and_get_restores_it(self):
        db = object()
        timestamp = dt.datetime(2026, 3, 29, 12, 34, 56, tzinfo=dt.timezone.utc)
        state = {"slots": {"start_time": timestamp}}

        with (
            patch.object(assistant_session_service, "SessionLocal", return_value=_SessionContext(db)),
            patch.object(assistant_session_service, "create_or_replace_assistant_session") as create_mock,
        ):
            assistant_session_service.save_session("session-3", state)
            captured_state = create_mock.call_args.kwargs["state"]

        self.assertEqual(
            captured_state["slots"]["start_time"],
            {
                "__teamhome_type__": "datetime",
                "value": timestamp.isoformat(),
            },
        )

        with (
            patch.object(assistant_session_service, "SessionLocal", return_value=_SessionContext(db)),
            patch.object(
                assistant_session_service,
                "get_assistant_session",
                return_value=_AssistantSessionRow(captured_state),
            ),
        ):
            restored = assistant_session_service.get_session("session-3")

        self.assertEqual(restored["slots"]["start_time"], timestamp)

    def test_pop_undo_batch_returns_deep_copy(self):
        db = object()
        stored_actions = [{"intent": "create_schedule", "record_id": "abc"}]

        with (
            patch.object(assistant_session_service, "SessionLocal", return_value=_SessionContext(db)),
            patch.object(
                assistant_session_service,
                "pop_assistant_undo_batch",
                return_value=stored_actions,
            ) as pop_mock,
        ):
            actions = assistant_session_service.pop_undo_batch(team_id="team-1", user_id="user-1")

        self.assertEqual(actions, stored_actions)
        actions[0]["record_id"] = "changed"
        self.assertEqual(stored_actions[0]["record_id"], "abc")
        pop_mock.assert_called_once_with(db, team_id="team-1", user_id="user-1")


if __name__ == "__main__":
    unittest.main()
