"""
Vector Store using LangChain with Qdrant.
Handles document chunking, embedding, and semantic search.
"""

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

import hashlib
from typing import List, Dict, Any, Optional, Callable
from dotenv import load_dotenv

load_dotenv()

# LangChain imports
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings


# QDRANT CONNECTION

client = QdrantClient(url="http://localhost:6333")

COLLECTION_NAME = "scraped_data"
VECTOR_SIZE = 384 



# COLLECTION SETUP

def ensure_collection(name: str):
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )


ensure_collection(COLLECTION_NAME)


# EMBEDDINGS

embeddings_model = HuggingFaceEmbeddings(
    model_name="all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)



# TEXT SPLITTER

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=10000,
    chunk_overlap=500,
    length_function=len,
    separators=["\n\n", "\n", ". ", "? ", "! ", " ", ""],
    is_separator_regex=False,
)


def chunk_text(text: str) -> List[str]:
    if not text or not text.strip():
        return []
    return [c for c in text_splitter.split_text(text) if c.strip()]





def store_pages(
    pages: List[Dict[str, Any]],
    collection_name: str = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> int:

    if not pages:
        return 0

    name = collection_name or COLLECTION_NAME
    ensure_collection(name)

    seen_urls = set()
    unique_pages = []
    for p in pages:
        if p.get("url") and p["url"] not in seen_urls and p.get("content"):
            seen_urls.add(p["url"])
            unique_pages.append(p)

    if not unique_pages:
        return 0

    total_pages = len(unique_pages)
    total_chunks = 0
    points: List[PointStruct] = []

    for page_idx, p in enumerate(unique_pages):
        chunks = chunk_text(p["content"])

        if progress_callback:
            progress_callback(
                page_idx + 1,
                total_pages,
                f"Chunking page {page_idx + 1}/{total_pages}: {p['title'][:50]}...",
            )

        vectors = embeddings_model.embed_documents(chunks)

        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            chunk_id = hashlib.sha256(
                f"{p['url']}_{i}".encode()
            ).hexdigest()

            points.append(
                PointStruct(
                    id=chunk_id,
                    vector=vector,
                    payload={
                        "url": p["url"],
                        "title": p["title"],
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "content": chunk,
                    },
                )
            )

        total_chunks += len(chunks)

    if not points:
        return 0

    if progress_callback:
        progress_callback(0, total_chunks, f"Storing {total_chunks} chunks...")

    client.upsert(
        collection_name=name,
        points=points,
    )

    return total_chunks



# SEARCH

def search(
    query: str,
    top_k: int = 5,
    collection_name: str = None,
) -> List[Dict[str, Any]]:

    name = collection_name or COLLECTION_NAME

    query_embedding = embeddings_model.embed_query(query)

    results = client.search(
        collection_name=name,
        query_vector=query_embedding,
        limit=top_k,
        with_payload=True,
    )

    formatted_results = []
    for hit in results:
        formatted_results.append(
            {
                "content": hit.payload.get("content", ""),
                "url": hit.payload.get("url", ""),
                "title": hit.payload.get("title", ""),
                "similarity": hit.score,
            }
        )

    return formatted_results


# CONTEXT BUILDER

def get_context_for_question(
    query: str,
    top_k: int = 3,
    collection_name: str = None,
) -> str:

    results = search(query, top_k, collection_name)

    if not results:
        return "No relevant information found."

    context_parts = []
    for i, result in enumerate(results, 1):
        content = result["content"]
        preview = content[:1500] + "..." if len(content) > 1500 else content

        context_parts.append(
            f"[Source {i}: {result['title']}]\n"
            f"URL: {result['url']}\n"
            f"Content: {preview}\n"
        )

    return "\n---\n".join(context_parts)



# COLLECTION UTILITIES

def clear_collection(collection_name: str = None):
    name = collection_name or COLLECTION_NAME
    client.delete_collection(name)
    ensure_collection(name)


def get_collection_stats(collection_name: str = None) -> Dict[str, Any]:
    name = collection_name or COLLECTION_NAME
    info = client.get_collection(name)
    return {
        "name": name,
        "points": info.points_count,
        "vectors": info.vectors_count,
    }


def has_embeddings(collection_name: str = None) -> bool:
    name = collection_name or COLLECTION_NAME
    try:
        info = client.get_collection(name)
        return info.points_count > 0
    except Exception:
        return False


def collection_exists(collection_name: str) -> bool:
    try:
        info = client.get_collection(collection_name)
        return info.points_count > 0
    except Exception:
        return False


def get_collection_urls(
    collection_name: str = None,
    limit: int = 100,
) -> List[str]:

    name = collection_name or COLLECTION_NAME
    urls = set()

    results = client.scroll(
        collection_name=name,
        limit=limit,
        with_payload=True,
    )

    for point in results[0]:
        payload = point.payload or {}
        if "url" in payload:
            urls.add(payload["url"])

    return list(urls)


def url_is_embedded(url: str, collection_name: str = None) -> bool:
    name = collection_name or COLLECTION_NAME

    results = client.scroll(
        collection_name=name,
        with_payload=True,
        limit=1,
        scroll_filter={
            "must": [
                {
                    "key": "url",
                    "match": {"value": url},
                }
            ]
        },
    )

    return len(results[0]) > 0
