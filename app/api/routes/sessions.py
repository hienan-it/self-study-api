from fastapi import APIRouter, Depends, Query, status
from typing import List, Optional
from app.models.user import User, UserRole
from app.models.knowledge import DifficultyLevel
from app.api.deps import get_current_active_user, get_admin_user
from app.schemas.session import StudySessionResponse, PracticeResultResponse
from app.services.session_service import (
    SessionService, get_session_service,
    StudySessionCreate, PracticeResultCreate,
    QuestionItem, MasteryReport,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ============================================
# STUDY SESSIONS
# ============================================

@router.post("/", response_model=StudySessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: StudySessionCreate,
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """
    Create a new study session.
    User selects lessons → system prepares the session.
    """
    return svc.create_session(current_user.id, data)


@router.get("/me", response_model=List[StudySessionResponse])
async def my_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """Get all study sessions for the current user."""
    return svc.get_sessions_for_user(current_user.id, skip=skip, limit=limit)


@router.get("/{session_id}", response_model=StudySessionResponse)
async def get_session(
    session_id: int,
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    from fastapi import HTTPException
    session = svc.get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return session


@router.patch("/{session_id}/complete", response_model=StudySessionResponse)
async def complete_session(
    session_id: int,
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """Mark a study session as completed."""
    return svc.complete_session(session_id, current_user.id)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_admin_user),
    svc: SessionService = Depends(get_session_service),
):
    """Delete a session. Admin only."""
    svc.delete_session(session_id)


# ============================================
# QUESTION SELECTION
# ============================================

@router.post("/{session_id}/questions", response_model=List[QuestionItem])
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
    from fastapi import HTTPException
    session = svc.get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return svc.select_questions(
        lesson_ids=session.selected_lessons,
        num_questions=num_questions,
        difficulty=difficulty,
    )


# ============================================
# PRACTICE RESULTS
# ============================================

@router.post("/results", response_model=PracticeResultResponse, status_code=status.HTTP_201_CREATED)
async def submit_result(
    data: PracticeResultCreate,
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """
    Submit practice results after completing questions.
    Score is recalculated server-side for integrity.
    """
    return svc.submit_result(current_user.id, data)


@router.get("/{session_id}/results", response_model=List[PracticeResultResponse])
async def get_session_results(
    session_id: int,
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """Get all practice results for a session."""
    from fastapi import HTTPException
    session = svc.get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return svc.get_results_for_session(session_id)


# ============================================
# MASTERY ANALYSIS + RECOMMENDATIONS
# ============================================

@router.get("/{session_id}/mastery", response_model=MasteryReport)
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
    return svc.analyze_mastery(session_id, current_user.id)


# ============================================
# USER STATS
# ============================================

@router.get("/stats/me")
async def my_stats(
    current_user: User = Depends(get_current_active_user),
    svc: SessionService = Depends(get_session_service),
):
    """Aggregate learning statistics for the current user."""
    return svc.get_user_stats(current_user.id)