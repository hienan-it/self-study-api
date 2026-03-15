"""
app/ai/exam_generator.py

Exam Generator — Sinh đề ôn tập từ Knowledge Graph.

Pipeline:
  GraphContext
       ↓
  Weighted Node Sampling (importance_weight + coverage maximization)
       ↓
  Bloom's Taxonomy Mapping (difficulty → cognitive level)
       ↓
  LLM Question Generation (constrained prompt, tiếng Việt)
       ↓
  List[GeneratedQuestion] → lưu vào Question bank hoặc trả về trực tiếp

Nguyên tắc:
  - LLM CHỈ sinh câu hỏi dựa trên nội dung node (title + description)
  - Không bịa kiến thức ngoài graph
  - Mỗi node quan trọng (importance >= threshold) phải có ít nhất 1 câu
  - Câu hỏi được map theo Bloom's Taxonomy
"""

import json
import logging
import random
from typing import List, Dict, Optional, Set
from dataclasses import dataclass

from app.ai.llm_client import LLMClient, get_llm_client
from app.ai.graph_rag import GraphContext, GraphContextSerializer, SubgraphExtractor
from app.models.knowledge import KnowledgeNode, DifficultyLevel, NodeType
from app.models.lesson import lesson_knowledge

logger = logging.getLogger(__name__)


# ============================================
# BLOOM'S TAXONOMY MAPPING
# ============================================

"""
Bloom's Taxonomy ánh xạ với difficulty_level:

  basic       → Remember (Nhớ)
                "Định nghĩa X là gì?", "Nêu tên...", "Liệt kê..."

  intermediate → Understand (Hiểu)
                "Giải thích tại sao...", "So sánh X và Y", "Phân biệt..."

  advanced    → Apply / Analyze (Áp dụng / Phân tích)
                "Tính...", "Chứng minh...", "Phân tích...", "Vận dụng..."
"""

BLOOM_MAPPING = {
    "basic": {
        "level": "Remember (Nhớ)",
        "verbs": ["Định nghĩa", "Nêu", "Liệt kê", "Nhận biết", "Gọi tên"],
        "question_stems": [
            "Định nghĩa {title} là gì?",
            "Nêu đặc điểm của {title}.",
            "{title} được định nghĩa như thế nào?",
            "Hãy nhận biết {title} trong các ví dụ sau.",
        ],
    },
    "intermediate": {
        "level": "Understand (Hiểu)",
        "verbs": ["Giải thích", "So sánh", "Phân biệt", "Mô tả", "Diễn giải"],
        "question_stems": [
            "Giải thích {title} bằng lời của bạn.",
            "So sánh {title} với khái niệm liên quan.",
            "Tại sao {title} quan trọng trong bài học này?",
            "Mô tả cách {title} hoạt động.",
        ],
    },
    "advanced": {
        "level": "Apply / Analyze (Áp dụng / Phân tích)",
        "verbs": ["Tính toán", "Chứng minh", "Phân tích", "Vận dụng", "Đánh giá"],
        "question_stems": [
            "Vận dụng {title} để giải quyết bài toán sau.",
            "Phân tích mối quan hệ của {title} với các khái niệm khác.",
            "Chứng minh hoặc tính toán dựa trên {title}.",
        ],
    },
}


# ============================================
# DATA STRUCTURES
# ============================================

@dataclass
class GeneratedQuestion:
    """Câu hỏi được sinh ra từ LLM."""
    knowledge_node_id: int
    knowledge_node_title: str
    question_type: str          # "multiple_choice" | "short_answer" | "true_false"
    difficulty: str             # "basic" | "intermediate" | "advanced"
    bloom_level: str            # "Remember" | "Understand" | "Apply/Analyze"
    content: str                # Nội dung câu hỏi
    options: Optional[Dict]     # {"A": "...", "B": "...", "C": "...", "D": "..."} hoặc None
    correct_answer: str         # "A" | "B" | "C" | "D" hoặc text ngắn
    explanation: str            # Giải thích đáp án bằng tiếng Việt


@dataclass
class ExamResult:
    """Kết quả generate exam."""
    questions: List[GeneratedQuestion]
    coverage_report: Dict       # Mỗi node được cover mấy câu
    total_questions: int
    nodes_covered: int
    nodes_total: int


# ============================================
# WEIGHTED NODE SAMPLER
# ============================================

