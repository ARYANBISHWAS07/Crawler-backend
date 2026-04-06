from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict
import math
import re

GENERIC_SOURCE_PATTERNS = [
    r"robots\.txt",
    r"/about\b",
    r"/about-us\b",
    r"/privacy\b",
    r"/terms\b",
    r"/home\b",
    r"wikipedia:about",
    r"wikipedia, the free encyclopedia",
]


def _normalize_mcq_question(raw_question: dict, source_doc: dict) -> Optional[dict]:
    if not isinstance(raw_question, dict):
        return None

    question_text = str(raw_question.get("question", "")).strip()
    options = raw_question.get("options")
    correct_option = str(raw_question.get("correct_option", "")).strip().upper()
    explanation = str(raw_question.get("explanation", "")).strip()

    if not question_text or not isinstance(options, dict):
        return None

    normalized_options: Dict[str, str] = {}
    for key in ("A", "B", "C", "D"):
        value = str(options.get(key, "")).strip()
        if not value:
            return None
        normalized_options[key] = value

    if correct_option not in {"A", "B", "C", "D"}:
        return None

    source_id = str(source_doc.get("id", ""))
    raw_id = str(raw_question.get("id", "")).strip() or question_text[:32]
    quiz_question_id = f"{source_id}:{raw_id}"

    return {
        "id": quiz_question_id,
        "question": question_text,
        "options": normalized_options,
        "correct_option": correct_option,
        "explanation": explanation,
        "metadata": source_doc.get("metadata", {}),
        "chunk_excerpt": str(source_doc.get("chunk_excerpt", "")).strip(),
    }


def _is_generic_source(question: dict) -> bool:
    metadata = question.get("metadata", {}) or {}
    url = str(metadata.get("url", "")).strip().lower()
    title = str(metadata.get("title", "")).strip().lower()
    haystack = f"{url} {title}"
    return any(re.search(pattern, haystack) for pattern in GENERIC_SOURCE_PATTERNS)


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _semantic_score(focus_query: str, question: dict) -> float:
    if not focus_query.strip():
        return 0.0

    from app.vector_store import embeddings_model

    metadata = question.get("metadata", {}) or {}
    url = str(metadata.get("url", "")).strip()
    title = str(metadata.get("title", "")).strip()
    chunk_excerpt = str(question.get("chunk_excerpt", "")).strip()
    question_text = str(question.get("question", "")).strip()
    text = "\n".join(part for part in [title, url, chunk_excerpt, question_text] if part)
    if not text:
        return 0.0

    query_vec = embeddings_model.embed_query(focus_query)
    text_vec = embeddings_model.embed_query(text)
    return _cosine_similarity(query_vec, text_vec)


def _apply_per_url_cap(questions: List[dict], max_questions_per_url: int) -> List[dict]:
    per_url_count = defaultdict(int)
    result = []
    for q in questions:
        url = str((q.get("metadata", {}) or {}).get("url", "")).strip() or "__no_url__"
        if per_url_count[url] >= max_questions_per_url:
            continue
        per_url_count[url] += 1
        result.append(q)
    return result


def _distinct_url_count(questions: List[dict]) -> int:
    urls = set()
    for q in questions:
        url = str((q.get("metadata", {}) or {}).get("url", "")).strip()
        if url:
            urls.add(url)
    return len(urls)


def filter_questions_by_scope(
    question_bank: List[dict],
    scope_mode: str,
    focus_query: Optional[str],
    collection_topic: Optional[str],
    min_semantic_score: float,
    max_questions_per_url: int,
    min_distinct_urls: int,
) -> List[dict]:
    """
    Scope-aware filtering and diversity controls for quiz question selection.
    """
    cleaned = [q for q in question_bank if not _is_generic_source(q)]

    if scope_mode == "focused":
        if not focus_query or not focus_query.strip():
            return []
        scored = []
        for q in cleaned:
            score = _semantic_score(focus_query, q)
            if score >= min_semantic_score:
                q_copy = dict(q)
                q_copy["semantic_score"] = score
                scored.append(q_copy)
        scored.sort(key=lambda x: x.get("semantic_score", 0.0), reverse=True)
        return _apply_per_url_cap(scored, max_questions_per_url)

    # broad mode: keep overall topic relevance using collection topic/query
    broad_topic = (focus_query or collection_topic or "").strip()
    if broad_topic:
        scored_broad = []
        for q in cleaned:
            score = _semantic_score(broad_topic, q)
            if score >= min_semantic_score:
                q_copy = dict(q)
                q_copy["semantic_score"] = score
                scored_broad.append(q_copy)
        if scored_broad:
            cleaned = scored_broad

    limited = _apply_per_url_cap(cleaned, max_questions_per_url)
    if _distinct_url_count(limited) < min_distinct_urls:
        # Relax per-url cap when collection has low URL diversity.
        return cleaned
    return limited


def filter_core_topic_with_labels(question_bank: List[dict], labels: Dict[str, str]) -> List[dict]:
    """
    Keep only questions classified as core_topic.
    """
    result = []
    for q in question_bank:
        label = (labels.get(q.get("id", ""), "") or "").strip().lower()
        if label == "core_topic":
            result.append(q)
    return result


async def get_collection_mcq_bank(collection_id: str) -> List[dict]:
    from app.database import get_collection

    chunk_collection = get_collection("chunk_question")
    cursor = chunk_collection.find({"collection_id": collection_id})

    bank: List[dict] = []
    async for doc in cursor:
        raw_questions = doc.get("questionnaire", [])
        if not isinstance(raw_questions, list):
            continue
        for raw_question in raw_questions:
            normalized = _normalize_mcq_question(raw_question, doc)
            if normalized:
                bank.append(normalized)
    return bank


async def create_quiz_session(document: dict) -> dict:
    from app.database import get_collection

    quiz_sessions = get_collection("quiz_sessions")
    await quiz_sessions.insert_one(document.copy())
    return document


async def get_quiz_session(session_id: str) -> Optional[dict]:
    from app.database import get_collection

    quiz_sessions = get_collection("quiz_sessions")
    doc = await quiz_sessions.find_one({"id": session_id})
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


async def complete_quiz_session(
    session_id: str,
    score: int,
    answers: List[dict],
    wrong_answers: List[dict],
    llm_suggestions: str,
) -> Optional[dict]:
    from app.database import get_collection

    quiz_sessions = get_collection("quiz_sessions")
    completed_at = datetime.utcnow()
    update_result = await quiz_sessions.update_one(
        {"id": session_id},
        {
            "$set": {
                "status": "completed",
                "score": score,
                "answers": answers,
                "wrong_answers": wrong_answers,
                "llm_suggestions": llm_suggestions,
                "completed_at": completed_at,
            }
        }
    )
    if update_result.matched_count == 0:
        return None
    result = await quiz_sessions.find_one({"id": session_id})
    if not result:
        return None
    result.pop("_id", None)
    return result
