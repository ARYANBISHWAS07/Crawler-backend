"""
Vector Store using LangChain with ChromaDB.
Handles document chunking, embedding, and semantic search.
"""
import chromadb
import hashlib
from typing import List, Dict, Any, Optional, Callable
import os
from dotenv import load_dotenv

load_dotenv()

# LangChain imports for text splitting
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings

# ChromaDB Cloud Configuration
CHROMA_API_KEY = os.getenv("CHROMA_API_KEY")
CHROMA_TENANT = os.getenv("CHROMA_TENANT")
CHROMA_DATABASE = os.getenv("CHROMA_DATABASE")

# Connect to Chroma Cloud
chroma_client = chromadb.CloudClient(
    api_key=CHROMA_API_KEY,
    tenant=CHROMA_TENANT,
    database=CHROMA_DATABASE
)

# Default collection
collection = chroma_client.get_or_create_collection(
    name="scraped_data",
    metadata={"hnsw:space": "cosine"}
)

# LangChain embeddings using HuggingFace
embeddings_model = HuggingFaceEmbeddings(
    model_name="all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)

# LangChain text splitter for chunking
# ChromaDB Cloud has 16KB limit, use 10KB chunks with overlap
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=10000,  # ~10KB chunks
    chunk_overlap=500,
    length_function=len,
    separators=["\n\n", "\n", ". ", "? ", "! ", " ", ""],
    is_separator_regex=False,
)


def chunk_text(text: str) -> List[str]:
    """
    Split text into chunks using LangChain's RecursiveCharacterTextSplitter.
    
    Args:
        text: The text to chunk
        
    Returns:
        List of text chunks
    """
    if not text or not text.strip():
        return []
    
    chunks = text_splitter.split_text(text)
    return [chunk for chunk in chunks if chunk.strip()]


