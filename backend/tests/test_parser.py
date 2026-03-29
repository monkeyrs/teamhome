import datetime as dt
import unittest
from unittest.mock import patch

from app.services.llm import parser


class ParserTests(unittest.TestCase):
    def test_parse_schedule_text_resolves_next_week_weekday(self):
        now = dt.datetime(2026, 3, 29, 10, 30, tzinfo=dt.timezone(dt.timedelta(hours=8)))
        with patch("app.services.llm.parser._now_local", return_value=now):
            parsed = parser.parse_schedule_text("创建日程 下周三晚上八点乐队排练")

        self.assertEqual(parsed["start_time"], "2026-04-01T20:00:00+08:00")
        self.assertEqual(parsed["end_time"], "2026-04-01T21:00:00+08:00")
        self.assertEqual(parsed["title"], "乐队排练")

    def test_parse_schedule_text_resolves_bare_weekday_to_upcoming_day(self):
        now = dt.datetime(2026, 3, 29, 10, 30, tzinfo=dt.timezone(dt.timedelta(hours=8)))
        with patch("app.services.llm.parser._now_local", return_value=now):
            parsed = parser.parse_schedule_text("周三晚上八点乐队排练")

        self.assertEqual(parsed["start_time"], "2026-04-01T20:00:00+08:00")
        self.assertEqual(parsed["title"], "乐队排练")

    def test_parse_schedule_text_resolves_month_day(self):
        now = dt.datetime(2026, 3, 29, 10, 30, tzinfo=dt.timezone(dt.timedelta(hours=8)))
        with patch("app.services.llm.parser._now_local", return_value=now):
            parsed = parser.parse_schedule_text("创建日程 4月4日下午三点 soundcheck")

        self.assertEqual(parsed["start_time"], "2026-04-04T15:00:00+08:00")
        self.assertEqual(parsed["end_time"], "2026-04-04T16:00:00+08:00")
        self.assertEqual(parsed["title"], "soundcheck")


if __name__ == "__main__":
    unittest.main()
