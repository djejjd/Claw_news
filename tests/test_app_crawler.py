"""Tests for app/tools/crawler.py — fetch_news() RSS crawler."""

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers: build fake feedparser entries
# ---------------------------------------------------------------------------

def _make_entry(title, link, summary, published_parsed=None):
    return {
        "title": title,
        "link": link,
        "summary": summary,
        "published_parsed": published_parsed,
    }


def _make_parsed(entries):
    """Return a MagicMock that mimics a feedparser.FeedParserDict."""
    mock = MagicMock()
    mock.entries = entries
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFetchNews:
    """Tests for fetch_news() — the async RSS crawler."""

    async def test_parses_multiple_urls(self):
        """Each URL is fed to feedparser.parse exactly once."""
        from app.tools.crawler import fetch_news

        urls = ["https://a.com/rss", "https://b.com/rss"]
        with patch("app.tools.crawler.feedparser") as mock_fp:
            mock_fp.parse.side_effect = lambda url: _make_parsed(
                [_make_entry(f"From {url}", url + "/1", "summary")]
            )
            result = await fetch_news(urls, limit=10)

        assert mock_fp.parse.call_count == 2
        assert len(result) == 2

    async def test_dedup_by_link_keeps_first(self):
        """When two feeds return the same link, only the first is kept."""
        from app.tools.crawler import fetch_news

        urls = ["https://a.com/rss", "https://b.com/rss"]
        with patch("app.tools.crawler.feedparser") as mock_fp:
            def _parse(url):
                if "a.com" in url:
                    return _make_parsed([
                        _make_entry("First", "https://dup.link", "summary a"),
                        _make_entry("Unique A", "https://a.com/unique", "summary"),
                    ])
                return _make_parsed([
                    _make_entry("Second (dup)", "https://dup.link", "summary b"),
                    _make_entry("Unique B", "https://b.com/unique", "summary"),
                ])

            mock_fp.parse.side_effect = _parse
            result = await fetch_news(urls, limit=10)

        links = [r["link"] for r in result]
        assert "https://dup.link" in links
        assert links.count("https://dup.link") == 1
        # First occurrence wins (from feed a)
        dup = next(r for r in result if r["link"] == "https://dup.link")
        assert dup["title"] == "First"

    async def test_limit_default_10(self):
        """Results are capped at 10 by default."""
        from app.tools.crawler import fetch_news

        urls = ["https://a.com/rss"]
        entries = [
            _make_entry(f"Item {i}", f"https://a.com/{i}", f"Summary {i}")
            for i in range(20)
        ]
        with patch("app.tools.crawler.feedparser") as mock_fp:
            mock_fp.parse.return_value = _make_parsed(entries)
            result = await fetch_news(urls)

        assert len(result) == 10

    async def test_limit_custom(self):
        """Results respect an explicit limit."""
        from app.tools.crawler import fetch_news

        urls = ["https://a.com/rss"]
        entries = [
            _make_entry(f"Item {i}", f"https://a.com/{i}", f"Summary {i}")
            for i in range(10)
        ]
        with patch("app.tools.crawler.feedparser") as mock_fp:
            mock_fp.parse.return_value = _make_parsed(entries)
            result = await fetch_news(urls, limit=3)

        assert len(result) == 3

    async def test_output_field_names(self):
        """Each result dict has title, link, summary, published_at."""
        from app.tools.crawler import fetch_news

        urls = ["https://a.com/rss"]
        entry = _make_entry("Test Title", "https://a.com/1", "<p>Some summary</p>", (2026, 5, 17))
        with patch("app.tools.crawler.feedparser") as mock_fp:
            mock_fp.parse.return_value = _make_parsed([entry])
            result = await fetch_news(urls)

        assert len(result) == 1
        item = result[0]
        assert set(item.keys()) == {"title", "link", "summary", "published_at"}
        assert item["title"] == "Test Title"
        assert item["link"] == "https://a.com/1"
        assert item["published_at"] == "2026-05-17"

    async def test_html_stripped_from_summary(self):
        """Summary has HTML tags removed."""
        from app.tools.crawler import fetch_news

        urls = ["https://a.com/rss"]
        entry = _make_entry("Title", "https://a.com/1", "<p>Hello <b>World</b></p>")
        with patch("app.tools.crawler.feedparser") as mock_fp:
            mock_fp.parse.return_value = _make_parsed([entry])
            result = await fetch_news(urls)

        assert result[0]["summary"] == "Hello World"

    async def test_failed_feed_skipped_others_processed(self, caplog):
        """When one RSS URL raises, it is logged and skipped; others still work."""
        from app.tools.crawler import fetch_news

        urls = ["https://bad.com/rss", "https://good.com/rss"]
        with patch("app.tools.crawler.feedparser") as mock_fp:
            def _parse(url):
                if "bad" in url:
                    raise ConnectionError("timeout")
                return _make_parsed([
                    _make_entry("Good", "https://good.com/1", "Works")
                ])

            mock_fp.parse.side_effect = _parse
            result = await fetch_news(urls, limit=10)

        assert len(result) == 1
        assert result[0]["title"] == "Good"
        # Check that the failure was logged (warning) via caplog
        assert any("bad.com" in r.message for r in caplog.records if r.levelname == "WARNING")

    async def test_empty_when_all_feeds_fail(self):
        """Returns [] when every RSS URL fails."""
        from app.tools.crawler import fetch_news

        urls = ["https://bad1.com/rss", "https://bad2.com/rss"]
        with patch("app.tools.crawler.feedparser") as mock_fp:
            mock_fp.parse.side_effect = RuntimeError("all dead")
            result = await fetch_news(urls, limit=10)

        assert result == []

    async def test_uses_thread_pool_for_sync_parse(self):
        """feedparser.parse() is sync; the implementation MUST run it in a thread pool."""
        from app.tools.crawler import fetch_news

        urls = ["https://a.com/rss"]
        with patch("app.tools.crawler.feedparser") as mock_fp:
            mock_fp.parse.return_value = _make_parsed([
                _make_entry("Thread test", "https://a.com/1", "summary")
            ])
            with patch("app.tools.crawler.asyncio.to_thread") as mock_to_thread:
                mock_to_thread.return_value = mock_fp.parse.return_value
                result = await fetch_news(urls, limit=10)

        # Each parse should go through asyncio.to_thread
        assert mock_to_thread.call_count == 1
        assert len(result) == 1

    async def test_missing_fields_default_to_empty_strings(self):
        """Entries with missing fields produce empty fallback values."""
        from app.tools.crawler import fetch_news

        urls = ["https://a.com/rss"]
        # Minimal entry — no title, no link, no summary, no published_parsed
        minimal = {}
        with patch("app.tools.crawler.feedparser") as mock_fp:
            mock_fp.parse.return_value = _make_parsed([minimal])
            result = await fetch_news(urls, limit=10)

        assert len(result) == 1
        item = result[0]
        assert item["title"] == ""
        assert item["link"] == ""
        assert item["summary"] == ""
        assert item["published_at"] == ""

    async def test_later_feeds_not_skipped_when_early_feed_has_many(self):
        """All RSS feeds participate even if earlier ones have enough entries."""
        from app.tools.crawler import fetch_news

        urls = ["https://a.com/rss", "https://b.com/rss"]
        with patch("app.tools.crawler.feedparser") as mock_fp:
            def _parse(url):
                if "a.com" in url:
                    return _make_parsed([
                        _make_entry(f"A{i}", f"https://a.com/{i}", f"sum{i}",
                                    (2026, 5, 10 + i))
                        for i in range(15)
                    ])
                return _make_parsed([
                    _make_entry("FromB", "https://b.com/1", "summary b",
                                (2026, 5, 25))
                ])

            mock_fp.parse.side_effect = _parse
            result = await fetch_news(urls, limit=10)

        assert mock_fp.parse.call_count == 2
        # Feed B was processed
        b_items = [r for r in result if r["link"] == "https://b.com/1"]
        assert len(b_items) == 1
        assert b_items[0]["title"] == "FromB"

    async def test_sorted_by_published_at_desc(self):
        """Results are sorted by published_at descending after collection."""
        from app.tools.crawler import fetch_news

        urls = ["https://a.com/rss"]
        entries = [
            _make_entry("Old", "https://a.com/old", "old", (2026, 5, 10)),
            _make_entry("New", "https://a.com/new", "new", (2026, 5, 20)),
            _make_entry("Mid", "https://a.com/mid", "mid", (2026, 5, 15)),
        ]
        with patch("app.tools.crawler.feedparser") as mock_fp:
            mock_fp.parse.return_value = _make_parsed(entries)
            result = await fetch_news(urls, limit=10)

        dates = [r["published_at"] for r in result]
        assert dates == ["2026-05-20", "2026-05-15", "2026-05-10"]
