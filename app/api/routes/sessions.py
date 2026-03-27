from fastapi import APIRouter, Depends, Query, status
from typing import Optional
from app.db.models.user import User
from app.db.models.knowledge import DifficultyLevel
from app.api.deps import get_current_active_user, get_admin_user
from app.schemas.session import StudySessionResponse, PracticeResultResponse
from app.core.responses import success_response
from app.core.exceptions import ResourceNotFoundException, ForbiddenException
from app.services.session_service import (
    SessionService,
    get_session_service,
    StudySessionCreate,
    PracticeResultCreate,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ============================================
# STUDY SESSIONS
# ============================================


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: StudySessionCreate,
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """Create a new study session. User selects lessons → system prepares the session."""
    session = svc.create_session(current_user.id, data)
    return success_response(
        StudySessionResponse.model_validate(session).model_dump(by_alias=True)
    )


@router.get("/me", response_model=None)
async def my_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """Get all study sessions for the current user."""
    sessions = svc.get_sessions_for_user(current_user.id, skip=skip, limit=limit)
    return success_response(
        [
            StudySessionResponse.model_validate(s).model_dump(by_alias=True)
            for s in sessions
        ]
    )


@router.get("/stats/me", response_model=None)
async def my_stats(
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """Aggregate learning statistics for the current user."""
    return success_response(svc.get_user_stats(current_user.id))


@router.get("/{session_id}", response_model=None)
async def get_session(
    session_id: int,
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """Get a study session by ID (owner only)."""
    session = svc.get_session_by_id(session_id)
    if not session:
        raise ResourceNotFoundException("StudySession", session_id)
    if session.user_id != current_user.id:
        raise ForbiddenException("Access denied")
    return success_response(
        StudySessionResponse.model_validate(session).model_dump(by_alias=True)
    )


@router.patch("/{session_id}/complete", response_model=None)
async def complete_session(
    session_id: int,
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """Mark a study session as completed."""
    session = svc.complete_session(session_id, current_user.id)
    return success_response(
        StudySessionResponse.model_validate(session).model_dump(by_alias=True)
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_admin_user),
    svc: SessionService = Depends(get_session_service),
):
    """Delete a session. Admin only."""
    svc.delete_session(session_id)
    return None


# ============================================
# QUESTION SELECTION
# ============================================


@router.post("/{session_id}/questions", response_model=None)
async def get_questions_for_session(
    session_id: int,
    num_questions: int = Query(default=10, ge=1, le=50),
    difficulty: Optional[DifficultyLevel] = Query(None),
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """
    Weighted question sampling for a session.

    Pulls questions from knowledge nodes linked to the session's lessons.
    Nodes with higher importance_weight appear more frequently.
    """
    session = svc.get_session_by_id(session_id)
    if not session:
        raise ResourceNotFoundException("StudySession", session_id)
    if session.user_id != current_user.id:
        raise ForbiddenException("Access denied")

    questions = svc.select_questions(
        lesson_ids=session.selected_lessons,
        num_questions=num_questions,
        difficulty=difficulty,
    )
    return success_response([q.model_dump(by_alias=True) for q in questions])


# ============================================
# PRACTICE RESULTS
# ============================================


@router.post("/results", response_model=None, status_code=status.HTTP_201_CREATED)
async def submit_result(
    data: PracticeResultCreate,
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """
    Submit practice results after completing questions.
    Score is recalculated server-side for integrity.
    """
    result = svc.submit_result(current_user.id, data)
    return success_response(
        PracticeResultResponse.model_validate(result).model_dump(by_alias=True)
    )


@router.get("/{session_id}/results", response_model=None)
async def get_session_results(
    session_id: int,
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """Get all practice results for a session."""
    session = svc.get_session_by_id(session_id)
    if not session:
        raise ResourceNotFoundException("StudySession", session_id)
    if session.user_id != current_user.id:
        raise ForbiddenException("Access denied")
    results = svc.get_results_for_session(session_id)
    return success_response(
        [
            PracticeResultResponse.model_validate(r).model_dump(by_alias=True)
            for r in results
        ]
    )


# ============================================
# MASTERY ANALYSIS + RECOMMENDATIONS
# ============================================


@router.get("/{session_id}/mastery", response_model=None)
async def get_mastery_report(
    session_id: int,
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """
    Mastery analysis after practice.

    Returns:
    - mastery_level: beginner / developing / proficient / mastered
    - weak_node_ids: knowledge nodes to review
    - strong_node_ids: knowledge nodes where user excels
    - recommendations: personalised suggestions in Vietnamese
    """
    report = svc.analyze_mastery(session_id, current_user.id)
    return success_response(
        report.model_dump(by_alias=True) if hasattr(report, "model_dump") else report
    )
