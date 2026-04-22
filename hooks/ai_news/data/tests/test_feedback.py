import unittest
from unittest.mock import patch
from ai_news.data.feedback import (
    get_stage, get_positives, get_explicit_negatives, build_examples_inline,
)


class TestGetStage(unittest.TestCase):
    def test_cold_under_10(self):
        fb = {"votes": {f"u{i}": {"source": "hackernews", "score": "up"} for i in range(5)}}
        self.assertEqual(get_stage("hackernews", fb), "cold")

    def test_mid_10_to_50(self):
        fb = {"votes": {f"u{i}": {"source": "hackernews", "score": "up"} for i in range(25)}}
        self.assertEqual(get_stage("hackernews", fb), "mid")

    def test_hot_50_plus(self):
        fb = {"votes": {f"u{i}": {"source": "hackernews", "score": "up"} for i in range(60)}}
        self.assertEqual(get_stage("hackernews", fb), "hot")

    def test_other_source_not_counted(self):
        fb = {"votes": {f"u{i}": {"source": "github_trending", "score": "up"} for i in range(60)}}
        self.assertEqual(get_stage("hackernews", fb), "cold")

    def test_empty_source_not_counted(self):
        fb = {"votes": {f"u{i}": {"source": "", "score": "up"} for i in range(60)}}
        self.assertEqual(get_stage("hackernews", fb), "cold")


class TestGetPositives(unittest.TestCase):
    def test_ups_returned_for_source_ts_desc(self):
        fb = {
            "votes": {
                "url1": {"source": "hackernews", "title": "A", "ts": "2026-04-20T10:00:00+09:00", "score": "up"},
                "url2": {"source": "github_trending", "title": "B", "ts": "2026-04-20T11:00:00+09:00", "score": "up"},
                "url3": {"source": "hackernews", "title": "C", "ts": "2026-04-20T12:00:00+09:00", "score": "up"},
            }
        }
        out = get_positives("hackernews", fb, limit=10)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["title"], "C")  # ts desc
        self.assertEqual(out[1]["title"], "A")

    def test_star_ranked_before_up(self):
        fb = {
            "votes": {
                "url_up_new": {"source": "hackernews", "title": "UP_NEW", "ts": "2026-04-22T10:00:00+09:00", "score": "up"},
                "url_star_old": {"source": "hackernews", "title": "STAR_OLD", "ts": "2026-04-20T10:00:00+09:00", "score": "star"},
            }
        }
        out = get_positives("hackernews", fb, limit=10)
        self.assertEqual(out[0]["title"], "STAR_OLD")  # star 优先于 up 即使 ts 更早
        self.assertEqual(out[1]["title"], "UP_NEW")

    def test_down_excluded_from_positives(self):
        fb = {
            "votes": {
                "url_up": {"source": "hackernews", "title": "U", "ts": "2026-04-20T10:00:00+09:00", "score": "up"},
                "url_down": {"source": "hackernews", "title": "D", "ts": "2026-04-20T11:00:00+09:00", "score": "down"},
            }
        }
        out = get_positives("hackernews", fb, limit=10)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["title"], "U")


class TestGetExplicitNegatives(unittest.TestCase):
    def test_returns_down_for_source(self):
        fb = {
            "votes": {
                "url1": {"source": "hackernews", "title": "D1", "ts": "2026-04-20T10:00:00+09:00", "score": "down"},
                "url2": {"source": "hackernews", "title": "U1", "ts": "2026-04-20T11:00:00+09:00", "score": "up"},
                "url3": {"source": "github_trending", "title": "D_OTHER", "ts": "2026-04-20T12:00:00+09:00", "score": "down"},
            }
        }
        out = get_explicit_negatives("hackernews", fb, limit=10)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["title"], "D1")


class TestBuildExamplesInline(unittest.TestCase):
    def test_returns_formatted_md_with_all_four_sections(self):
        fb = {
            "votes": {
                "url_star": {"source": "hackernews", "title": "STAR_A", "ts": "2026-04-20T10:00:00+09:00", "score": "star"},
                "url_up": {"source": "hackernews", "title": "UP_B", "ts": "2026-04-20T11:00:00+09:00", "score": "up"},
                "url_down": {"source": "hackernews", "title": "DOWN_C", "ts": "2026-04-20T12:00:00+09:00", "score": "down"},
            }
        }
        with patch("ai_news.data.feedback._history") as mock_h:
            mock_h.get_negatives.return_value = []
            out = build_examples_inline("hackernews", fb)
        self.assertIn("强正例 ⭐", out)
        self.assertIn("正例 👍", out)
        self.assertIn("显式负例 👎", out)
        self.assertIn("隐式负例", out)
        self.assertIn("[2026-04-20] STAR_A", out)
        self.assertIn("[2026-04-20] UP_B", out)
        self.assertIn("[2026-04-20] DOWN_C", out)


if __name__ == "__main__":
    unittest.main()