class WeightedNodeSampler:
    """
    Chọn nodes để sinh câu hỏi theo 2 chiến lược kết hợp:

    1. Coverage Maximization (Greedy Set Cover):
       Đảm bảo mỗi node quan trọng (importance >= threshold) có ít nhất 1 câu.

    2. Weighted Sampling:
       Phân bổ số câu còn lại theo importance_weight.
       Probability ∝ importance_weight
    """

    def sample(
        self,
        ctx: GraphContext,
        total_questions: int,
        coverage_threshold: int = 5,   # Node có importance >= này PHẢI có câu hỏi
        max_questions_per_node: int = 3,
    ) -> Dict[int, int]:
        """
        Trả về dict: {node_id: số_câu_hỏi_cần_sinh}

        Args:
            ctx: GraphContext chứa các nodes
            total_questions: Tổng số câu hỏi cần sinh
            coverage_threshold: Nodes quan trọng >= ngưỡng này phải được cover
            max_questions_per_node: Giới hạn số câu mỗi node (tránh lặp)

        Returns:
            {node_id: số_câu} — tổng giá trị = total_questions (hoặc ít hơn nếu không đủ nodes)
        """
        nodes = ctx.nodes
        if not nodes:
            return {}

        allocation: Dict[int, int] = {n.id: 0 for n in nodes}

        # ---- Phase 1: Coverage Maximization ----
        # Các node quan trọng (importance >= threshold) phải có ít nhất 1 câu
        must_cover = [n for n in nodes if n.importance_weight >= coverage_threshold]
        remaining_budget = total_questions

        for node in must_cover:
            if remaining_budget <= 0:
                break
            allocation[node.id] = 1
            remaining_budget -= 1

        # ---- Phase 2: Weighted Sampling ----
        # Phân bổ budget còn lại theo importance_weight
        if remaining_budget > 0:
            # Tạo weighted pool
            pool = []
            for node in nodes:
                # Số câu tối đa có thể thêm cho node này
                can_add = max_questions_per_node - allocation[node.id]
                if can_add > 0:
                    # Thêm node vào pool tương ứng với importance_weight lần
                    pool.extend([node.id] * node.importance_weight)

            # Sample không thay thế
            sampled_ids = []
            pool_copy = pool.copy()
            random.shuffle(pool_copy)

            seen = set()
            counts: Dict[int, int] = {}

            for node_id in pool_copy:
                if remaining_budget <= 0:
                    break
                current_count = counts.get(node_id, 0)
                max_add = max_questions_per_node - allocation[node_id]
                if current_count < max_add:
                    counts[node_id] = current_count + 1
                    allocation[node_id] += 1
                    remaining_budget -= 1

        # Loại bỏ nodes có 0 câu
        return {node_id: count for node_id, count in allocation.items() if count > 0}

    def get_coverage_report(
        self,
        ctx: GraphContext,
        allocation: Dict[int, int],
    ) -> Dict:
        """Báo cáo coverage sau khi sample."""
        nodes_covered = len([n for n in ctx.nodes if allocation.get(n.id, 0) > 0])
        return {
            "nodes_total": ctx.total_nodes,
            "nodes_covered": nodes_covered,
            "coverage_rate": round(nodes_covered / ctx.total_nodes * 100, 1) if ctx.total_nodes > 0 else 0,
            "allocation": {
                n.title: allocation.get(n.id, 0)
                for n in sorted(ctx.nodes, key=lambda x: -x.importance_weight)
            }
        }


# ============================================
# LLM QUESTION GENERATOR
# ============================================

class QuestionLLMGenerator:
    """
    Gọi LLM để sinh câu hỏi cho từng knowledge node.
    Mỗi câu hỏi được sinh theo Bloom's Taxonomy phù hợp với difficulty_level.
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.serializer = GraphContextSerializer()

    async def generate_for_node(
        self,
        node: KnowledgeNode,
        num_questions: int,
        question_type: str = "multiple_choice",
        ctx: Optional[GraphContext] = None,
    ) -> List[GeneratedQuestion]:
        """
        Sinh câu hỏi cho một knowledge node cụ thể.

        Args:
            node: KnowledgeNode cần sinh câu hỏi
            num_questions: Số câu cần sinh
            question_type: "multiple_choice" | "short_answer" | "true_false"
            ctx: GraphContext để cung cấp context liên quan (tuỳ chọn)

        Returns:
            List[GeneratedQuestion]
        """
        bloom = BLOOM_MAPPING.get(node.difficulty_level, BLOOM_MAPPING["basic"])

        # Context bổ sung từ graph (nodes liên quan)
        related_context = ""
        if ctx:
            related_nodes = ctx.get_children(node.id)
            if related_nodes:
                related_titles = ", ".join([n.title for n in related_nodes[:5]])
                related_context = f"\nCác khái niệm liên quan: {related_titles}"

        system_prompt = """Bạn là giáo viên giỏi đang soạn đề kiểm tra cho học sinh Việt Nam.
