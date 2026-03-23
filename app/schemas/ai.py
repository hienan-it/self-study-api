from typing import List, Optional
from pydantic import BaseModel, Field
from app.db.models.knowledge import DifficultyLevel

class MindmapGenerateRequest(BaseModel):
    lesson_ids: List[int] = Field(..., min_items=1, description="Danh sách lesson ID")
    root_node_id: Optional[int] = Field(None, description="Node làm gốc (None = tự chọn)")
    max_depth: int = Field(default=3, ge=1, le=5, description="Độ sâu BFS tối đa")
    min_importance: int = Field(default=2, ge=1, le=10, description="Ngưỡng importance tối thiểu")
    difficulty_filter: Optional[DifficultyLevel] = Field(None, description="Lọc theo độ khó")
    enrich_with_llm: bool = Field(default=True, description="Dùng LLM để thêm ghi chú học tập")


class MindmapResponse(BaseModel):
    id: int
    user_id: int
    root_node_id: int
    structure: dict
    created_at: Optional[str]

    class Config:
        from_attributes = True


class ExamGenerateRequest(BaseModel):
    lesson_ids: List[int] = Field(..., min_items=1, description="Danh sách lesson ID")
    total_questions: int = Field(default=10, ge=3, le=30, description="Tổng số câu hỏi")
    question_type: str = Field(
        default="multiple_choice",
        description="Loại câu hỏi: multiple_choice | short_answer | true_false"
    )
    difficulty_filter: Optional[DifficultyLevel] = Field(None, description="Chỉ sinh câu của độ khó này")
    coverage_threshold: int = Field(
        default=5, ge=1, le=10,
        description="Nodes có importance >= giá trị này phải có câu hỏi"
    )
    max_depth: int = Field(default=2, ge=1, le=4, description="Độ sâu BFS khi lấy subgraph")


class ExamQuestionResponse(BaseModel):
    knowledge_node_id: int
    knowledge_node_title: str
    question_type: str
    difficulty: str
    bloom_level: str
    content: str
    options: Optional[dict]
    correct_answer: str
    explanation: str


class ExamResponse(BaseModel):
    total_questions: int
    nodes_covered: int
    nodes_total: int
    coverage_report: dict
    questions: List[ExamQuestionResponse]