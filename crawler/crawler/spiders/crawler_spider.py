import scrapy
from urllib.parse import urlparse

class CrawlerSpider(scrapy.Spider):
    name = "crawler"

    def __init__(self, urls, max_depth=1, job_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = urls
        self.allowed_domains = [urlparse(u).netloc for u in urls]
        self.max_depth = int(max_depth)
        self.job_id = job_id

    def parse(self, response):
        depth = response.meta.get("depth", 0)

        text = " ".join(
            t.strip()
            for t in response.css("body *::text").getall()
            if t.strip()
        )

        yield {
            "url": response.url,
            "text": text[:5000],
            "job_id": self.job_id
        }

        if depth < self.max_depth:
            for link in response.css("a::attr(href)").getall():
                yield response.follow(link, callback=self.parse)
