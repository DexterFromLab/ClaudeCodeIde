"""Local web scraper based on Crawl4AI.

Runs 100% on your machine - no API keys, no tokens,
no paid services. Uses Chromium browser via Playwright.

Requirements:
    pip install crawl4ai
    crawl4ai-setup
"""

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse


@dataclass
class ScrapeResult:
    """Result of scraping a page."""
    url: str
    markdown: str = ""
    title: str = ""
    links: list[str] = field(default_factory=list)
    html: str = ""
    is_error: bool = False
    error_msg: str = ""
    elapsed_sec: float = 0.0

    def __str__(self):
        if self.is_error:
            return f"[Error: {self.error_msg}]"
        return self.markdown[:500] + "..." if len(self.markdown) > 500 else self.markdown

    @property
    def summary(self) -> str:
        return (
            f"URL: {self.url}\n"
            f"Title: {self.title}\n"
            f"Size: {len(self.markdown)} chars\n"
            f"Links: {len(self.links)}\n"
            f"Time: {self.elapsed_sec:.1f}s"
        )


@dataclass
class CrawlResult:
    """Result of crawling multiple pages."""
    start_url: str
    pages: list[ScrapeResult] = field(default_factory=list)
    is_error: bool = False
    error_msg: str = ""

    def __str__(self):
        if self.is_error:
            return f"[Error: {self.error_msg}]"
        return f"Crawl {self.start_url}: {len(self.pages)} pages"


def _get_event_loop():
    """Get or create event loop (safe with tkinter)."""
    try:
        loop = asyncio.get_running_loop()
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


class Scraper:
    """Local web scraper - no API keys, runs on your machine.

    Example:
        scraper = Scraper()
        page = scraper.scrape("https://example.com")
        print(page.markdown)
    """

    def __init__(
        self,
        on_status: Optional[Callable[[str], None]] = None,
        headless: bool = True,
    ):
        self.on_status = on_status
        self.headless = headless
        self._busy = False

    @property
    def busy(self):
        return self._busy

    @property
    def is_configured(self) -> bool:
        """Always True - no configuration required."""
        return True

    def _emit(self, msg: str):
        if self.on_status:
            self.on_status(msg)

    # ------------------------------------------------------------------ #
    #  Scrape - single page
    # ------------------------------------------------------------------ #

    def scrape(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30000,
    ) -> ScrapeResult:
        """Scrape a single page. Returns markdown."""
        self._emit(f"Scraping {url}...")
        import time
        t0 = time.time()

        async def _do():
            from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

            config_kwargs = {"page_timeout": timeout}
            if wait_for:
                config_kwargs["wait_until"] = "networkidle"

            config = CrawlerRunConfig(**config_kwargs)

            async with AsyncWebCrawler(headless=self.headless) as crawler:
                result = await crawler.arun(url=url, config=config)
                return result

        try:
            result = asyncio.run(_do())
            elapsed = time.time() - t0

            if not result.success:
                return ScrapeResult(
                    url=url,
                    is_error=True,
                    error_msg=result.error_message or "Unknown error",
                    elapsed_sec=elapsed,
                )

            links = []
            if hasattr(result, 'links') and result.links:
                for link_group in [result.links.get("internal", []), result.links.get("external", [])]:
                    for link in link_group:
                        href = link.get("href", "") if isinstance(link, dict) else str(link)
                        if href:
                            links.append(href)

            title = ""
            if hasattr(result, 'metadata') and result.metadata:
                title = result.metadata.get("title", "")

            return ScrapeResult(
                url=url,
                markdown=result.markdown or "",
                title=title,
                links=links,
                html=result.html or "",
                elapsed_sec=elapsed,
            )
        except Exception as e:
            return ScrapeResult(
                url=url,
                is_error=True,
                error_msg=str(e),
                elapsed_sec=time.time() - t0,
            )

    # ------------------------------------------------------------------ #
    #  Multi-scrape - multiple pages
    # ------------------------------------------------------------------ #

    def scrape_many(
        self,
        urls: list[str],
        timeout: int = 30000,
    ) -> list[ScrapeResult]:
        """Scrape multiple pages at once (parallel in a single browser session)."""
        self._emit(f"Scraping {len(urls)} pages...")
        import time
        t0 = time.time()

        async def _do():
            from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
            config = CrawlerRunConfig(page_timeout=timeout)

            async with AsyncWebCrawler(headless=self.headless) as crawler:
                results = await crawler.arun_many(urls=urls, config=config)
                return results

        try:
            raw_results = asyncio.run(_do())
            elapsed = time.time() - t0

            scrape_results = []
            for r in raw_results:
                if r.success:
                    title = ""
                    if hasattr(r, 'metadata') and r.metadata:
                        title = r.metadata.get("title", "")
                    scrape_results.append(ScrapeResult(
                        url=r.url,
                        markdown=r.markdown or "",
                        title=title,
                        elapsed_sec=elapsed / len(urls),
                    ))
                else:
                    scrape_results.append(ScrapeResult(
                        url=r.url,
                        is_error=True,
                        error_msg=r.error_message or "Error",
                    ))
            return scrape_results
        except Exception as e:
            return [ScrapeResult(url=u, is_error=True, error_msg=str(e)) for u in urls]

    # ------------------------------------------------------------------ #
    #  Map - discover links on a page
    # ------------------------------------------------------------------ #

    def map_site(
        self,
        url: str,
        max_depth: int = 1,
    ) -> list[str]:
        """Discover all links on a page (up to max_depth levels)."""
        self._emit(f"Mapping links on {url}...")

        visited = set()
        to_visit = [url]
        domain = urlparse(url).netloc
        all_urls = []

        for depth in range(max_depth + 1):
            if not to_visit:
                break
            self._emit(f"  Depth {depth}: {len(to_visit)} pages...")
            results = self.scrape_many(to_visit) if len(to_visit) > 1 else [self.scrape(to_visit[0])]

            next_level = []
            for r in results:
                visited.add(r.url)
                if r.url not in all_urls:
                    all_urls.append(r.url)
                if not r.is_error:
                    for link in r.links:
                        parsed = urlparse(link)
                        if parsed.netloc == domain and link not in visited:
                            next_level.append(link)
                            if link not in all_urls:
                                all_urls.append(link)
            to_visit = list(set(next_level) - visited)[:20]  # limit

        return all_urls

    # ------------------------------------------------------------------ #
    #  Async wrappers (for GUI)
    # ------------------------------------------------------------------ #

    def scrape_async(self, url: str, callback: Callable[[ScrapeResult], None], **kwargs):
        """Scrape asynchronously. Result via callback."""
        if self._busy:
            return
        self._busy = True

        def worker():
            try:
                result = self.scrape(url, **kwargs)
                callback(result)
            finally:
                self._busy = False

        threading.Thread(target=worker, daemon=True).start()
