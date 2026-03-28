import datetime as dt
import decimal
import uuid
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.database import get_db
from app.main import create_app


def build_user(**overrides):
    payload = {
        "id": uuid.uuid4(),
        "wechat_openid": "openid-1",
        "nickname": "Alice",
        "avatar": None,
        "language": "zh-CN",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def build_team(**overrides):
    payload = {
        "id": uuid.uuid4(),
        "name": "TeamHome",
        "owner_id": uuid.uuid4(),
        "join_password": None,
        "members": [],
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class ApiSmokeTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.db = object()
        self.current_user = build_user()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()
        self.client.close()

    def test_auth_login_returns_token_and_user(self):
        user = build_user()

        with (
            patch("app.api.auth.exchange_wechat_code_for_openid", new=AsyncMock(return_value="openid-xyz")),
            patch("app.api.auth.get_or_create_user_by_openid", return_value=user) as user_mock,
        ):
            response = self.client.post(
                "/auth/login",
                json={"code": "wechat-code", "nickname": "Alice", "language": "zh-CN"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("token", data)
        self.assertEqual(data["user"]["id"], str(user.id))
        self.assertEqual(data["user"]["language"], "zh-CN")
        user_mock.assert_called_once_with(
            self.db,
            "openid-xyz",
            nickname="Alice",
            language="zh-CN",
        )

    def test_create_team_returns_serialized_team(self):
        team = build_team(
            name="FamilyTeam",
            owner_id=self.current_user.id,
            is_demo=False,
            join_password="1234",
            members=[SimpleNamespace(), SimpleNamespace()],
        )

        with (
            patch("app.api.teams.ensure_demo_data"),
            patch("app.api.teams.get_team_by_name", side_effect=[None, team]) as team_lookup,
            patch("app.api.teams.create_team", return_value=team) as create_mock,
        ):
            response = self.client.post("/teams", json={"name": "FamilyTeam", "password": "1234"})

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "FamilyTeam")
        self.assertFalse(data["is_demo"])
        self.assertTrue(data["can_write"])
        self.assertEqual(data["join_password"], "1234")
        self.assertEqual(data["member_count"], 2)
        create_mock.assert_called_once_with(
            self.db,
            name="FamilyTeam",
            owner_id=self.current_user.id,
            join_password="1234",
        )
        self.assertEqual(team_lookup.call_count, 2)

    def test_list_teams_includes_demo_team_flags(self):
        demo_team = build_team(
            name="Badz乐队",
            is_demo=True,
            join_password=None,
            members=[SimpleNamespace(), SimpleNamespace(), SimpleNamespace()],
        )

        with (
            patch("app.api.teams.ensure_demo_data"),
            patch("app.api.teams.list_accessible_teams_for_user", return_value=[demo_team]),
        ):
            response = self.client.get("/teams")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertTrue(payload[0]["is_demo"])
        self.assertTrue(payload[0]["is_readonly"])
        self.assertFalse(payload[0]["can_write"])

    def test_leave_demo_team_hides_instead_of_removing_membership(self):
        team_id = uuid.uuid4()
        demo_team = build_team(id=team_id, name="Badz乐队", is_demo=True)

        with (
            patch("app.api.teams.ensure_demo_data"),
            patch("app.api.teams.get_team", return_value=demo_team),
            patch("app.api.teams.is_demo_team_hidden", return_value=False),
            patch("app.api.teams.hide_demo_team") as hide_mock,
        ):
            response = self.client.delete(f"/teams/{team_id}/members/me")

        self.assertEqual(response.status_code, 204)
        hide_mock.assert_called_once_with(self.db, team_id=team_id, user_id=self.current_user.id)

    def test_create_existing_demo_team_unhides_for_user(self):
        team_id = uuid.uuid4()
        demo_team = build_team(id=team_id, name="teamhome开发", is_demo=True, members=[SimpleNamespace()])

        with (
            patch("app.api.teams.ensure_demo_data"),
            patch("app.api.teams.get_team_by_name", side_effect=[demo_team, demo_team]),
            patch("app.api.teams.unhide_demo_team") as unhide_mock,
        ):
            response = self.client.post("/teams", json={"name": "teamhome开发"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "teamhome开发")
        self.assertTrue(response.json()["is_demo"])
        self.assertFalse(response.json()["can_write"])
        unhide_mock.assert_called_once_with(self.db, team_id=team_id, user_id=self.current_user.id)

    def test_create_finance_returns_record_payload(self):
        team_id = uuid.uuid4()
        occurred_at = dt.datetime(2026, 3, 28, 9, 30, tzinfo=dt.timezone.utc)
        created_at = dt.datetime(2026, 3, 28, 9, 35, tzinfo=dt.timezone.utc)
        record = SimpleNamespace(
            id=uuid.uuid4(),
            team_id=team_id,
            user_id=self.current_user.id,
            amount=decimal.Decimal("28.50"),
            type="expense",
            category="Lunch",
            occurred_at=occurred_at,
            location="Office",
            location_latitude=None,
            location_longitude=None,
            note="team meal",
            created_at=created_at,
            user=self.current_user,
        )

        with (
            patch("app.api.finance.can_read_team", return_value=True),
            patch("app.api.finance.can_write_team", return_value=True),
            patch("app.api.finance.create_finance_record", return_value=record) as create_mock,
            patch("app.api.finance.touch_place") as touch_place_mock,
        ):
            response = self.client.post(
                "/finance",
                json={
                    "team_id": str(team_id),
                    "amount": "28.50",
                    "type": "expense",
                    "category": "Lunch",
                    "occurred_at": "2026-03-28T09:30:00+00:00",
                    "location": "Office",
                    "note": "team meal",
                },
            )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["amount"], "28.50")
        self.assertEqual(data["creator_nickname"], "Alice")
        self.assertEqual(data["occurred_at"], "2026-03-28T09:30:00+00:00")
        create_mock.assert_called_once()
        touch_place_mock.assert_called_once_with(self.db, team_id=team_id, name="Office")

    def test_create_schedule_returns_schedule_payload(self):
        team_id = uuid.uuid4()
        start_time = dt.datetime(2026, 3, 29, 8, 0, tzinfo=dt.timezone.utc)
        end_time = dt.datetime(2026, 3, 29, 9, 0, tzinfo=dt.timezone.utc)
        created_at = dt.datetime(2026, 3, 28, 12, 0, tzinfo=dt.timezone.utc)
        schedule = SimpleNamespace(
            id=uuid.uuid4(),
            team_id=team_id,
            title="Morning Sync",
            description="Weekly planning",
            location="Meeting Room",
            location_latitude=None,
            location_longitude=None,
            is_all_day=False,
            start_time=start_time,
            end_time=end_time,
            created_by=self.current_user.id,
            status="pending",
            created_at=created_at,
            creator=self.current_user,
        )

        with (
            patch("app.api.schedules.can_read_team", return_value=True),
            patch("app.api.schedules.can_write_team", return_value=True),
            patch("app.api.schedules.create_schedule", return_value=schedule) as create_mock,
            patch("app.api.schedules.touch_place") as touch_place_mock,
        ):
            response = self.client.post(
                "/schedules",
                json={
                    "team_id": str(team_id),
                    "title": "Morning Sync",
                    "description": "Weekly planning",
                    "location": "Meeting Room",
                    "is_all_day": False,
                    "start_time": "2026-03-29T08:00:00+00:00",
                    "end_time": "2026-03-29T09:00:00+00:00",
                },
            )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Morning Sync")
        self.assertEqual(data["creator_nickname"], "Alice")
        self.assertEqual(data["status"], "pending")
        create_mock.assert_called_once()
        touch_place_mock.assert_called_once_with(self.db, team_id=team_id, name="Meeting Room")

    def test_timeline_returns_grouped_schedule_and_finance(self):
        team_id = uuid.uuid4()
        schedule_item = SimpleNamespace(
            id=uuid.uuid4(),
            team_id=team_id,
            created_at=dt.datetime(2026, 3, 28, 6, 0, tzinfo=dt.timezone.utc),
            creator=self.current_user,
            title="Breakfast Plan",
            description="Meet at cafe",
            location="Cafe",
            is_all_day=False,
            start_time=dt.datetime(2026, 3, 28, 7, 0, tzinfo=dt.timezone.utc),
            end_time=dt.datetime(2026, 3, 28, 8, 0, tzinfo=dt.timezone.utc),
            status="pending",
        )
        finance_item = SimpleNamespace(
            id=uuid.uuid4(),
            team_id=team_id,
            created_at=dt.datetime(2026, 3, 28, 9, 0, tzinfo=dt.timezone.utc),
            user=self.current_user,
            occurred_at=dt.datetime(2026, 3, 28, 9, 30, tzinfo=dt.timezone.utc),
            type="expense",
            category="Breakfast",
            location="Cafe",
            amount=decimal.Decimal("18.80"),
            note="shared meal",
        )

        with (
            patch("app.api.timeline.can_read_team", return_value=True),
            patch("app.api.timeline.list_schedules", return_value=[schedule_item]),
            patch("app.api.timeline.list_finance_records", return_value=[finance_item]),
        ):
            response = self.client.get(
                f"/timeline?team_id={team_id}&window_start=2026-03-27T00:00:00%2B00:00&window_end=2026-03-30T00:00:00%2B00:00"
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["days"]), 1)
        self.assertEqual(data["days"][0]["day_key"], "2026-03-28")
        self.assertEqual(len(data["days"][0]["items"]), 2)
        kinds = [item["kind"] for item in data["days"][0]["items"]]
        self.assertEqual(kinds, ["expense", "schedule"])

    def test_assistant_execute_returns_payload(self):
        team_id = uuid.uuid4()
        assistant_result = {
            "reply": "Recorded expense 88",
            "status": "executed",
            "intent": "create_finance",
            "session_id": None,
            "missing_slots": [],
            "pending_action": None,
            "data": {"can_undo": True, "results": [{"intent": "create_finance", "status": "executed"}]},
            "cards": [],
        }

        with (
            patch("app.api.assistant.can_read_team", return_value=True),
            patch("app.api.assistant.message_requires_write_access", return_value=False),
            patch("app.api.assistant.execute_assistant", return_value=assistant_result) as execute_mock,
        ):
            response = self.client.post(
                "/assistant/execute",
                json={
                    "team_id": str(team_id),
                    "message": "dinner 88",
                    "session_id": None,
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "executed")
        self.assertEqual(data["intent"], "create_finance")
        self.assertTrue(data["data"]["can_undo"])
        execute_mock.assert_called_once()

    def test_assistant_execute_returns_500_on_unexpected_error(self):
        team_id = uuid.uuid4()

        with (
            patch("app.api.assistant.can_read_team", return_value=True),
            patch("app.api.assistant.message_requires_write_access", return_value=False),
            patch("app.api.assistant.execute_assistant", side_effect=RuntimeError("boom")),
        ):
            response = self.client.post(
                "/assistant/execute",
                json={
                    "team_id": str(team_id),
                    "message": "dinner 88",
                    "session_id": None,
                },
            )

        self.assertEqual(response.status_code, 500)
        self.assertTrue(response.json()["detail"])

    def test_assistant_execute_blocks_mutation_on_demo_team(self):
        team_id = uuid.uuid4()

        with (
            patch("app.api.assistant.can_read_team", return_value=True),
            patch("app.api.assistant.message_requires_write_access", return_value=True),
        ):
            response = self.client.post(
                "/assistant/execute",
                json={
                    "team_id": str(team_id),
                    "message": "记一笔排练室费用 180",
                    "session_id": None,
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "TEAM_READ_ONLY")

    def test_assistant_orchestration_returns_404_when_debug_disabled(self):
        with patch(
            "app.api.assistant.get_settings",
            return_value=SimpleNamespace(debug_endpoints_enabled=lambda: False),
        ):
            response = self.client.get("/assistant/orchestration")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Not found")


if __name__ == "__main__":
    unittest.main()
