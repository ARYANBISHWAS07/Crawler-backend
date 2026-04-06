from datetime import datetime
import random
import uuid
from fastapi import APIRouter, HTTPException, status

from app import collection_store
from app import llm_service
from app import quiz_store
from app.models.quiz import (
    QuizStartRequest,
    QuizStartResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
    QuizQuestionPublic,
    WrongQuestionFeedback,
)

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


@router.get("/collections")
async def list_quiz_ready_collections():
    """
    List collections that currently have enough MCQ questions to run a quiz.
    """
    collections = await collection_store.get_all_collections(limit=200)
    result = []
    for coll in collections:
        question_bank = await quiz_store.get_collection_mcq_bank(coll["id"])
        if not question_bank:
            continue
        result.append({
            "collection_id": coll["id"],
            "name": coll.get("name", ""),
            "url": coll.get("url", ""),
            "available_questions": len(question_bank),
        })
    return {"collections": result, "count": len(result)}


@router.post("/start", response_model=QuizStartResponse, status_code=status.HTTP_201_CREATED)
async def start_quiz(req: QuizStartRequest):
    """
    Start a new quiz session for a selected collection.
    """
    collection = await collection_store.get_collection_by_id(req.collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    question_bank = await quiz_store.get_collection_mcq_bank(req.collection_id)
    if len(question_bank) < req.question_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Not enough MCQ questions in this collection. "
                f"Available: {len(question_bank)}, requested: {req.question_count}"
            ),
        )

    selected_questions = random.sample(question_bank, req.question_count)
    quiz_session_id = str(uuid.uuid4())
    created_at = datetime.utcnow()
    quiz_document = {
        "id": quiz_session_id,
        "collection_id": req.collection_id,
        "user_id": req.user_id,
        "status": "in_progress",
        "total_questions": req.question_count,
        "score": 0,
        "questions": selected_questions,
        "answers": [],
        "wrong_answers": [],
        "llm_suggestions": "",
        "created_at": created_at,
        "completed_at": None,
    }
    await quiz_store.create_quiz_session(quiz_document)

    public_questions = [
        QuizQuestionPublic(
            id=q["id"],
            question=q["question"],
            options=q["options"],
        )
        for q in selected_questions
    ]

    return QuizStartResponse(
        quiz_session_id=quiz_session_id,
        collection_id=req.collection_id,
        total_questions=req.question_count,
        questions=public_questions,
        created_at=created_at,
    )


@router.post("/{quiz_session_id}/submit", response_model=QuizSubmitResponse)
async def submit_quiz(quiz_session_id: str, req: QuizSubmitRequest):
    """
    Submit answers for a quiz session, compute score, and get LLM guidance.
    """
    session = await quiz_store.get_quiz_session(quiz_session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz session not found",
        )

    if session.get("status") == "completed":
        wrong_answers = [
            WrongQuestionFeedback(**item)
            for item in session.get("wrong_answers", [])
        ]
        total_questions = int(session.get("total_questions", 0))
        score = int(session.get("score", 0))
        percentage = round((score / total_questions) * 100, 2) if total_questions else 0.0
        return QuizSubmitResponse(
            quiz_session_id=quiz_session_id,
            score=score,
            total_questions=total_questions,
            percentage=percentage,
            wrong_answers=wrong_answers,
            llm_suggestions=session.get("llm_suggestions", ""),
            completed_at=session.get("completed_at") or datetime.utcnow(),
        )

    question_map = {q["id"]: q for q in session.get("questions", [])}
    if not question_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quiz session has no questions",
        )

    answer_map = {}
    for item in req.answers:
        selected = item.selected_option.strip().upper()
        if selected not in {"A", "B", "C", "D"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid option '{item.selected_option}' for question '{item.question_id}'",
            )
        if item.question_id in question_map:
            answer_map[item.question_id] = selected

    score = 0
    normalized_answers = []
    wrong_answers = []
    for question_id, question in question_map.items():
        selected_option = answer_map.get(question_id, "")
        correct_option = question.get("correct_option", "")
        is_correct = selected_option == correct_option
        if is_correct:
            score += 1
        normalized_answers.append({
            "question_id": question_id,
            "selected_option": selected_option,
            "is_correct": is_correct,
        })
        if not is_correct:
            wrong_answers.append({
                "question_id": question_id,
                "question": question.get("question", ""),
                "selected_option": selected_option,
                "correct_option": correct_option,
                "options": question.get("options", {}),
                "explanation": question.get("explanation", ""),
            })

    llm_suggestions = llm_service.generate_quiz_improvement_feedback(
        score=score,
        total_questions=len(question_map),
        wrong_answers=wrong_answers,
    )
    updated_session = await quiz_store.complete_quiz_session(
        session_id=quiz_session_id,
        score=score,
        answers=normalized_answers,
        wrong_answers=wrong_answers,
        llm_suggestions=llm_suggestions,
    )
    if not updated_session:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finalize quiz session",
        )

    total_questions = len(question_map)
    percentage = round((score / total_questions) * 100, 2) if total_questions else 0.0
    return QuizSubmitResponse(
        quiz_session_id=quiz_session_id,
        score=score,
        total_questions=total_questions,
        percentage=percentage,
        wrong_answers=[WrongQuestionFeedback(**item) for item in wrong_answers],
        llm_suggestions=llm_suggestions,
        completed_at=updated_session.get("completed_at") or datetime.utcnow(),
    )


@router.get("/{quiz_session_id}")
async def get_quiz_session(quiz_session_id: str):
    """
    Get an existing quiz session, including score and suggestions if completed.
    """
    session = await quiz_store.get_quiz_session(quiz_session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz session not found",
        )

    return session
