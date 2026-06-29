from __future__ import annotations

import unittest
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

PARSER_PATH = Path(__file__).parents[1] / "custom_components/codex_usage/parser.py"
spec = spec_from_file_location("codex_usage_parser", PARSER_PATH)
assert spec is not None and spec.loader is not None
parser = module_from_spec(spec)
spec.loader.exec_module(parser)

parse_usage_response = parser.parse_usage_response
retry_after_to_datetime = parser.retry_after_to_datetime


class ParserTest(unittest.TestCase):
    def test_parses_usage_body(self) -> None:
        data = parse_usage_response(
            {
                "plan_type": "plus",
                "rate_limit": {
                    "allowed": True,
                    "limit_reached": False,
                    "primary_window": {
                        "used_percent": 42,
                        "limit_window_seconds": 18000,
                        "reset_after_seconds": 1200,
                        "reset_at": 1782780000,
                    },
                },
                "credits": {"has_credits": True, "unlimited": False, "balance": "12.5"},
                "rate_limit_reset_credits": {"available_count": 2},
            },
            {},
        )

        self.assertEqual(data["plan_type"], "plus")
        self.assertEqual(data["codex_primary_usage_percent"], 42)
        self.assertEqual(data["codex_primary_window_minutes"], 300)
        self.assertEqual(data["credits_balance"], 12.5)
        self.assertEqual(data["reset_credits_available"], 2)
        self.assertTrue(data["codex_allowed"])

    def test_parses_codex_headers(self) -> None:
        data = parse_usage_response(
            {},
            {
                "x-codex-primary-used-percent": "51.5",
                "x-codex-primary-window-minutes": "300",
                "x-codex-primary-reset-at": "1782780000",
                "x-codex-credits-has-credits": "true",
                "x-codex-credits-unlimited": "false",
                "x-codex-credits-balance": "7",
                "x-codex-promo-message": "hello",
            },
        )

        self.assertEqual(data["codex_primary_usage_percent"], 51.5)
        self.assertEqual(data["codex_primary_window_minutes"], 300)
        self.assertEqual(data["credits_enabled"], True)
        self.assertEqual(data["credits_balance"], 7)
        self.assertEqual(data["promo_message"], "hello")

    def test_retry_after_delta(self) -> None:
        now = datetime(2026, 6, 30, 0, 0, tzinfo=UTC)
        self.assertEqual(
            retry_after_to_datetime("120", now),
            datetime(2026, 6, 30, 0, 2, tzinfo=UTC),
        )


if __name__ == "__main__":
    unittest.main()
