import unittest
from unittest.mock import patch

from ai_news.data import content_fetcher, schemas


class TestSelectBoundaryCandidates(unittest.TestCase):
    def _make(self, source, title_score, url=None):
        return {
            "source": source,
            "title_score": title_score,
            "url": url or f"http://example.com/{source}/{title_score}",
        }

    def test_select_basic_boundary(self):
        pool = [
            self._make("hn", 9),     # high, skip
            self._make("hn", 7),     # boundary
            self._make("hn", 5),     # boundary
            self._make("hn", 2),     # low, skip
            self._make("threads", 6),  # boundary
        ]
        result = content_fetcher.select_boundary_candidates(pool, cap=10)
        urls = {it["url"] for it in result}
        self.assertEqual(len(result), 3)
        self.assertIn("http://example.com/hn/7", urls)
        self.assertIn("http://example.com/hn/5", urls)
        self.assertIn("http://example.com/threads/6", urls)

    def test_excludes_github_trending(self):
        pool = [
            self._make("github_trending", 7),
            self._make("hn", 7),
        ]
        result = content_fetcher.select_boundary_candidates(pool, cap=10)
        sources = {it["source"] for it in result}
        self.assertNotIn("github_trending", sources)
        self.assertIn("hn", sources)

    def test_cap_truncates_by_title_score_desc(self):
        pool = [self._make("hn", 5 + i % 3, url=f"u{i}") for i in range(20)]
        result = content_fetcher.select_boundary_candidates(pool, cap=5)
        self.assertEqual(len(result), 5)
        # 应优先取分数最高的（=7）
        scores = [it["title_score"] for it in result]
        self.assertTrue(all(s >= 6 for s in scores), f"expected >=6, got {scores}")

    def test_min_fetch_补足(self):
        # 只有 1 条边界，触发补足
        pool = [
            self._make("hn", 6, url="boundary"),
            self._make("hn", 9, url="high1"),
            self._make("hn", 9, url="high2"),
            self._make("hn", 9, url="high3"),
            self._make("hn", 9, url="high4"),
            self._make("hn", 9, url="high5"),
            self._make("hn", 9, url="high6"),  # rank 6 进补足
            self._make("hn", 9, url="high7"),  # rank 7
            self._make("hn", 9, url="high8"),
        ]
        result = content_fetcher.select_boundary_candidates(pool, cap=10, min_fetch=4)
        self.assertGreaterEqual(len(result), 4)
        urls = {it["url"] for it in result}
        self.assertIn("boundary", urls)

    def test_hard_cap_enforced(self):
        pool = [self._make("hn", 6, url=f"u{i}") for i in range(20)]
        result = content_fetcher.select_boundary_candidates(pool, cap=10, hard_cap=12)
        self.assertLessEqual(len(result), 12)

    def test_empty_pool(self):
        self.assertEqual(content_fetcher.select_boundary_candidates([]), [])

    def test_no_eligible(self):
        # 全部 github_trending
        pool = [self._make("github_trending", 7)]
        self.assertEqual(content_fetcher.select_boundary_candidates(pool), [])


class TestTruncateReason(unittest.TestCase):
    def test_short_passthrough(self):
        self.assertEqual(content_fetcher.truncate_reason("短理由"), "短理由")

    def test_exact_40(self):
        s = "x" * 40
        self.assertEqual(content_fetcher.truncate_reason(s), s)

    def test_truncate_with_ellipsis(self):
        s = "x" * 50
        result = content_fetcher.truncate_reason(s, max_chars=40)
        self.assertEqual(len(result), 40)
        self.assertTrue(result.endswith("…"))

    def test_empty(self):
        self.assertEqual(content_fetcher.truncate_reason(""), "")
        self.assertEqual(content_fetcher.truncate_reason(None), "")


