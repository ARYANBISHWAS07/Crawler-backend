from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig


class _HTMLToTextParser(HTMLParser):
    """Minimal HTML-to-text fallback when markdown/text output is unavailable."""

    _BLOCK_TAGS = {
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "main",
        "p",
        "pre",
        "section",
        "td",
        "th",
        "tr",
    }

    _SKIP_TAGS = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower_tag = tag.lower()
        if lower_tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if lower_tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if lower_tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if lower_tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if data:
            self._parts.append(data)

    def get_text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self._parts).splitlines() if line.strip())


def _extract_text_from_result(result: Any) -> str:
    """Best-effort readable text extraction across crawl4ai versions."""
    extracted = getattr(result, "extracted_content", None)
    if isinstance(extracted, str) and extracted.strip():
        return extracted.strip()

    markdown = getattr(result, "markdown", None)
    if markdown:
        markdown_text = str(markdown).strip()
        if markdown_text:
            return markdown_text

    cleaned_html = getattr(result, "cleaned_html", None) or getattr(result, "html", None)
    if isinstance(cleaned_html, str) and cleaned_html.strip():
        parser = _HTMLToTextParser()
        parser.feed(cleaned_html)
        parser.close()
        return unescape(parser.get_text()).strip()

    return ""


async def scrape_single_page(url: str) -> dict:
    """
    Scrapes ONLY the given page and detects the website.
    No crawling across links.
    """

    parsed = urlparse(url)
    domain = parsed.netloc or parsed.hostname or ""
    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(only_text=True)
    crawler = AsyncWebCrawler(config=browser_config)

    async with crawler:
        result = await crawler.arun(url=url, config=run_config)

        if not getattr(result, "success", False):
            error_message = getattr(result, "error_message", None) or "Failed to scrape page"
            raise RuntimeError(error_message)

        content = _extract_text_from_result(result)
        if not content:
            raise RuntimeError("Failed to extract page content")

        return {
            "domain": domain,                       
            "page_url": getattr(result, "url", url),  
            "content": content,
        }
