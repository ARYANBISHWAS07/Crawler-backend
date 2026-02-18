import asyncio
from urllib.parse import urlparse
from typing import Optional, Callable, List, Dict, Any
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    DefaultMarkdownGenerator,
    PruningContentFilter,
)

from crawl4ai.deep_crawling import DFSDeepCrawlStrategy, BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import FilterChain, DomainFilter




async def run_crawl(
    start_url: str, 
    max_pages: int = 0, 
    max_depth: int = 10,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[Dict[str, Any]]:
    """
    Crawl a website using the new crawl4ai architecture.
    Saves full content of each page with real-time progress updates.
    
    Args:
        start_url: The starting URL to crawl
        max_pages: Maximum number of pages to crawl (0 = unlimited)
        max_depth: Maximum depth of crawling from start URL
        progress_callback: Optional callback for progress (current, total, message)
    
    Returns:
        List of dictionaries containing url, title, and content for each page
    """
    # Browser configuration (global browser settings)
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
    )
    
    # Extract domain from URL
    parsed_url = urlparse(start_url)
    domain = parsed_url.netloc
    
    # Create filter chain with domain filter
    filter_chain = FilterChain([
        DomainFilter(allowed_domains=[domain])
    ])
    
    # Set max_pages - if 0, use a very high number for "unlimited"
    effective_max_pages = max_pages if max_pages > 0 else 10000
    
    # Crawler run configuration with deep crawl strategy
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        deep_crawl_strategy=BFSDeepCrawlStrategy(
            max_depth=max_depth,
            max_pages=effective_max_pages,
            include_external=False,
            filter_chain=filter_chain,
        ),
        verbose=False,
    )

    results = []
    
    if progress_callback:
        progress_callback(0, effective_max_pages, f"Starting crawl of {domain}...")
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # arun now returns a list of CrawlResult when using deep_crawl_strategy
        crawl_results = await crawler.arun(
            url=start_url,
            config=run_config
        )
        
        # Handle both single result and list of results
        if not isinstance(crawl_results, list):
            crawl_results = [crawl_results]
        
        total_pages = len(crawl_results)
        
        for idx, page in enumerate(crawl_results):
            if progress_callback:
                progress_callback(
                    idx + 1, 
                    total_pages, 
                    f"Processing page {idx + 1}/{total_pages}: {page.url[:60]}..."
                )
            
            if page.success:
                markdown_content = ""
                if page.markdown:
                    if hasattr(page.markdown, 'raw_markdown'):
                        markdown_content = page.markdown.raw_markdown
                    elif hasattr(page.markdown, 'fit_markdown'):
                        markdown_content = page.markdown.fit_markdown
                    else:
                        markdown_content = str(page.markdown)
                
                if not markdown_content and page.html:
                    markdown_content = page.html
                
                if not markdown_content and hasattr(page, 'cleaned_html') and page.cleaned_html:
                    markdown_content = page.cleaned_html
                
                results.append({
                    "url": page.url,
                    "title": page.metadata.get("title", "") if page.metadata else "",
                    "content": markdown_content  # Full content, no truncation
                })
                
                print(f"Crawled: {page.url} ({len(markdown_content)} chars)")
    
    if progress_callback:
        progress_callback(len(results), len(results), f"Crawl complete! Found {len(results)} pages.")

    print(f"Total pages crawled: {len(results)}")
    return results


def crawl_sync(
    url: str, 
    max_pages: int = 0, 
    max_depth: int = 10,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[Dict[str, Any]]:
    """Synchronous wrapper for run_crawl with optional progress callback."""
    return asyncio.run(run_crawl(url, max_pages, max_depth, progress_callback))

async def crawl_manual(
    start_url: str,
    max_depth: int = 2,
    max_pages: int = 10,
):
    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(
            threshold=0.5,
            threshold_type="fixed",
        )
    )
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        markdown_generator=md_generator,
        verbose=False,
    )

    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        results = await crawler.arun(
            url=start_url,
            config=run_config
        )
        print(f"Crawled URL: {results.url}")
        print(f"Content length: {len(results.markdown)}")
        print(f"Content preview: {results.markdown[:200]}...")
        # print(f"Length: {len(results.markdown)}")
        print(results.markdown)
        return {
            "length": len(results.markdown),
            "url": results.url,
            "content": results.markdown,  
        }
    



async def crawl_site(
    start_url: str,
    domain: str,
    max_depth: int = 8,
    max_pages: int = 1000,
):
    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(
            threshold=0.5,
            threshold_type="fixed",
        )
    )

    filter_chain = FilterChain([
        # ResolveRelativeURLFilter(start_url),
        # NormalizeURLFilter(start_url),
        DomainFilter(allowed_domains=[domain]),
        # URLPatternFilter(deny_patterns=[r"\?.*", r"#.*"]),
    ])

    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        markdown_generator=md_generator,
        auto_url_join=True,
        deep_crawl_strategy=DFSDeepCrawlStrategy(
            max_depth=max_depth,
            max_pages=max_pages,
            include_external=False,
            filter_chain=filter_chain,
        ),
        verbose=False,
    )

    browser_config = BrowserConfig(
        headless=True,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        crawl_results = await crawler.arun(
            url=start_url,
            config=run_config
        )

    pages = []
    for page in crawl_results if isinstance(crawl_results, list) else [crawl_results]:
        if page.success and page.markdown:
            content = (
                page.markdown.raw_markdown
                if hasattr(page.markdown, "raw_markdown")
                else page.markdown.fit_markdown
            )
            pages.append({
                "url": page.url,
                "title": page.metadata.get("title", ""),
                "content": content,
                "length": len(content),
            })

    return {
        "pages_crawled": len(pages),
        "pages": pages,
    }

