"""Unit tests for weekly marker parsing and replacement (no MCP)."""

from __future__ import annotations

import unittest

from phase5_delivery.src.gdocs_weekly_idempotent import (
    api_span_for_plain_span,
    build_week_block,
    doc_json_to_plain_with_index_map,
    find_week_span_in_plain,
    is_well_formed_week_id,
    replace_week_section,
    week_id_from_report_date,
)


class WeeklyIdempotentTests(unittest.TestCase):
    def test_week_id_from_month_tag(self) -> None:
        self.assertEqual(week_id_from_report_date("March-W4-2026"), "March-W4-2026")

    def test_week_id_from_date_string(self) -> None:
        result = week_id_from_report_date("2026-03-24")
        self.assertEqual(result, "March-W4-2026")

    def test_is_well_formed_week_id(self) -> None:
        self.assertTrue(is_well_formed_week_id("March-W4-2026"))
        self.assertTrue(is_well_formed_week_id("January-W1-2026"))
        self.assertFalse(is_well_formed_week_id("2026-W13"))
        self.assertFalse(is_well_formed_week_id("2026-03-24"))

    def test_build_and_find_span(self) -> None:
        wid = "March-W4-2026"
        body = "hello pulse"
        block = build_week_block(wid, body, section_title="Title")
        plain = f"intro\n\n{block}\ntrailer"
        span = find_week_span_in_plain(plain, wid)
        self.assertIsNotNone(span)
        start, end = span  # type: ignore[misc]
        self.assertEqual(plain[start:end], block)

    def test_find_span_rejects_partial_marker(self) -> None:
        plain = "===== WEEK: March-W4-2026 =====\nno end"
        self.assertIsNone(find_week_span_in_plain(plain, "March-W4-2026"))

    def test_replace_week_section_idempotent(self) -> None:
        wid = "March-W4-2026"
        b1 = build_week_block(wid, "v1", section_title="T")
        b2 = build_week_block(wid, "v2", section_title="T")
        doc = f"keep\n{b1}\ntail"
        out = replace_week_section(doc, wid, b2)
        self.assertEqual(out.count("===== WEEK"), 1)
        self.assertIn("v2", out)
        self.assertNotIn("v1", out)

    def test_api_span_for_plain_span(self) -> None:
        idx = [10, 11]
        self.assertEqual(api_span_for_plain_span(idx, 0, 2), (10, 12))

    def test_doc_json_to_plain_and_map(self) -> None:
        doc = {
            "body": {
                "content": [
                    {
                        "startIndex": 1,
                        "endIndex": 3,
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 1,
                                    "endIndex": 3,
                                    "textRun": {"content": "Hi"},
                                }
                            ]
                        },
                    }
                ]
            }
        }
        plain, m = doc_json_to_plain_with_index_map(doc)
        self.assertEqual(plain, "Hi")
        self.assertEqual(m, [1, 2])


if __name__ == "__main__":
    unittest.main()
