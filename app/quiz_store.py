from datetime import datetime
from typing import Dict, List, Optional


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
    }


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
