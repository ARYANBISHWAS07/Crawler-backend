# crawler/run_spider.py
import sys
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from crawler.spiders.crawler_spider import CrawlerSpider
from app.job_store import JOB_STORE, JobStatus

def run(job_id, urls, depth):
    JOB_STORE[job_id]["status"] = JobStatus.running
    try:
        process = CrawlerProcess(get_project_settings())
        process.crawl(
            CrawlerSpider,
            urls=urls,
            max_depth=depth,
            job_id=job_id
        )
        process.start()
        JOB_STORE[job_id]["status"] = JobStatus.completed
    except Exception:
        JOB_STORE[job_id]["status"] = JobStatus.failed

if __name__ == "__main__":
    job_id = sys.argv[1]
    urls = sys.argv[2].split(",")
    depth = int(sys.argv[3])
    run(job_id, urls, depth)
