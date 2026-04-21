import unittest
from unittest.mock import patch
from ai_news.feedback import get_stage, get_positives, build_examples_inline


class TestGetStage(unittest.TestCase):
    def test_cold_under_10(self):
        fb = {"votes": {f"u{i}": {"source": "hackernews"} for i in range(5)}}
        self.assertEqual(get_stage("hackernews", fb), "cold")

    def test_mid_10_to_50(self):
        fb = {"votes": {f"u{i}": {"source": "hackernews"} for i in range(25)}}
        self.assertEqual(get_stage("hackernews", fb), "mid")

    def test_hot_50_plus(self):
        fb = {"votes": {f"u{i}": {"source": "hackernews"} for i in range(60)}}
        self.assertEqual(get_stage("hackernews", fb), "hot")

    def test_other_source_not_counted(self):
        fb = {"votes": {f"u{i}": {"source": "github_trending"} for i in range(60)}}
        self.assertEqual(get_stage("hackernews", fb), "cold")

    def test_empty_source_not_counted(self):
        fb = {"votes": {f"u{i}": {"source": ""} for i in range(60)}}
        self.assertEqual(get_stage("hackernews", fb), "cold")


class TestGetPositives(unittest.TestCase):
    def test_returns_positives_for_source(self):
        fb = {
            "votes": {
                "url1": {"source": "hackernews", "title": "A", "ts": "2026-04-20T10:00:00+09:00"},
                "url2": {"source": "github_trending", "title": "B", "ts": "2026-04-20T11:00:00+09:00"},
                "url3": {"source": "hackernews", "title": "C", "ts": "2026-04-20T12:00:00+09:00"},
            }
        }
        out = get_positives("hackernews", fb, limit=10)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["title"], "C")  # 按 ts desc
        self.assertEqual(out[1]["title"], "A")


class TestBuildExamplesInline(unittest.TestCase):
    def test_returns_formatted_md_string(self):
        fb = {"votes": {"url1": {"source": "hackernews", "title": "A", "ts": "2026-04-20T10:00:00+09:00"}}}
        with patch("ai_news.feedback._history") as mock_h:
            mock_h.get_negatives.return_value = []
            out = build_examples_inline("hackernews", fb)
        self.assertIn("正例", out)
        self.assertIn("负例", out)
        self.assertIn("[2026-04-20] A", out)


if __name__ == "__main__":
    unittest.main()
