import asyncio
from urllib.parse import urlparse
from typing import Optional, Callable, List, Dict, Any
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
)
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
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
                # Get the full markdown content - no truncation
                markdown_content = ""
                if page.markdown:
                    # markdown is now an object with raw_markdown property
                    if hasattr(page.markdown, 'raw_markdown'):
                        markdown_content = page.markdown.raw_markdown
                    elif hasattr(page.markdown, 'fit_markdown'):
                        # fit_markdown contains cleaned/formatted content
                        markdown_content = page.markdown.fit_markdown
                    else:
                        markdown_content = str(page.markdown)
                
                # Also try to get HTML content if markdown is empty
                if not markdown_content and page.html:
                    markdown_content = page.html
                
                # Get cleaned HTML content as fallback
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
