# crawler/run_spider.py
import sys
import os
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from crawler.crawler.spiders.crawler_spider import CrawlerSpider

def run(job_id, urls, depth):
    from datetime import datetime
    import asyncio
    from app.job_store import create_job, get_job, update_job
    from scrapy import signals

    job_data = None
    try:
        job_data = asyncio.run(get_job(job_id))
    except Exception as e:
        print(f"Failed to check job in DB: {e}")
    if not job_data:
        job_data = {
            "id": job_id,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "urls": urls,
            "depth": depth
        }
        try:
            asyncio.run(create_job(job_data))
        except Exception as e:
            print(f"Failed to create job in DB: {e}")
    # Update job status to running
    try:
        asyncio.run(update_job(job_id, {"status": "running"}))
    except Exception as e:
        print(f"Failed to update job status to running: {e}")

    # Collect crawled items
    crawled_pages = []
    def item_scraped(item, response, spider):
        crawled_pages.append(dict(item))

    try:
        process = CrawlerProcess(get_project_settings())
        # Create the crawler and connect the signal
        crawler = process.create_crawler(CrawlerSpider)
        crawler.signals.connect(item_scraped, signal=signals.item_scraped)
        process.crawl(
            crawler,
            urls=urls,
            max_depth=depth,
            job_id=job_id
        )
        process.start()
        # After crawling, update the job with crawled pages
        try:
            asyncio.run(update_job(job_id, {"status": "completed", "pages": crawled_pages}))
        except Exception as e:
            print(f"Failed to update job status to completed: {e}")
    except Exception as e:
        # Update job status to failed
        print(f"Crawler error: {e}")
        try:
            asyncio.run(update_job(job_id, {"status": "failed", "error": str(e)}))
        except Exception as e:
            print(f"Failed to update job status to failed: {e}")

if __name__ == "__main__":
    job_id = sys.argv[1]
    urls = sys.argv[2].split(",")
    depth = int(sys.argv[3])
    run(job_id, urls, depth)