Nhiệm vụ: Sinh câu hỏi trắc nghiệm/tự luận ngắn từ nội dung kiến thức được cung cấp.

QUY TẮC BẮT BUỘC:
1. CHỈ dùng thông tin trong phần "Nội dung kiến thức" — không bịa thêm
2. Câu hỏi phải phù hợp với mức Bloom được chỉ định
3. Đáp án phải chính xác và có giải thích rõ ràng
4. Viết bằng tiếng Việt, ngôn ngữ phù hợp với học sinh
5. Các phương án nhiễu (sai) phải hợp lý, không quá dễ loại trừ
6. Trả về JSON hợp lệ theo format được yêu cầu"""

        user_prompt = f"""Nội dung kiến thức cần ra đề:
- Chủ đề: {node.title}
- Loại: {node.node_type}
- Độ khó: {node.difficulty_level}
- Mô tả: {node.description or 'Không có mô tả thêm'}
{related_context}

Mức Bloom cần đạt: {bloom['level']}
Động từ hành động: {', '.join(bloom['verbs'])}

Yêu cầu: Sinh {num_questions} câu hỏi loại "{question_type}" theo mức Bloom trên.

Trả về JSON theo format sau:
{{
  "questions": [
    {{
      "content": "Nội dung câu hỏi đầy đủ?",
      "options": {{"A": "Phương án A", "B": "Phương án B", "C": "Phương án C", "D": "Phương án D"}},
      "correct_answer": "A",
      "explanation": "Giải thích tại sao đáp án đúng là A: ..."
    }}
  ]
}}

