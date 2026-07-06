import unittest
import ai_news.data.fetchers as F
from ai_news.data.fetchers import _TrendingParser


class TestTodayStarsInt(unittest.TestCase):
    def test_parses_today_stars_as_int(self):
        html = """
        <article class="Box-row">
          <h2><a href="/owner/repo">owner/repo</a></h2>
          <p class="col-9">desc</p>
          <a class="Link--muted" href="/owner/repo/stargazers">1,234</a>
          <span class="d-inline-block float-sm-right">123 stars today</span>
        </article>
        <article class="Box-row">
          <h2><a href="/a/b">a/b</a></h2>
          <p class="col-9">desc</p>
          <a class="Link--muted" href="/a/b/stargazers">9</a>
          <span class="d-inline-block float-sm-right">9 stars today</span>
        </article>
        """
        p = _TrendingParser()
        p.feed(html)
        self.assertEqual(p.items[0]["today_stars_int"], 123)
        self.assertEqual(p.items[1]["today_stars_int"], 9)
        # 排序 (123 > 9) 不出现字典序 bug
        p.items.sort(key=lambda x: x["today_stars_int"], reverse=True)
        self.assertEqual(p.items[0]["today_stars_int"], 123)


class TestGithubTrendingMultiFailure(unittest.TestCase):
    """fetch_github_trending_multi 的失败暴露 / 降级不误报行为."""

    def setUp(self):
        self._rss, self._search = F.fetch_github_trending_rss, F.fetch_github_search

    def tearDown(self):
        F.fetch_github_trending_rss, F.fetch_github_search = self._rss, self._search

    def test_all_empty_no_exception_raises(self):
        # 关键盲区: 各源 HTTP 200 但返回空、都不抛异常时, 仍应 raise 暴露失败
        F.fetch_github_trending_rss = lambda since, limit=25: []
        F.fetch_github_search = lambda params: []
        with self.assertRaises(RuntimeError):
            F.fetch_github_trending_multi({})

    def test_all_exception_raises(self):
        def boom(*a, **k):
            raise RuntimeError("HTTP 403")
        F.fetch_github_trending_rss = boom
        F.fetch_github_search = boom
        with self.assertRaises(RuntimeError):
            F.fetch_github_trending_multi({})

    def test_partial_success_no_raise(self):
        # RSS 全挂但 total 正常 = 成功降级, 不得误报
        def boom(*a, **k):
            raise RuntimeError("HTTP 403")
        F.fetch_github_trending_rss = boom
        F.fetch_github_search = lambda params: [{
            "title": "a/b", "url": "u", "total_stars_int": 9,
            "daily_stars": 0, "weekly_stars": 0, "monthly_stars": 0,
        }]
        out = F.fetch_github_trending_multi({})
        self.assertTrue(out)
        self.assertEqual({x["dimension"] for x in out}, {"total"})

    def test_search_empty_total_falls_back_to_pool(self):
        # Jina 搜索空 (云端封 github 全局端点) 时, total 回退到 trending 池按总 star 排
        rss = [
            {"url": "u1", "title": "big/repo", "total_stars_int": 500,
             "daily_stars": 0, "weekly_stars": 0, "monthly_stars": 0},
            {"url": "u2", "title": "small/repo", "total_stars_int": 20,
             "daily_stars": 0, "weekly_stars": 0, "monthly_stars": 0},
        ]
        F.fetch_github_trending_rss = lambda since, limit=25: rss
        F.fetch_github_search = lambda params: []
        out = F.fetch_github_trending_multi({})
        total = [x for x in out if x["dimension"] == "total"]
        self.assertEqual([x["url"] for x in total], ["u1", "u2"])  # 按总 star 降序


class TestGithubSearch(unittest.TestCase):
    """fetch_github_search 走 Jina 代理: 解析 stargazers 锚点 + 描述, 失败返 []."""

    _SAMPLE = (
        "### ![Image 1](https://github.com/owner1.png?size=40)\n\n"
        "[owner1/claude-tool](https://github.com/owner1/claude-tool)\n\n"
        "A Claude helper tool.\n\n"
        "[topic](https://github.com/topics/x)\n\n"
        "*    Python\n"
        "·*   [12k](https://github.com/owner1/claude-tool/stargazers)\n"
        "·*   Updated 1 day ago\n\n"
        "### ![Image 2](https://github.com/owner2.png?size=40)\n\n"
        "[owner2/mcp-server](https://github.com/owner2/mcp-server)\n\n"
        "An MCP server.\n\n"
        "*    Go\n"
        "·*   [3,400](https://github.com/owner2/mcp-server/stargazers)\n"
    )

    def setUp(self):
        self._fetch = F._fetch

    def tearDown(self):
        F._fetch = self._fetch

    def test_parses_full_name_stars_desc(self):
        F._fetch = lambda url, headers=None, timeout=25: self._SAMPLE.encode()
        out = F.fetch_github_search({"queries": ["claude"], "pages": 1, "min_stars": 30})
        by = {it["title"]: it for it in out}
        self.assertEqual(by["owner1/claude-tool"]["total_stars_int"], 12000)
        self.assertEqual(by["owner1/claude-tool"]["desc"], "A Claude helper tool.")
        self.assertEqual(by["owner1/claude-tool"]["url"],
                         "https://github.com/owner1/claude-tool")
        self.assertEqual(by["owner2/mcp-server"]["total_stars_int"], 3400)

    def test_dedups_across_pages_and_queries(self):
        F._fetch = lambda url, headers=None, timeout=25: self._SAMPLE.encode()
        out = F.fetch_github_search({"queries": ["claude", "topic:mcp"], "pages": 2})
        self.assertEqual(sorted(it["title"] for it in out),
                         ["owner1/claude-tool", "owner2/mcp-server"])

    def test_fetch_failure_returns_empty(self):
        def boom(*a, **k):
            raise RuntimeError("network down")
        F._fetch = boom
        self.assertEqual(
            F.fetch_github_search({"queries": ["claude"], "pages": 1}), [])

    def test_no_stargazers_returns_empty(self):
        F._fetch = lambda url, headers=None, timeout=25: b"no results here"
        self.assertEqual(
            F.fetch_github_search({"queries": ["claude"], "pages": 1}), [])


if __name__ == "__main__":
    unittest.main()
