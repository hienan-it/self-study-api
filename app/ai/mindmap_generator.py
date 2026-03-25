"""
app/ai/mindmap_generator.py

Mindmap Generator — Graph → Tree + LLM enrichment.

Pipeline:
  GraphContext (nodes + edges)
       ↓
  BFS Spanning Tree (loại bỏ chu trình, giữ cấu trúc cây)
       ↓
  LLM Enrichment (thêm mô tả, ghi chú học tập bằng tiếng Việt)
       ↓
  JSON Mindmap (lưu vào GeneratedMindmap)

LLM bị ràng buộc chỉ dùng thông tin từ graph context.
Không được bịa thêm kiến thức ngoài graph.
"""

import json
import logging
from typing import Optional, Dict, Set, List
from collections import deque
from sqlalchemy.orm import Session as DBSession

from app.ai.llm_client import LLMClient, get_llm_client
from app.ai.graph_rag import GraphContext, GraphContextSerializer, SubgraphExtractor
from app.db.models.knowledge import KnowledgeNode, KnowledgeEdge, DifficultyLevel
from app.db.models.session import GeneratedMindmap
from app.db.models.lesson import lesson_knowledge

logger = logging.getLogger(__name__)


# ============================================
# TREE BUILDER (Graph → Tree, không dùng LLM)
# ============================================

class MindmapTreeBuilder:
    """
    Chuyển knowledge graph thành cây mindmap bằng BFS spanning tree.

    Xử lý chu trình: node đã visit sẽ không được thêm lại,
    tránh infinite loop trong cấu trúc cây.
    """

    def build(self, ctx: GraphContext, root_node_id: Optional[int] = None) -> dict:
        """
        Xây dựng cây mindmap từ GraphContext.

        Args:
            ctx: Subgraph context đã extract
            root_node_id: Node làm gốc cây. Nếu None → tự chọn node quan trọng nhất
                          không có incoming edge trong subgraph.

        Returns:
            dict dạng cây:
            {
                "id": 1,
                "title": "Hàm số",
                "node_type": "concept",
                "difficulty_level": "basic",
                "importance_weight": 9,
                "description": "...",
                "children": [...]
            }
        """
        if ctx.is_empty():
            return {}

        # Chọn root node
        if root_node_id:
            root = ctx.get_node_by_id(root_node_id)
            if not root:
                logger.warning(f"Root node {root_node_id} không có trong subgraph, tự chọn root.")
                root = ctx.get_root_candidates()[0]
        else:
            root = ctx.get_root_candidates()[0]

        # BFS spanning tree — tránh chu trình
        visited: Set[int] = set()

        def build_subtree(node: KnowledgeNode) -> dict:
            visited.add(node.id)

            # Lấy children chưa visit
            children_nodes = [
                n for n in ctx.get_children(node.id)
                if n.id not in visited
            ]

            # Sắp xếp children: importance_weight giảm dần
            children_nodes.sort(key=lambda n: -n.importance_weight)

            return {
                "id": node.id,
                "title": node.title,
                "node_type": node.node_type,
                "difficulty_level": node.difficulty_level,
                "importance_weight": node.importance_weight,
                "description": node.description or "",
                "children": [build_subtree(child) for child in children_nodes],
            }

        return build_subtree(root)


# ============================================
# LLM ENRICHMENT
# ============================================

class MindmapLLMEnricher:
    """
    Dùng LLM để làm phong phú mindmap tree.

    Nhiệm vụ của LLM:
    - Thêm "learning_note": ghi chú học tập ngắn, dễ nhớ cho mỗi node
    - Thêm "key_formula": công thức quan trọng (nếu node_type là formula/theorem)
    - Thêm "memory_tip": mẹo ghi nhớ bằng tiếng Việt
    - Gợi ý "study_order": thứ tự nên học các nhánh

    LLM KHÔNG được:
    - Thêm node mới không có trong graph
    - Thay đổi cấu trúc cây (thêm/xóa children)
    - Bịa thông tin không có trong description của node
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.serializer = GraphContextSerializer()

    async def enrich(self, tree: dict, ctx: GraphContext) -> dict:
        """
        Gọi LLM để enrich mindmap tree.

        Args:
            tree: Raw tree từ MindmapTreeBuilder
            ctx: GraphContext (dùng làm "RAG context" cho LLM)

        Returns:
            Enriched tree với learning_note, key_formula, memory_tip
        """
        if not tree:
            return tree

        # Serialize graph context để đưa vào prompt
        graph_context_text = self.serializer.to_prompt_text(ctx)
        tree_json = json.dumps(tree, ensure_ascii=False, indent=2)

        system_prompt = """Bạn là trợ lý giáo dục thông minh chuyên hỗ trợ học sinh Việt Nam.
