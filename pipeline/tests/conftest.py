from __future__ import annotations

from pathlib import Path

import pytest

from sermon_pipeline.config import SOURCES_DIR, SourceConfig, load_source
from sermon_pipeline.scrapers.allsouls import _PAGE_FIELD as PAGE_FIELD

FIXTURES = Path(__file__).parent / "fixtures"
AS = FIXTURES / "all-souls-langham-place"

ALL_SOULS_PAGES = {
    "https://www.allsouls.org/Media/rss.xml": AS / "rss.xml",
    "https://www.allsouls.org/Media/AllMedia.aspx": AS / "allmedia.html",
    "https://www.allsouls.org/Groups/471841/1_Kings.aspx": AS / "group_1_kings.html",
    "https://www.allsouls.org/Groups/468891/No_Favourites.aspx": AS / "group_no_favourites.html",
}


class FakeFetcher:
    """Serves fixtures by URL; unknown URLs return an empty page. Records every call."""

    def __init__(self, pages: dict[str, Path | str] | None = None, fail: set[str] = frozenset()) -> None:
        self.pages = dict(ALL_SOULS_PAGES if pages is None else pages)
        self.fail = set(fail)
        self.calls: list[str] = []
        self.posts: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str) -> str:
        self.calls.append(url)
        if url in self.fail:
            raise OSError(f"simulated network failure: {url}")
        page = self.pages.get(url)
        if page is None:
            return "<html><body></body></html>"
        return page.read_text(encoding="utf-8") if isinstance(page, Path) else page

    def post(self, url: str, form: dict[str, str]) -> str:
        """Postback pages are served by `url#page=N` keys."""
        self.posts.append((url, dict(form)))
        return self.get(f"{url}#page={form.get(PAGE_FIELD, '?')}")


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher()


@pytest.fixture
def all_souls() -> SourceConfig:
    return load_source(SOURCES_DIR / "all-souls-langham-place.toml")
