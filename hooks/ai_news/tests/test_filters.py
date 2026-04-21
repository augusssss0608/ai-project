import unittest
from ai_news.filters import is_pure_ai_news, apply_hard_filter


class TestIsPureAiNews(unittest.TestCase):
    def test_hard_noise_rejects_vulnerability(self):
        self.assertFalse(is_pure_ai_news("GPT 漏洞导致数据泄露"))
        self.assertFalse(is_pure_ai_news("OpenAI CVE-2024-xxxx 披露"))

    def test_core_ai_passes_even_with_soft_noise(self):
        # "融資" 是 soft noise, 但 Claude 是 core AI 产品
        self.assertTrue(is_pure_ai_news("Claude 新版本发布"))

    def test_soft_noise_rejects_when_only_secondary_keyword(self):
        # "LLM" 是次级关键词, "融資" 是 soft noise → 剔除
        self.assertFalse(is_pure_ai_news("某 LLM 公司融資 1 億美元"))

    def test_no_ai_keyword_rejects(self):
        self.assertFalse(is_pure_ai_news("iPhone 新机发布"))


class TestApplyHardFilter(unittest.TestCase):
    def test_filter_removes_hard_noise(self):
        items = [
            {"title": "Claude 4.7 发布", "url": "a"},
            {"title": "GPT 漏洞 CVE-2024", "url": "b"},
            {"title": "量子位融资 1 亿", "url": "c"},
        ]
        out = apply_hard_filter(items)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["url"], "a")


if __name__ == "__main__":
    unittest.main()