Lưu ý:
- Nếu loại là "true_false": options là {{"A": "Đúng", "B": "Sai"}}, correct_answer là "A" hoặc "B"
- Nếu loại là "short_answer": options là null, correct_answer là câu trả lời ngắn
- Mỗi câu hỏi phải độc lập, không lặp lại ý"""

        try:
            result = await self.llm.complete_json_fast(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.6,  # Cao hơn để câu hỏi đa dạng
                max_tokens=2000,
            )

            questions_data = result.get("questions", [])
            generated = []

            for q_data in questions_data[:num_questions]:
                generated.append(GeneratedQuestion(
                    knowledge_node_id=node.id,
                    knowledge_node_title=node.title,
                    question_type=question_type,
                    difficulty=node.difficulty_level,
                    bloom_level=bloom["level"],
                    content=q_data.get("content", ""),
                    options=q_data.get("options"),
                    correct_answer=q_data.get("correct_answer", ""),
                    explanation=q_data.get("explanation", ""),
                ))

            logger.info(f"[Exam] Sinh {len(generated)} câu cho node '{node.title}'")
            return generated

        except Exception as e:
            logger.error(f"[Exam] Lỗi khi sinh câu hỏi cho node {node.id}: {e}")
            return []

    async def generate_batch(
        self,
        ctx: GraphContext,
        allocation: Dict[int, int],
        question_type: str = "multiple_choice",
    ) -> List[GeneratedQuestion]:
        """
        Sinh câu hỏi cho tất cả nodes theo allocation dict.
        Xử lý tuần tự để tránh rate limit.

        Args:
            ctx: GraphContext
            allocation: {node_id: số_câu}
            question_type: Loại câu hỏi

        Returns:
            Tất cả câu hỏi đã sinh
        """
        all_questions: List[GeneratedQuestion] = []

        # Sắp xếp theo importance_weight để sinh node quan trọng trước
        sorted_nodes = sorted(
            ctx.nodes,
            key=lambda n: -n.importance_weight
        )

        for node in sorted_nodes:
            num = allocation.get(node.id, 0)
            if num <= 0:
                continue

            questions = await self.generate_for_node(
                node=node,
                num_questions=num,
                question_type=question_type,
                ctx=ctx,
            )
            all_questions.extend(questions)

        # Shuffle để không lộ thứ tự node
        random.shuffle(all_questions)
        return all_questions


# ============================================
# MAIN SERVICE
# ============================================

class ExamGenerator:
    """
    Service tổng hợp: nhận lesson_ids, trả về ExamResult.

    Flow:
        lesson_ids → SubgraphExtractor → WeightedNodeSampler
               → QuestionLLMGenerator → ExamResult
    """

    def __init__(self, db, llm_client: LLMClient):
        self.db = db
        self.sampler = WeightedNodeSampler()
        self.question_generator = QuestionLLMGenerator(llm_client)
        self.extractor = SubgraphExtractor()

    async def generate_exam(
        self,
        lesson_ids: List[int],
        total_questions: int = 10,
        question_type: str = "multiple_choice",
        difficulty_filter: Optional[DifficultyLevel] = None,
        coverage_threshold: int = 5,
        max_depth: int = 2,
    ) -> ExamResult:
        """
        Generate đề thi từ các lessons đã chọn.

        Args:
            lesson_ids: Danh sách lesson ID
            total_questions: Tổng số câu hỏi (5–30 là hợp lý)
            question_type: "multiple_choice" | "short_answer" | "true_false"
            difficulty_filter: Chỉ sinh câu của độ khó nhất định
            coverage_threshold: Nodes có importance >= này phải có câu
            max_depth: Độ sâu BFS khi extract subgraph

        Returns:
            ExamResult chứa tất cả câu hỏi và báo cáo coverage
        """
        from app.models.knowledge import KnowledgeNode, KnowledgeEdge
        from sqlalchemy import or_

        # ---- Bước 1: Query nodes từ lessons ----
        seed_nodes: List[KnowledgeNode] = (
            self.db.query(KnowledgeNode)
            .join(lesson_knowledge, KnowledgeNode.id == lesson_knowledge.c.knowledge_node_id)
            .filter(lesson_knowledge.c.lesson_id.in_(lesson_ids))
            .all()
        )

        if not seed_nodes:
            raise ValueError(f"Không tìm thấy knowledge nodes cho lessons: {lesson_ids}")

        seed_ids = [n.id for n in seed_nodes]

        all_edges: List[KnowledgeEdge] = (
            self.db.query(KnowledgeEdge)
            .filter(
                or_(
                    KnowledgeEdge.from_node_id.in_(seed_ids),
                    KnowledgeEdge.to_node_id.in_(seed_ids),
                )
            )
            .all()
        )

        neighbor_ids = set()
        for edge in all_edges:
            neighbor_ids.add(edge.from_node_id)
            neighbor_ids.add(edge.to_node_id)

        all_nodes: List[KnowledgeNode] = (
            self.db.query(KnowledgeNode)
            .filter(KnowledgeNode.id.in_(neighbor_ids))
            .all()
        )
        node_lookup = {n.id: n for n in all_nodes}

        # ---- Bước 2: Extract Subgraph ----
        ctx = self.extractor.extract_for_lessons(
            lesson_nodes=seed_nodes,
            all_edges=all_edges,
            all_neighbor_nodes=node_lookup,
            max_depth=max_depth,
            difficulty_filter=difficulty_filter,
        )

        logger.info(f"[Exam] Subgraph: {ctx.total_nodes} nodes cho {len(lesson_ids)} lessons")

        # ---- Bước 3: Weighted Sampling ----
        allocation = self.sampler.sample(
            ctx=ctx,
            total_questions=total_questions,
            coverage_threshold=coverage_threshold,
        )

        coverage_report = self.sampler.get_coverage_report(ctx, allocation)
        logger.info(
            f"[Exam] Coverage: {coverage_report['nodes_covered']}/{coverage_report['nodes_total']} nodes "
            f"({coverage_report['coverage_rate']}%)"
        )

        # ---- Bước 4: LLM Question Generation ----
        questions = await self.question_generator.generate_batch(
            ctx=ctx,
            allocation=allocation,
            question_type=question_type,
        )

        logger.info(f"[Exam] Sinh được {len(questions)} câu hỏi")

        return ExamResult(
            questions=questions,
            coverage_report=coverage_report,
            total_questions=len(questions),
            nodes_covered=coverage_report["nodes_covered"],
            nodes_total=coverage_report["nodes_total"],
        )

    def exam_result_to_dict(self, result: ExamResult) -> dict:
        """Serialize ExamResult thành dict để lưu DB hoặc trả về API."""
        return {
            "total_questions": result.total_questions,
            "nodes_covered": result.nodes_covered,
            "nodes_total": result.nodes_total,
            "coverage_report": result.coverage_report,
            "questions": [
                {
                    "knowledge_node_id": q.knowledge_node_id,
                    "knowledge_node_title": q.knowledge_node_title,
                    "question_type": q.question_type,
                    "difficulty": q.difficulty,
                    "bloom_level": q.bloom_level,
                    "content": q.content,
                    "options": q.options,
                    "correct_answer": q.correct_answer,
                    "explanation": q.explanation,
                }
                for q in result.questions
            ]
        }


# ============================================
# DEPENDENCY
# ============================================

def get_exam_generator(
    db,
    llm_client: Optional[LLMClient] = None,
) -> ExamGenerator:
    if llm_client is None:
        llm_client = get_llm_client()
    return ExamGenerator(db, llm_client)