Nhiệm vụ: Làm phong phú mindmap học tập bằng cách thêm ghi chú học tập vào mỗi node.

QUY TẮC BẮT BUỘC:
1. CHỈ dùng thông tin có trong Knowledge Graph Context được cung cấp
2. KHÔNG bịa thêm kiến thức không có trong context
3. KHÔNG thay đổi cấu trúc cây (id, title, children phải giữ nguyên)
4. Viết bằng tiếng Việt, ngắn gọn, dễ hiểu cho học sinh
5. Trả về JSON hợp lệ với đúng cấu trúc được yêu cầu"""

        user_prompt = f"""Dưới đây là Knowledge Graph Context (nguồn kiến thức duy nhất bạn được phép dùng):

{graph_context_text}

---

Dưới đây là cây mindmap cần làm phong phú:

{tree_json}

---

Hãy thêm các trường sau vào MỖI node trong cây (kể cả nodes trong children):
- "learning_note": Ghi chú học tập 1–2 câu, giải thích đơn giản cho học sinh
- "memory_tip": Mẹo ghi nhớ sáng tạo (ví dụ: câu thơ, viết tắt, liên tưởng hình ảnh)
- "key_formula": Công thức/định nghĩa quan trọng nhất (để trống "" nếu không có)
- "difficulty_note": 1 câu về tại sao node này khó/dễ

QUAN TRỌNG: Giữ NGUYÊN tất cả các trường gốc (id, title, node_type, difficulty_level, 
importance_weight, description, children). Chỉ THÊM các trường mới.

Trả về JSON hoàn chỉnh của cây đã được làm phong phú."""

        try:
            enriched_data = await self.llm.complete_json_fast(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.4,
                max_tokens=4000,
            )

            # Validate: kiểm tra root node id còn đúng không
            if enriched_data.get("id") != tree.get("id"):
                logger.warning("LLM thay đổi cấu trúc cây, dùng tree gốc.")
                return tree

            logger.info(f"[Mindmap] Enriched thành công cho root node id={tree.get('id')}")
            return enriched_data

        except Exception as e:
            logger.error(f"[Mindmap] LLM enrichment thất bại: {e}")
            # Fallback: trả về tree gốc không có enrichment
            return tree

    async def generate_study_order(self, tree: dict, ctx: GraphContext) -> List[str]:
        """
        Gọi LLM sinh thứ tự học tập được khuyến nghị dựa trên cấu trúc graph.

        Returns:
            List các bước học theo thứ tự, ví dụ:
            ["1. Học Khái niệm hàm số trước", "2. Tiếp theo là Tập xác định", ...]
        """
        graph_context_text = self.serializer.to_prompt_text(ctx)

        user_prompt = f"""Dựa trên knowledge graph sau:

{graph_context_text}

Hãy đề xuất thứ tự học tập tối ưu cho học sinh.
Xem xét các mối quan hệ prerequisite và builds_on giữa các nodes.

