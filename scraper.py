"""Lokalny web scraper oparty na Crawl4AI.

Dziala w 100% na Twoim komputerze - bez API keys, bez tokenow,
bez zadnych platnych uslug. Uzywa przegladarki Chromium przez Playwright.

Wymaga:
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
    """Wynik scrapowania strony."""
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
            return f"[Blad: {self.error_msg}]"
        return self.markdown[:500] + "..." if len(self.markdown) > 500 else self.markdown

    @property
    def summary(self) -> str:
        return (
            f"URL: {self.url}\n"
            f"Tytul: {self.title}\n"
            f"Rozmiar: {len(self.markdown)} znakow\n"
            f"Linki: {len(self.links)}\n"
            f"Czas: {self.elapsed_sec:.1f}s"
        )


@dataclass
class CrawlResult:
    """Wynik crawlowania wielu stron."""
    start_url: str
    pages: list[ScrapeResult] = field(default_factory=list)
    is_error: bool = False
    error_msg: str = ""

    def __str__(self):
        if self.is_error:
            return f"[Blad: {self.error_msg}]"
        return f"Crawl {self.start_url}: {len(self.pages)} stron"


def _get_event_loop():
    """Pobierz lub stworz event loop (bezpieczne z tkinter)."""
    try:
        loop = asyncio.get_running_loop()
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


class Scraper:
    """Lokalny web scraper - bez API keys, dziala na Twoim komputerze.

    Przyklad:
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
        """Zawsze True - nie wymaga konfiguracji."""
        return True

    def _emit(self, msg: str):
        if self.on_status:
            self.on_status(msg)

    # ------------------------------------------------------------------ #
    #  Scrape - pojedyncza strona
    # ------------------------------------------------------------------ #

    def scrape(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30000,
    ) -> ScrapeResult:
        """Scrapuj pojedyncza strone. Zwraca markdown."""
        self._emit(f"Scrapuje {url}...")
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
                    error_msg=result.error_message or "Nieznany blad",
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
    #  Multi-scrape - wiele stron
    # ------------------------------------------------------------------ #

    def scrape_many(
        self,
        urls: list[str],
        timeout: int = 30000,
    ) -> list[ScrapeResult]:
        """Scrapuj wiele stron na raz (rownolegle w jednej sesji przegladarki)."""
        self._emit(f"Scrapuje {len(urls)} stron...")
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
                        error_msg=r.error_message or "Blad",
                    ))
            return scrape_results
        except Exception as e:
            return [ScrapeResult(url=u, is_error=True, error_msg=str(e)) for u in urls]

    # ------------------------------------------------------------------ #
    #  Map - odkryj linki na stronie
    # ------------------------------------------------------------------ #

    def map_site(
        self,
        url: str,
        max_depth: int = 1,
    ) -> list[str]:
        """Odkryj wszystkie linki na stronie (do max_depth poziomu)."""
        self._emit(f"Mapuje linki na {url}...")

        visited = set()
        to_visit = [url]
        domain = urlparse(url).netloc
        all_urls = []

        for depth in range(max_depth + 1):
            if not to_visit:
                break
            self._emit(f"  Glebokosc {depth}: {len(to_visit)} stron...")
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
    #  Async wrappers (do GUI)
    # ------------------------------------------------------------------ #

    def scrape_async(self, url: str, callback: Callable[[ScrapeResult], None], **kwargs):
        """Scrapuj asynchronicznie. Wynik przez callback."""
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
