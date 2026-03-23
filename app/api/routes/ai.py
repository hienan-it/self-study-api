"""
app/api/routes/ai_routes.py

AI Routes — endpoints cho Mindmap Generation và Exam Generation.

Endpoints:
  POST /ai/mindmap          → Sinh mindmap từ session
  GET  /ai/mindmap/{id}     → Lấy mindmap đã sinh
  POST /ai/exam             → Sinh đề thi từ session
  POST /ai/exam/preview     → Preview đề thi không lưu DB

Tất cả đều yêu cầu authentication.
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.models.user import User
from app.db.models.knowledge import DifficultyLevel
from app.db.models.session import GeneratedMindmap, StudySession
from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.ai.llm_client import get_llm_client, LLMClient
from app.ai.mindmap_generator import get_mindmap_generator
from app.ai.exam_generator import get_exam_generator
from app.schemas.ai import MindmapResponse, MindmapGenerateRequest, ExamResponse, ExamGenerateRequest, \
    ExamQuestionResponse

router = APIRouter(prefix="/ai", tags=["ai"])

# ============================================
# MINDMAP ENDPOINTS
# ============================================

@router.post("/mindmap", response_model=MindmapResponse, status_code=status.HTTP_201_CREATED)
async def generate_mindmap(
    request: MindmapGenerateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
):
    """
    Sinh mindmap từ danh sách lessons.

    Flow:
    1. Query knowledge nodes liên kết với lessons
    2. BFS subgraph extraction
    3. Graph → Tree (BFS spanning tree)
    4. LLM enrichment (thêm learning_note, memory_tip, key_formula)
    5. Lưu vào DB và trả về

    **Thời gian**: ~5–15 giây (tùy số nodes và LLM latency)
    """
    try:
        generator = get_mindmap_generator(db, llm_client)
        mindmap = await generator.generate_for_session(
            user_id=current_user.id,
            lesson_ids=request.lesson_ids,
            root_node_id=request.root_node_id,
            max_depth=request.max_depth,
            min_importance=request.min_importance,
            difficulty_filter=request.difficulty_filter,
            enrich_with_llm=request.enrich_with_llm,
        )
        return mindmap

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi sinh mindmap: {str(e)}"
        )


@router.get("/mindmap/me", response_model=List[MindmapResponse])
async def my_mindmaps(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Lấy tất cả mindmaps đã sinh của người dùng hiện tại."""
    mindmaps = (
        db.query(GeneratedMindmap)
        .filter(GeneratedMindmap.user_id == current_user.id)
        .order_by(GeneratedMindmap.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return mindmaps


@router.get("/mindmap/{mindmap_id}", response_model=MindmapResponse)
async def get_mindmap(
    mindmap_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Lấy mindmap theo ID."""
    mindmap = db.query(GeneratedMindmap).filter(GeneratedMindmap.id == mindmap_id).first()
    if not mindmap:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mindmap không tìm thấy")
    if mindmap.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập")
    return mindmap


@router.delete("/mindmap/{mindmap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mindmap(
    mindmap_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Xoá mindmap."""
    mindmap = db.query(GeneratedMindmap).filter(GeneratedMindmap.id == mindmap_id).first()
    if not mindmap:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mindmap không tìm thấy")
    if mindmap.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập")
    db.delete(mindmap)
    db.commit()


# ============================================
# EXAM ENDPOINTS
# ============================================

@router.post("/exam", response_model=ExamResponse, status_code=status.HTTP_201_CREATED)
async def generate_exam(
    request: ExamGenerateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
):
    """
    Sinh đề thi từ danh sách lessons.

    Flow:
    1. Extract subgraph từ lessons
    2. Weighted sampling: node quan trọng → nhiều câu hơn
    3. Coverage check: đảm bảo node quan trọng không bị bỏ sót
    4. LLM sinh câu hỏi theo Bloom's Taxonomy
    5. Trả về đề thi kèm đáp án và giải thích

    **Bloom's Taxonomy mapping**:
    - basic → Remember (Nhớ)
    - intermediate → Understand (Hiểu)
    - advanced → Apply/Analyze (Áp dụng/Phân tích)

    **Thời gian**: ~10–30 giây tùy số câu hỏi
    """
    try:
        generator = get_exam_generator(db, llm_client)
        result = await generator.generate_exam(
            lesson_ids=request.lesson_ids,
            total_questions=request.total_questions,
            question_type=request.question_type,
            difficulty_filter=request.difficulty_filter,
            coverage_threshold=request.coverage_threshold,
            max_depth=request.max_depth,
        )

        return ExamResponse(
            total_questions=result.total_questions,
            nodes_covered=result.nodes_covered,
            nodes_total=result.nodes_total,
            coverage_report=result.coverage_report,
            questions=[
                ExamQuestionResponse(
                    knowledge_node_id=q.knowledge_node_id,
                    knowledge_node_title=q.knowledge_node_title,
                    question_type=q.question_type,
                    difficulty=q.difficulty,
                    bloom_level=q.bloom_level,
                    content=q.content,
                    options=q.options,
                    correct_answer=q.correct_answer,
                    explanation=q.explanation,
                )
                for q in result.questions
            ]
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi sinh đề thi: {str(e)}"
        )


@router.post("/exam/session/{session_id}", response_model=ExamResponse)
async def generate_exam_for_session(
    session_id: int,
    total_questions: int = Query(default=10, ge=3, le=30),
    question_type: str = Query(default="multiple_choice"),
    difficulty_filter: Optional[DifficultyLevel] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
):
    """
    Sinh đề thi tự động từ một study session có sẵn.
    Dùng lesson_ids đã được lưu trong session.
    """
    session = db.query(StudySession).filter(StudySession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session không tìm thấy")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập")

    try:
        generator = get_exam_generator(db, llm_client)
        result = await generator.generate_exam(
            lesson_ids=session.selected_lessons,
            total_questions=total_questions,
            question_type=question_type,
            difficulty_filter=difficulty_filter,
        )

        return ExamResponse(
            total_questions=result.total_questions,
            nodes_covered=result.nodes_covered,
            nodes_total=result.nodes_total,
            coverage_report=result.coverage_report,
            questions=[
                ExamQuestionResponse(**vars(q))
                for q in result.questions
            ]
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi sinh đề thi: {str(e)}"
        )