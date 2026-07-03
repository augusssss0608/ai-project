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


if __name__ == "__main__":
    unittest.main()