def store_pages(
    pages: List[Dict[str, Any]], 
    collection_name: str = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> int:
    """
    Store crawled pages as embeddings in the vector database.
    Uses LangChain for chunking and embedding.
    
    Args:
        pages: List of dicts with 'url', 'title', 'content' keys
        collection_name: Optional custom collection name
        progress_callback: Optional callback for progress updates (current, total, message)
        
    Returns:
        Number of chunks stored
    """
    if not pages:
        return 0
    
    # Use custom collection if specified
    coll = collection
    if collection_name:
        coll = chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
    
    # Filter out duplicate URLs and empty content
    seen_urls = set()
    unique_pages = []
    for p in pages:
        if p['url'] not in seen_urls and p.get('content'):
            seen_urls.add(p['url'])
            unique_pages.append(p)
    
    if not unique_pages:
        return 0
    
    total_pages = len(unique_pages)
    
    # Chunk all pages and prepare for storage
    all_texts = []
    all_metadatas = []
    all_ids = []
    
    for page_idx, p in enumerate(unique_pages):
        content = p["content"]
        
        # Use LangChain text splitter for chunking
        chunks = chunk_text(content)
        
        if progress_callback:
            progress_callback(
                page_idx + 1, 
                total_pages, 
                f"Chunking page {page_idx + 1}/{total_pages}: {p['title'][:50]}..."
            )
        
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
                
            all_texts.append(chunk)
            all_metadatas.append({
                "url": p["url"],
                "title": p["title"],
                "chunk_index": i,
                "total_chunks": len(chunks)
            })
            # Unique ID per chunk
            chunk_id = f"doc_{hashlib.sha256((p['url'] + str(i)).encode()).hexdigest()[:16]}"
            all_ids.append(chunk_id)
    
    if not all_texts:
        return 0
    
    total_chunks = len(all_texts)
    
    if progress_callback:
        progress_callback(0, total_chunks, f"Generating embeddings for {total_chunks} chunks...")
    
    # Generate embeddings using LangChain HuggingFace embeddings
    # Process in batches to show progress
    batch_size = 50
    all_embeddings = []
    
    for i in range(0, len(all_texts), batch_size):
        end = min(i + batch_size, len(all_texts))
        batch_texts = all_texts[i:end]
        
        if progress_callback:
            progress_callback(
                end, 
                total_chunks, 
                f"Embedding chunks {i + 1}-{end} of {total_chunks}..."
            )
        
        batch_embeddings = embeddings_model.embed_documents(batch_texts)
        all_embeddings.extend(batch_embeddings)
    
    if progress_callback:
        progress_callback(0, total_chunks, f"Storing {total_chunks} chunks in vector database...")
    
    # Upsert in batches
    upsert_batch_size = 100
    for i in range(0, len(all_texts), upsert_batch_size):
        end = min(i + upsert_batch_size, len(all_texts))
        
        if progress_callback:
            progress_callback(
                end, 
                total_chunks, 
                f"Storing chunks {i + 1}-{end} of {total_chunks}..."
            )
        
        coll.upsert(
            documents=all_texts[i:end],
            embeddings=all_embeddings[i:end],
            metadatas=all_metadatas[i:end],
            ids=all_ids[i:end]
        )
    
    print(f"📦 Stored {len(all_texts)} chunks from {len(unique_pages)} pages")
    return len(all_texts)


def search(query: str, top_k: int = 5, collection_name: str = None) -> List[Dict[str, Any]]:
    """
    Search for relevant content based on semantic similarity.
    Uses LangChain embeddings for query encoding.
    
    Args:
        query: The user's question or search query
        top_k: Number of top results to return
        collection_name: Optional custom collection name
        
    Returns:
        List of relevant documents with their metadata and similarity scores
    """
    coll = collection
    if collection_name:
        coll = chroma_client.get_or_create_collection(name=collection_name)
    
    print(f"🔍 Searching for: {query} (top_k={top_k})")
    # Convert query to embedding using LangChain
    query_embedding = embeddings_model.embed_query(query)
    
    # Search for similar documents
    results = coll.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    
    # Format results
    formatted_results = []
    if results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            formatted_results.append({
                "content": doc,
                "url": results["metadatas"][0][i].get("url", ""),
                "title": results["metadatas"][0][i].get("title", ""),
                "similarity": 1 - results["distances"][0][i]  # Convert distance to similarity
            })
    
    return formatted_results


def get_context_for_question(query: str, top_k: int = 3, collection_name: str = None) -> str:
    """
    Get relevant context for answering a question.
    Formats the search results into a context string for LLM.
    
    Args:
        query: The user's question
        top_k: Number of relevant chunks to retrieve
        collection_name: Optional custom collection name
        
    Returns:
        Formatted context string with sources
    """
    results = search(query, top_k=top_k, collection_name=collection_name)
    
    if not results:
        return "No relevant information found."
    
    context_parts = []
    for i, result in enumerate(results, 1):
        content_preview = result['content'][:1500] + "..." if len(result['content']) > 1500 else result['content']
        context_parts.append(
            f"[Source {i}: {result['title']}]\n"
            f"URL: {result['url']}\n"
            f"Content: {content_preview}\n"
        )
    
    return "\n---\n".join(context_parts)


def clear_collection(collection_name: str = None):
    """Clear all documents from a collection."""
    name = collection_name or "scraped_data"
    chroma_client.delete_collection(name)
    chroma_client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def get_collection_stats(collection_name: str = None) -> Dict[str, Any]:
    """Get statistics about the collection."""
    coll = collection
    if collection_name:
        coll = chroma_client.get_or_create_collection(name=collection_name)
    
    return {
        "name": coll.name,
        "count": coll.count()
    }


def has_embeddings(collection_name: str = None) -> bool:
    """Check if a collection has any embeddings stored."""
    try:
        coll = collection
        if collection_name:
            coll = chroma_client.get_or_create_collection(name=collection_name)
        return coll.count() > 0
    except Exception:
        return False


def collection_exists(collection_name: str) -> bool:
    """Check if a collection exists and has content."""
    try:
        coll = chroma_client.get_or_create_collection(name=collection_name)
        return coll.count() > 0
    except Exception:
        return False


def get_collection_urls(collection_name: str = None, limit: int = 100) -> List[str]:
    """Get all unique URLs stored in a collection."""
    coll = collection
    if collection_name:
        coll = chroma_client.get_or_create_collection(name=collection_name)
    
    try:
        results = coll.get(limit=limit, include=["metadatas"])
        urls = set()
        if results["metadatas"]:
            for meta in results["metadatas"]:
                if meta and "url" in meta:
                    urls.add(meta["url"])
        return list(urls)
    except Exception:
        return []


def url_is_embedded(url: str, collection_name: str = None) -> bool:
    """Check if a specific URL has been embedded."""
    coll = collection
    if collection_name:
        coll = chroma_client.get_or_create_collection(name=collection_name)
    
    try:
        # Generate the same ID that would be used for this URL
        doc_id = f"doc_{hashlib.sha256(url.encode()).hexdigest()[:16]}"
        results = coll.get(ids=[doc_id])
        return len(results["ids"]) > 0
    except Exception:
        return False
