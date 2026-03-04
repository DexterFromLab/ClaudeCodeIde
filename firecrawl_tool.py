"""Wrapper Firecrawl do integracji z Claude Code IDE.

Opakowuje firecrawl-py SDK w prosty interfejs do scrapowania,
przeszukiwania i mapowania stron www.

Wymaga:
    pip install firecrawl-py
    + klucz API: https://firecrawl.dev/app/api-keys
"""

import json
import os
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class ScrapeResult:
    """Wynik scrapowania strony."""
    url: str
    markdown: str = ""
    title: str = ""
    links: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    is_error: bool = False
    error_msg: str = ""

    def __str__(self):
        if self.is_error:
            return f"[Blad: {self.error_msg}]"
        return self.markdown[:500] + "..." if len(self.markdown) > 500 else self.markdown


@dataclass
class SearchResult:
    """Wynik wyszukiwania."""
    query: str
    results: list[dict] = field(default_factory=list)
    is_error: bool = False
    error_msg: str = ""

    def __str__(self):
        if self.is_error:
            return f"[Blad: {self.error_msg}]"
        lines = [f"Wyniki dla: {self.query}\n"]
        for i, r in enumerate(self.results, 1):
            lines.append(f"{i}. {r.get('title', '?')}")
            lines.append(f"   {r.get('url', '')}")
            desc = r.get("description", "")
            if desc:
                lines.append(f"   {desc[:120]}")
            lines.append("")
        return "\n".join(lines)


@dataclass
class MapResult:
    """Wynik mapowania URL-i strony."""
    url: str
    urls: list[str] = field(default_factory=list)
    is_error: bool = False
    error_msg: str = ""

    def __str__(self):
        if self.is_error:
            return f"[Blad: {self.error_msg}]"
        return f"Znaleziono {len(self.urls)} URL-i na {self.url}"


class Firecrawl:
    """Prosty interfejs do Firecrawl API.

    Przyklad:
        fc = Firecrawl(api_key="fc-...")
        page = fc.scrape("https://example.com")
        print(page.markdown)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ):
        self._api_key = api_key or os.environ.get("FIRECRAWL_API_KEY", "")
        self.on_status = on_status
        self._app = None
        self._busy = False

    @property
    def busy(self):
        return self._busy

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def set_api_key(self, key: str):
        self._api_key = key
        self._app = None  # force reinit

    def _get_app(self):
        if not self._api_key:
            raise ValueError(
                "Brak klucza API Firecrawl. Ustaw FIRECRAWL_API_KEY lub podaj api_key."
            )
        if self._app is None:
            from firecrawl import FirecrawlApp
            self._app = FirecrawlApp(api_key=self._api_key)
        return self._app

    def _emit_status(self, msg: str):
        if self.on_status:
            self.on_status(msg)

    # ------------------------------------------------------------------ #
    #  Scrape
    # ------------------------------------------------------------------ #

    def scrape(
        self,
        url: str,
        only_main_content: bool = True,
        wait_for: Optional[int] = None,
    ) -> ScrapeResult:
        """Scrapuj pojedyncza strone. Zwraca markdown."""
        self._emit_status(f"Scrapuje {url}...")
        try:
            app = self._get_app()
            kwargs = {"only_main_content": only_main_content}
            if wait_for:
                kwargs["wait_for"] = wait_for
            doc = app.scrape(url, **kwargs)
            return ScrapeResult(
                url=url,
                markdown=doc.markdown or "",
                title=(doc.metadata or {}).get("title", ""),
                links=[l.get("url", "") for l in (doc.links or [])] if hasattr(doc, "links") and doc.links else [],
                metadata=doc.metadata or {},
            )
        except Exception as e:
            return ScrapeResult(url=url, is_error=True, error_msg=str(e))

    # ------------------------------------------------------------------ #
    #  Search
    # ------------------------------------------------------------------ #

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> SearchResult:
        """Wyszukaj w internecie. Zwraca liste wynikow."""
        self._emit_status(f"Szukam: {query}...")
        try:
            app = self._get_app()
            data = app.search(query, limit=limit)
            results = []
            items = data.data if hasattr(data, "data") else (data if isinstance(data, list) else [])
            for item in items:
                if hasattr(item, "title"):
                    results.append({
                        "title": item.title or "",
                        "url": item.url or "",
                        "description": item.description or "" if hasattr(item, "description") else "",
                    })
                elif isinstance(item, dict):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "description": item.get("description", ""),
                    })
            return SearchResult(query=query, results=results)
        except Exception as e:
            return SearchResult(query=query, is_error=True, error_msg=str(e))

    # ------------------------------------------------------------------ #
    #  Map
    # ------------------------------------------------------------------ #

    def map_site(
        self,
        url: str,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> MapResult:
        """Odkryj wszystkie URL-e na stronie."""
        self._emit_status(f"Mapuje {url}...")
        try:
            app = self._get_app()
            kwargs = {"limit": limit}
            if search:
                kwargs["search"] = search
            data = app.map(url, **kwargs)
            urls = []
            if hasattr(data, "links"):
                urls = data.links or []
            elif isinstance(data, list):
                urls = data
            return MapResult(url=url, urls=urls)
        except Exception as e:
            return MapResult(url=url, is_error=True, error_msg=str(e))

    # ------------------------------------------------------------------ #
    #  Crawl (synchroniczny - czeka na wynik)
    # ------------------------------------------------------------------ #

    def crawl(
        self,
        url: str,
        limit: int = 10,
        max_depth: int = 2,
    ) -> list[ScrapeResult]:
        """Crawluj cala strone (do limit podstron). Zwraca liste ScrapeResult."""
        self._emit_status(f"Crawluje {url} (max {limit} stron)...")
        try:
            app = self._get_app()
            job = app.crawl(url, limit=limit, max_discovery_depth=max_depth)
            results = []
            pages = job.data if hasattr(job, "data") else []
            for page in pages:
                results.append(ScrapeResult(
                    url=page.url if hasattr(page, "url") else url,
                    markdown=page.markdown or "" if hasattr(page, "markdown") else "",
                    title=(page.metadata or {}).get("title", "") if hasattr(page, "metadata") else "",
                    metadata=page.metadata or {} if hasattr(page, "metadata") else {},
                ))
            return results
        except Exception as e:
            return [ScrapeResult(url=url, is_error=True, error_msg=str(e))]

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

    def search_async(self, query: str, callback: Callable[[SearchResult], None], **kwargs):
        """Szukaj asynchronicznie. Wynik przez callback."""
        if self._busy:
            return
        self._busy = True

        def worker():
            try:
                result = self.search(query, **kwargs)
                callback(result)
            finally:
                self._busy = False

        threading.Thread(target=worker, daemon=True).start()