class TestMergeContentScore(unittest.TestCase):
    def test_merge_truncates_reason(self):
        item = {
            "title_score": 7,
            "content_status": schemas.CONTENT_STATUS_NOT_ATTEMPTED,
            "reason": "x" * 60,
        }
        content_fetcher.merge_content_score(item)
        self.assertLessEqual(len(item["reason"]), 40)
        self.assertTrue(item["reason"].endswith("…"))


    def test_fetched_合成(self):
        item = {
            "title_score": 7,
            "content_score": 8,
            "content_status": schemas.CONTENT_STATUS_FETCHED,
        }
        content_fetcher.merge_content_score(item)
        # 0.4 * 7 + 0.6 * 8 = 2.8 + 4.8 = 7.6
        self.assertEqual(item["ai_score"], 7.6)

    def test_failed_惩罚(self):
        item = {
            "title_score": 7,
            "content_status": schemas.CONTENT_STATUS_FAILED,
        }
        content_fetcher.merge_content_score(item)
        # content_score = max(0, 7-1) = 6
        # ai_score = 0.4 * 7 + 0.6 * 6 = 2.8 + 3.6 = 6.4
        self.assertEqual(item["content_score"], 6)
        self.assertEqual(item["ai_score"], 6.4)

    def test_not_attempted_keep_title(self):
        item = {"title_score": 7, "content_status": schemas.CONTENT_STATUS_NOT_ATTEMPTED}
        content_fetcher.merge_content_score(item)
        self.assertEqual(item["ai_score"], 7)

    def test_failed_zero_bound(self):
        item = {"title_score": 0, "content_status": schemas.CONTENT_STATUS_FAILED}
        content_fetcher.merge_content_score(item)
        # title=0, content = max(0, 0-1) = 0
        self.assertEqual(item["content_score"], 0)
        self.assertEqual(item["ai_score"], 0)

    def test_fetched_missing_content_score_falls_back(self):
        # fetched 但二轮 scorer 没给 content_score → 走 failed 路径
        item = {"title_score": 7, "content_status": schemas.CONTENT_STATUS_FETCHED}
        content_fetcher.merge_content_score(item)
        self.assertEqual(item["content_status"], schemas.CONTENT_STATUS_FAILED)
        self.assertEqual(item["ai_score"], 6.4)


class TestFetchBoundaryContents(unittest.TestCase):
    def test_all_success(self):
        items = [{"url": "http://a"}, {"url": "http://b"}]
        with patch.object(content_fetcher, "fetch_article_text",
                          return_value=("正文内容", "")):
            metrics = content_fetcher.fetch_boundary_contents(items, max_workers=2)
        self.assertEqual(metrics["attempted"], 2)
        self.assertEqual(metrics["succeeded"], 2)
        self.assertEqual(metrics["failed"], 0)
        self.assertEqual(metrics["success_rate"], 1.0)
        for it in items:
            self.assertEqual(it["content_status"], schemas.CONTENT_STATUS_FETCHED)
            self.assertEqual(it["full_content"], "正文内容")

    def test_all_fail(self):
        items = [{"url": "http://a"}, {"url": "http://b"}]
        with patch.object(content_fetcher, "fetch_article_text",
                          return_value=("", "jina http 403")):
            metrics = content_fetcher.fetch_boundary_contents(items, max_workers=2)
        self.assertEqual(metrics["succeeded"], 0)
        self.assertEqual(metrics["failed"], 2)
        for it in items:
            self.assertEqual(it["content_status"], schemas.CONTENT_STATUS_FAILED)
            self.assertEqual(it["full_content"], "")
            self.assertEqual(it["fetch_error"], "jina http 403")

    def test_mixed(self):
        items = [{"url": "http://ok"}, {"url": "http://fail"}]

        def side_effect(url, **kw):
            if "ok" in url:
                return "good content", ""
            return "", "timeout"

        with patch.object(content_fetcher, "fetch_article_text", side_effect=side_effect):
            metrics = content_fetcher.fetch_boundary_contents(items, max_workers=2)
        self.assertEqual(metrics["attempted"], 2)
        self.assertEqual(metrics["succeeded"], 1)
        self.assertEqual(metrics["failed"], 1)
        self.assertAlmostEqual(metrics["success_rate"], 0.5)
        # 按 url 找具体哪条成功
        ok_item = next(it for it in items if "ok" in it["url"])
        fail_item = next(it for it in items if "fail" in it["url"])
        self.assertEqual(ok_item["content_status"], schemas.CONTENT_STATUS_FETCHED)
        self.assertEqual(fail_item["content_status"], schemas.CONTENT_STATUS_FAILED)

    def test_empty(self):
        metrics = content_fetcher.fetch_boundary_contents([])
        self.assertEqual(metrics["attempted"], 0)
        self.assertEqual(metrics["succeeded"], 0)
        self.assertEqual(metrics["failed"], 0)


if __name__ == "__main__":
    unittest.main()
