# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter


class CrawlerPipeline:
    def process_item(self, item, spider):
        return item


import uuid
from sentence_transformers import SentenceTransformer
from qdrant_client.models import PointStruct
from app.vector_store import client, ensure_collection, COLLECTION_NAME

class QdrantPipeline:
    def open_spider(self, spider):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        ensure_collection(vector_size=384)

    def process_item(self, item, spider):
        vector = self.model.encode(item["text"]).tolist()

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "url": item["url"],
                "job_id": item["job_id"]
            }
        )

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[point]
        )

        return item
