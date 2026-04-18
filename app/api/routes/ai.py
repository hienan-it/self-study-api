"""
app/api/routes/ai.py

AI Routes — Mindmap Generation và Exam Generation.

Endpoints:
  POST /ai/mindmap          → Sinh mindmap từ session
  GET  /ai/mindmap/me       → Danh sách mindmaps của user
  GET  /ai/mindmap/{id}     → Lấy mindmap đã sinh
  DELETE /ai/mindmap/{id}   → Xoá mindmap
  POST /ai/exam             → Sinh đề thi từ lessons (Bloom's Taxonomy)
  POST /ai/exam/session/{id}→ Sinh đề thi từ session có sẵn

Tất cả đều yêu cầu authentication.
"""

import traceback
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.db.models.user import User
from app.db.models.knowledge import DifficultyLevel
from app.db.models.session import GeneratedMindmap, StudySession
from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.ai.llm_client import get_llm_client, LLMClient
from app.ai.mindmap_generator import get_mindmap_generator
from app.ai.exam_generator import get_exam_generator
from app.schemas.ai import (
    MindmapResponse,
    MindmapGenerateRequest,
    ExamResponse,
    ExamGenerateRequest,
    ExamQuestionResponse,
)
from app.core.responses import success_response
from app.core.exceptions import ResourceNotFoundException, ForbiddenException

router = APIRouter(prefix="/ai", tags=["ai"])


# ============================================
# MINDMAP ENDPOINTS
# ============================================


@router.post("/mindmap", response_model=None, status_code=status.HTTP_201_CREATED)
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
        return success_response(
            MindmapResponse.model_validate(mindmap).model_dump(by_alias=True)
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi sinh mindmap: {str(e)}",
        )


@router.get("/mindmap/me", response_model=None)
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
    return success_response(
        [MindmapResponse.model_validate(m).model_dump(by_alias=True) for m in mindmaps]
    )