Trả về JSON theo format:
{{
  "study_order": [
    "Bước 1: [tên node] - [lý do ngắn gọn]",
    "Bước 2: ...",
    ...
  ],
  "estimated_time": "Ước tính thời gian học: X tiết"
}}"""

        try:
            result = await self.llm.complete_json_fast(user_prompt=user_prompt, temperature=0.3)
            return result.get("study_order", [])
        except Exception as e:
            logger.error(f"[Mindmap] Không thể sinh study order: {e}")
            return []


# ============================================
# MAIN SERVICE
# ============================================

class MindmapGenerator:
    """
    Service tổng hợp: nhận lesson_ids, trả về GeneratedMindmap đã lưu DB.

    Flow:
        lesson_ids → query nodes/edges (DB) → SubgraphExtractor → MindmapTreeBuilder
               → MindmapLLMEnricher → lưu GeneratedMindmap → trả về
    """

    def __init__(self, db: DBSession, llm_client: LLMClient):
        self.db = db
        self.tree_builder = MindmapTreeBuilder()
        self.enricher = MindmapLLMEnricher(llm_client)
        self.extractor = SubgraphExtractor()
        self.serializer = GraphContextSerializer()

    async def generate_for_session(
        self,
        user_id: int,
        lesson_ids: List[int],
        root_node_id: Optional[int] = None,
        max_depth: int = 3,
        min_importance: int = 2,
        difficulty_filter: Optional[DifficultyLevel] = None,
        enrich_with_llm: bool = True,
    ) -> GeneratedMindmap:
        """
        Generate và lưu mindmap cho một học session.

        Args:
            user_id: ID học sinh
            lesson_ids: Danh sách lesson đã chọn
            root_node_id: Node làm gốc (None = tự chọn)
            max_depth: Độ sâu BFS tối đa
            min_importance: Chỉ lấy node có importance >= giá trị này
            difficulty_filter: Lọc theo độ khó
            enrich_with_llm: True = gọi LLM thêm ghi chú; False = chỉ dùng raw tree

        Returns:
            GeneratedMindmap đã được lưu vào database
        """
        # ---- Bước 1: Query nodes từ lessons ----
        from app.db.models.knowledge import KnowledgeNode, KnowledgeEdge
        from sqlalchemy import or_

        seed_nodes: List[KnowledgeNode] = (
            self.db.query(KnowledgeNode)
            .join(lesson_knowledge, KnowledgeNode.id == lesson_knowledge.c.knowledge_node_id)
            .filter(lesson_knowledge.c.lesson_id.in_(lesson_ids))
            .all()
        )

        if not seed_nodes:
            raise ValueError(f"Không tìm thấy knowledge nodes cho lessons: {lesson_ids}")

        seed_ids = [n.id for n in seed_nodes]

        # Query tất cả edges liên quan
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

        # Build neighbor lookup
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

        # ---- Bước 2: BFS Subgraph Extraction ----
        ctx = self.extractor.extract_for_lessons(
            lesson_nodes=seed_nodes,
            all_edges=all_edges,
            all_neighbor_nodes=node_lookup,
            max_depth=max_depth,
            min_importance=min_importance,
            difficulty_filter=difficulty_filter,
        )

        logger.info(
            f"[Mindmap] Subgraph extracted: {ctx.total_nodes} nodes, "
            f"{ctx.total_edges} edges, depth={ctx.max_depth_reached}"
        )

        # ---- Bước 3: Graph → Tree ----
        tree = self.tree_builder.build(ctx, root_node_id)

        if not tree:
            raise ValueError("Không thể tạo cây mindmap từ subgraph.")

        # ---- Bước 4: LLM Enrichment (tuỳ chọn) ----
        if enrich_with_llm:
            tree = await self.enricher.enrich(tree, ctx)
            study_order = await self.enricher.generate_study_order(tree, ctx)
        else:
            study_order = []

        # ---- Bước 5: Lưu vào DB ----
        structure = {
            "tree": tree,
            "study_order": study_order,
            "metadata": {
                "total_nodes": ctx.total_nodes,
                "total_edges": ctx.total_edges,
                "lesson_ids": lesson_ids,
                "max_depth": max_depth,
                "enriched": enrich_with_llm,
            }
        }

        root_node_id_saved = tree.get("id")

        mindmap = GeneratedMindmap(
            user_id=user_id,
            root_node_id=root_node_id_saved,
            structure=structure,
        )
        self.db.add(mindmap)
        self.db.commit()
        self.db.refresh(mindmap)

        logger.info(f"[Mindmap] Đã lưu GeneratedMindmap id={mindmap.id} cho user_id={user_id}")
        return mindmap


# ============================================
# DEPENDENCY
# ============================================

def get_mindmap_generator(
    db: DBSession,
    llm_client: Optional[LLMClient] = None,
) -> MindmapGenerator:
    if llm_client is None:
        llm_client = get_llm_client()
    return MindmapGenerator(db, llm_client)