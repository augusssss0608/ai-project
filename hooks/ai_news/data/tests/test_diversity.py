import unittest

from ai_news.data import diversity, schemas


def make_item(source, ai_score, event_key="", topic_tags=None, title="t", url=None, desc=""):
    return {
        "source": source,
        "ai_score": ai_score,
        "title_score": ai_score,
        "event_key": event_key,
        "topic_tags": topic_tags or ["other"],
        "title": title,
        "desc": desc,
        "url": url or f"http://{source}/{title}/{ai_score}",
    }


class TestIsChineseItem(unittest.TestCase):
    def test_pure_chinese(self):
        # CJK 占比 >= 0.3 即视为中文
        self.assertTrue(diversity.is_chinese_item({"title": "Claude Code 重大更新", "desc": "实战分析与案例"}))

    def test_pure_english(self):
        self.assertFalse(diversity.is_chinese_item({"title": "Claude Code update released", "desc": "GA"}))

    def test_below_threshold(self):
        # 大部分英文，少量中文
        item = {"title": "GPT-5.5 release with massive improvements", "desc": ""}
        self.assertFalse(diversity.is_chinese_item(item))


class TestMmrSelect(unittest.TestCase):
    def test_basic_select(self):
        pool = [
            make_item("hn", 9, event_key="e1", topic_tags=["model_release"]),
            make_item("hn", 8, event_key="e2", topic_tags=["tool_release"]),
            make_item("threads", 7, event_key="e3", topic_tags=["tutorial"]),
        ]
        selected, _, metrics = diversity.mmr_select(pool, target_n=10)
        self.assertEqual(len(selected), 3)
        self.assertEqual(metrics["pool_size"], 3)

    def test_event_dedup_hard_cap(self):
        # 5 条同 event_key，硬上限 2
        pool = [
            make_item("hn", 9 - i * 0.1, event_key="gpt55", url=f"u{i}")
            for i in range(5)
        ]
        selected, suppressed, metrics = diversity.mmr_select(pool, target_n=10)
        self.assertEqual(len(selected), 2)  # 硬上限 2
        self.assertEqual(metrics["max_event_count"], 2)
        # 3 条被压
        self.assertEqual(len(suppressed), 3)
        for s in suppressed:
            self.assertEqual(s["reason"], "duplicate_event")

    def test_topic_hard_cap(self):
        # 5 条同 topic 不同 event
        pool = [
            make_item("s1", 9 - i * 0.1, event_key=f"e{i}", topic_tags=["model_release"], url=f"u{i}")
            for i in range(5)
        ]
        selected, _, metrics = diversity.mmr_select(pool, target_n=10)
        # 同 topic 硬上限 4
        self.assertEqual(len(selected), 4)
        self.assertEqual(metrics["max_topic_count"], 4)

    def test_source_hard_cap(self):
        # 5 条同 source，不同 event 不同 topic
        topics = ["paper", "tool_release", "tutorial", "infra", "policy"]
        pool = [
            make_item("hn", 9 - i * 0.1, event_key=f"e{i}", topic_tags=[topics[i]], url=f"u{i}")
            for i in range(5)
        ]
        selected, _, metrics = diversity.mmr_select(pool, target_n=10)
        # 同 source 硬上限 4
        self.assertEqual(len(selected), 4)
        self.assertEqual(metrics["max_source_count"], 4)

    def test_github_excluded(self):
        pool = [
            make_item("github_trending", 10, event_key="repo1"),
            make_item("hn", 5, event_key="e1"),
        ]
        selected, _, metrics = diversity.mmr_select(pool, target_n=10)
        sources = {it["source"] for it in selected}
        self.assertNotIn("github_trending", sources)
        self.assertIn("hn", sources)

    def test_min_score_relax(self):
        # 全部低于 MIN_SCORE，验证兜底；分散到多个 source 和 topic 避免硬上限
        sources = ["hn", "threads", "qbitai", "ithome_tw"]
        topics = ["paper", "tool_release", "tutorial", "infra", "policy",
                  "business", "community_discourse", "model_release",
                  "agent_workflow", "coding_tool"]
        pool = [
            make_item(
                sources[i % len(sources)],
                4,
                event_key=f"e{i}",
                topic_tags=[topics[i % len(topics)]],
                url=f"u{i}",
            )
            for i in range(15)
        ]
        selected, _, metrics = diversity.mmr_select(pool, target_n=10, min_score=5.0)
        # 兜底放宽后应该能选到 10
        self.assertEqual(len(selected), 10)

    def test_event_key_empty_fallback(self):
        # event_key 空，url:<url> 兜底，每条独立 dedup
        pool = [
            make_item("hn", 8, event_key="", url=f"u{i}")
            for i in range(3)
        ]
        selected, _, _ = diversity.mmr_select(pool, target_n=10)
        # 3 条不同 url → 3 个独立 event_key
        self.assertEqual(len(selected), 3)

    def test_chinese_language_bonus(self):
        pool = [
            make_item("hn", 7, event_key="e1", title="GPT-5.5 update", desc=""),
            make_item("hn", 7, event_key="e2", title="GPT-5.5 中文实测", desc="实战分析"),
        ]
        selected, _, _ = diversity.mmr_select(pool, target_n=1)
        self.assertEqual(len(selected), 1)
        # 中文条目应优先（+0.2 bonus）
        self.assertIn("中文", selected[0]["title"])


class TestComputeQualityMetrics(unittest.TestCase):
    def test_avg_and_counts(self):
        featured = [
            {"ai_score": 8, "reason": "短理由", "event_key": "e1"},
            {"ai_score": 7, "reason": "另一个", "event_key": "e2"},
        ]
        raw = [
            {"ai_score": 9, "reason": "x"},
            {"ai_score": 8, "reason": "y"},
        ]
        m = diversity.compute_quality_metrics(featured, raw)
        self.assertEqual(m["featured_avg_ai_score"], 7.5)
        self.assertEqual(m["raw_top10_avg_ai_score"], 8.5)
        self.assertEqual(m["reason_over_40_count"], 0)
        self.assertEqual(m["missing_event_key_count"], 0)

    def test_reason_over_40_detection(self):
        long_reason = "x" * 50
        featured = [{"ai_score": 8, "reason": long_reason, "event_key": "e1"}]
        m = diversity.compute_quality_metrics(featured, [])
        self.assertEqual(m["reason_over_40_count"], 1)

    def test_missing_event_key(self):
        featured = [{"ai_score": 8, "reason": "x", "event_key": ""}]
        m = diversity.compute_quality_metrics(featured, [])
        self.assertEqual(m["missing_event_key_count"], 1)


if __name__ == "__main__":
    unittest.main()