@router.get("/mindmap/{mindmap_id}", response_model=None)
async def get_mindmap(
    mindmap_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Lấy mindmap theo ID."""
    mindmap = (
        db.query(GeneratedMindmap).filter(GeneratedMindmap.id == mindmap_id).first()
    )
    if not mindmap:
        raise ResourceNotFoundException("GeneratedMindmap", mindmap_id)
    if mindmap.user_id != current_user.id:
        raise ForbiddenException("Không có quyền truy cập")
    return success_response(
        MindmapResponse.model_validate(mindmap).model_dump(by_alias=True)
    )


@router.delete("/mindmap/{mindmap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mindmap(
    mindmap_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Xoá mindmap."""
    mindmap = (
        db.query(GeneratedMindmap).filter(GeneratedMindmap.id == mindmap_id).first()
    )
    if not mindmap:
        raise ResourceNotFoundException("GeneratedMindmap", mindmap_id)
    if mindmap.user_id != current_user.id:
        raise ForbiddenException("Không có quyền truy cập")
    db.delete(mindmap)
    db.commit()
    return None


# ============================================
# EXAM ENDPOINTS
# ============================================


@router.post("/exam", response_model=None, status_code=status.HTTP_201_CREATED)
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
    - basic       → Remember (Nhớ)
    - intermediate→ Understand (Hiểu)
    - advanced    → Apply/Analyze (Áp dụng/Phân tích)

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
        
        exam = ExamResponse(
            total_questions=result.total_questions,
            nodes_covered=result.nodes_covered,
            nodes_total=result.nodes_total,
            coverage_report=result.coverage_report,
            questions=[
                ExamQuestionResponse(
                    id=q.id,
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
            ],
        )
        return success_response(exam.model_dump(by_alias=True))

        # result_data = {
        #         "success": True,
        #         "data": {
        #             "total_questions": 10,
        #             "nodes_covered": 7,
        #             "nodes_total": 9,
        #             "coverage_report": {
        #             "nodes_total": 9,
        #             "nodes_covered": 7,
        #             "coverage_rate": 77.8,
        #             "allocation": {
        #                 "Thông tin": 1,
        #                 "Khái niệm tin học": 2,
        #                 "Dữ liệu": 2,
        #                 "Vai trò máy tính": 0,
        #                 "Bit": 1,
        #                 "Đơn vị đo thông tin": 1,
        #                 "Dạng thông tin": 0,
        #                 "Đặc tính máy tính": 1,
        #                 "Sự hình thành tin học": 2
        #             }
        #         },
        #         "questions": [
        #             {
        #                 "knowledge_node_id": 7,
        #                 "knowledge_node_title": "Bit",
        #                 "question_type": "multiple_choice",
        #                 "difficulty": "basic",
        #                 "bloom_level": "Remember (Nhớ)",
        #                 "content": "Đơn vị nhỏ nhất của thông tin được gọi là gì?",
        #                 "options": {
        #                     "A": "Bit",
        #                     "B": "Byte",
        #                     "C": "Kilobyte",
        #                     "D": "Megabyte"
        #                 },
        #                 "correct_answer": "A",
        #                 "explanation": "Theo định nghĩa, Bit là đơn vị nhỏ nhất của thông tin. Các đơn vị khác như Byte, Kilobyte, Megabyte đều là các đơn vị đo thông tin nhưng lớn hơn Bit."
        #             },
        #             {
        #                 "knowledge_node_id": 1,
        #                 "knowledge_node_title": "Sự hình thành tin học",
        #                 "question_type": "multiple_choice",
        #                 "difficulty": "basic",
        #                 "bloom_level": "Remember (Nhớ)",
        #                 "content": "Phát biểu nào sau đây mô tả đúng về sự phát triển của Tin học dựa trên nội dung kiến thức đã cho?",
        #                 "options": {
        #                     "A": "Tin học phát triển độc lập, không liên quan đến các yếu tố xã hội.",
        #                     "B": "Tin học chỉ phát triển sau khi cách mạng công nghiệp đã kết thúc.",
        #                     "C": "Tin học phát triển song hành với cách mạng công nghiệp và sự bùng nổ thông tin.",
        #                     "D": "Tin học chỉ phát triển nhờ sự bùng nổ thông tin, không liên quan đến cách mạng công nghiệp."
        #                 },
        #                 "correct_answer": "C",
        #                 "explanation": "Nội dung kiến thức chỉ ra rằng 'Tin học phát triển cùng cách mạng công nghiệp và sự bùng nổ thông tin', điều này có nghĩa là Tin học phát triển song hành với hai yếu tố này. Các phương án khác đều không đúng với thông tin được cung cấp."
        #             },
        #             {
        #                 "knowledge_node_id": 6,
        #                 "knowledge_node_title": "Thông tin",
        #                 "question_type": "multiple_choice",
        #                 "difficulty": "basic",
        #                 "bloom_level": "Remember (Nhớ)",
        #                 "content": "Định nghĩa nào sau đây mô tả đúng về thông tin?",
        #                 "options": {
        #                     "A": "Thông tin là dữ liệu thô, chưa qua xử lý.",
        #                     "B": "Thông tin là dữ liệu đã được xử lý có ý nghĩa.",
        #                     "C": "Thông tin là tập hợp các sự kiện và con số.",
        #                     "D": "Thông tin là dữ liệu đã được thu thập nhưng không cần xử lý."
        #                 },
        #                 "correct_answer": "B",
        #                 "explanation": "Theo nội dung kiến thức đã học, thông tin được định nghĩa là dữ liệu đã được xử lý và mang lại ý nghĩa. Các phương án khác mô tả dữ liệu ở trạng thái thô hoặc chưa đầy đủ về bản chất của thông tin."
        #             },
        #             {
        #                 "knowledge_node_id": 5,
        #                 "knowledge_node_title": "Dữ liệu",
        #                 "question_type": "multiple_choice",
        #                 "difficulty": "basic",
        #                 "bloom_level": "Remember (Nhớ)",
        #                 "content": "Theo nội dung kiến thức đã học, khái niệm 'dữ liệu' được định nghĩa là gì?",
        #                 "options": {
        #                     "A": "Các sự kiện thô chưa xử lý.",
        #                     "B": "Các thông tin đã được phân tích.",
        #                     "C": "Những kết quả đã được tổng hợp.",
        #                     "D": "Tập hợp các quyết định quan trọng."
        #                 },
        #                 "correct_answer": "A",
        #                 "explanation": "Dữ liệu được định nghĩa là các sự kiện thô chưa xử lý. Đây là đặc điểm cơ bản nhất để nhận biết dữ liệu."
        #             },
        #             {
        #                 "knowledge_node_id": 4,
        #                 "knowledge_node_title": "Khái niệm tin học",
        #                 "question_type": "multiple_choice",
        #                 "difficulty": "basic",
        #                 "bloom_level": "Remember (Nhớ)",
        #                 "content": "Theo định nghĩa được cung cấp, Tin học là ngành khoa học nghiên cứu về vấn đề gì?",
        #                 "options": {
        #                     "A": "Thông tin và cách xử lý thông tin bằng máy tính.",
        #                     "B": "Lịch sử phát triển của các loại máy tính.",
        #                     "C": "Các kỹ thuật lập trình và phát triển phần mềm.",
        #                     "D": "Cấu tạo và nguyên lý hoạt động của máy tính."
        #                 },
        #                 "correct_answer": "A",
        #                 "explanation": "Theo định nghĩa, Tin học là ngành khoa học nghiên cứu về thông tin và cách xử lý thông tin bằng máy tính. Các phương án khác là những lĩnh vực liên quan hoặc một phần của Tin học nhưng không phải là định nghĩa bao quát."
        #             },
        #             {
        #                 "knowledge_node_id": 5,
        #                 "knowledge_node_title": "Dữ liệu",
        #                 "question_type": "multiple_choice",
        #                 "difficulty": "basic",
        #                 "bloom_level": "Remember (Nhớ)",
        #                 "content": "Đặc điểm nào sau đây mô tả đúng về dữ liệu?",
        #                 "options": {
        #                     "A": "Đã được xử lý và có ý nghĩa.",
        #                     "B": "Luôn mang lại giá trị trực tiếp.",
        #                     "C": "Là các sự kiện thô.",
        #                     "D": "Giúp đưa ra quyết định nhanh chóng."
        #                 },
        #                 "correct_answer": "C",
        #                 "explanation": "Dữ liệu có đặc điểm là các sự kiện thô, chưa trải qua quá trình xử lý để trở thành thông tin có ý nghĩa. Các phương án khác mô tả thông tin hoặc giá trị của thông tin."
        #             },
        #             {
        #                 "knowledge_node_id": 8,
        #                 "knowledge_node_title": "Đơn vị đo thông tin",
        #                 "question_type": "multiple_choice",
        #                 "difficulty": "basic",
        #                 "bloom_level": "Remember (Nhớ)",
        #                 "content": "Trong các đơn vị sau, đơn vị nào dùng để đo lượng thông tin?",
        #                 "options": {
        #                     "A": "Byte",
        #                     "B": "Mét",
        #                     "C": "Kilogram",
        #                     "D": "Giờ"
        #                 },
        #                 "correct_answer": "A",
        #                 "explanation": "Byte là một trong các đơn vị cơ bản dùng để đo lượng thông tin, thường được dùng để chỉ dung lượng của dữ liệu hoặc bộ nhớ. Mét dùng để đo chiều dài, Kilogram dùng để đo khối lượng, còn Giờ dùng để đo thời gian."
        #             },
        #             {
        #                 "knowledge_node_id": 1,
        #                 "knowledge_node_title": "Sự hình thành tin học",
        #                 "question_type": "multiple_choice",
        #                 "difficulty": "basic",
        #                 "bloom_level": "Remember (Nhớ)",
        #                 "content": "Theo nội dung kiến thức, sự hình thành và phát triển của Tin học gắn liền với những yếu tố chính nào?",
        #                 "options": {
        #                     "A": "Cách mạng công nghiệp và sự bùng nổ thông tin.",
        #                     "B": "Sự phát triển của nông nghiệp và y học.",
        #                     "C": "Các cuộc chiến tranh thế giới và khủng hoảng kinh tế.",
        #                     "D": "Sự ra đời của các loại hình nghệ thuật mới."
        #                 },
        #                 "correct_answer": "A",
        #                 "explanation": "Nội dung kiến thức đã nêu rõ: 'Tin học phát triển cùng cách mạng công nghiệp và sự bùng nổ thông tin'. Do đó, đáp án A là chính xác."
        #             },
        #             {
        #                 "knowledge_node_id": 3,
        #                 "knowledge_node_title": "Đặc tính máy tính",
        #                 "question_type": "multiple_choice",
        #                 "difficulty": "basic",
        #                 "bloom_level": "Remember (Nhớ)",
        #                 "content": "Đâu là một trong những đặc tính cơ bản của máy tính được đề cập?",
        #                 "options": {
        #                     "A": "Tốc độ xử lý chậm",
        #                     "B": "Khả năng lưu trữ nhỏ",
        #                     "C": "Hoạt động liên tục",
        #                     "D": "Độ chính xác thấp"
        #                 },
        #                 "correct_answer": "C",
        #                 "explanation": "Theo nội dung kiến thức, máy tính có đặc tính hoạt động liên tục. Các phương án A, B, D đều trái ngược với các đặc tính cơ bản khác của máy tính là nhanh, lưu trữ lớn và chính xác."
        #             },
        #             {
        #                 "knowledge_node_id": 4,
        #                 "knowledge_node_title": "Khái niệm tin học",
        #                 "question_type": "multiple_choice",
        #                 "difficulty": "basic",
        #                 "bloom_level": "Remember (Nhớ)",
        #                 "content": "Phạm vi nghiên cứu chính của Tin học, như đã nêu, bao gồm những yếu tố nào?",
        #                 "options": {
        #                     "A": "Thông tin và cách thức xử lý chúng bằng máy tính.",
        #                     "B": "Dữ liệu và các phương pháp lưu trữ chúng.",
        #                     "C": "Phần cứng máy tính và các thiết bị ngoại vi.",
        #                     "D": "Các ngôn ngữ lập trình và ứng dụng phần mềm."
        #                 },
        #                 "correct_answer": "A",
        #                 "explanation": "Định nghĩa Tin học tập trung vào việc nghiên cứu thông tin và cách xử lý thông tin bằng máy tính. Mặc dù dữ liệu, phần cứng và lập trình là các khía cạnh quan trọng, nhưng 'thông tin và cách xử lý bằng máy tính' là cốt lõi của định nghĩa được cung cấp."
        #             }
        #         ]
        #     }
        # }

        # actual_data = result_data["data"]

        # exam = ExamResponse(
        #     total_questions=actual_data["total_questions"],
        #     nodes_covered=actual_data["nodes_covered"],
        #     nodes_total=actual_data["nodes_total"],
        #     coverage_report=actual_data["coverage_report"],
        #     questions=[
        #         ExamQuestionResponse(
        #             id=q.get("id", 0),
        #             knowledge_node_id=q["knowledge_node_id"],
        #             knowledge_node_title=q["knowledge_node_title"],
        #             question_type=q["question_type"],
        #             difficulty=q["difficulty"],
        #             bloom_level=q["bloom_level"],
        #             content=q["content"],
        #             options=q["options"],
        #             correct_answer=q["correct_answer"],
        #             explanation=q["explanation"],
        #         )
        #         for q in actual_data["questions"]
        #     ],
        # )
        # return success_response(exam.model_dump(by_alias=True))

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi sinh đề thi: {str(e)}",
        )


@router.post("/exam/session/{session_id}", response_model=None)
async def generate_exam_for_session(
    session_id: int,
    total_questions: int = Query(default=10, ge=3, le=30),
    question_type: str = Query(default="multiple_choice"),
    difficulty_filter: Optional[DifficultyLevel] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
):
    """Sinh đề thi tự động từ một study session có sẵn."""
    session = db.query(StudySession).filter(StudySession.id == session_id).first()
    if not session:
        raise ResourceNotFoundException("StudySession", session_id)
    if session.user_id != current_user.id:
        raise ForbiddenException("Không có quyền truy cập")

    try:
        generator = get_exam_generator(db, llm_client)
        result = await generator.generate_exam(
            lesson_ids=session.selected_lessons,
            total_questions=total_questions,
            question_type=question_type,
            difficulty_filter=difficulty_filter,
        )

        exam = ExamResponse(
            total_questions=result.total_questions,
            nodes_covered=result.nodes_covered,
            nodes_total=result.nodes_total,
            coverage_report=result.coverage_report,
            questions=[
                ExamQuestionResponse(
                    id=q.id,
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
            ],
        )
        return success_response(exam.model_dump(by_alias=True))

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi sinh đề thi: {str(e)}",
        )
