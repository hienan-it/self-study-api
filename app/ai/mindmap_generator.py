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

import traceback
import json
import logging
import asyncio
from typing import Optional, Dict, Set, List
from collections import deque
from sqlalchemy.orm import Session as DBSession

from app.ai.llm_client import LLMClient, get_llm_client
from app.ai.graph_rag import GraphContext, GraphContextSerializer, SubgraphExtractor
from app.db.models.knowledge import KnowledgeNode, KnowledgeEdge, DifficultyLevel
from app.db.models.session import GeneratedMindmap
from app.db.models.lesson import lesson_knowledge

from app.core.logger import access_logger, error_logger


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

        # Build adjacency
        adjacency: Dict[int, List[int]] = {}
        has_parent: Set[int] = set()
        for edge in ctx.edges:
            adjacency.setdefault(edge.from_node_id, []).append(edge.to_node_id)
            has_parent.add(edge.to_node_id)

        node_lookup = {n.id: n for n in ctx.nodes}
        visited: Set[int] = set()

        def build_subtree(node: KnowledgeNode) -> dict:
            visited.add(node.id)
            child_ids = [nid for nid in adjacency.get(node.id, []) if nid not in visited]
            children_nodes = sorted(
                [node_lookup[nid] for nid in child_ids if nid in node_lookup],
                key=lambda n: -n.importance_weight
            )
            return {
                "id": node.id,
                "title": node.title,
                "node_type": node.node_type,
                "difficulty_level": node.difficulty_level,
                "importance_weight": node.importance_weight,
                "description": node.description or "",
                "children": [build_subtree(child) for child in children_nodes],
            }

        # Tìm real root nếu có
        if root_node_id and root_node_id in node_lookup:
            root = node_lookup[root_node_id]
            tree = build_subtree(root)
        else:
            candidates = ctx.get_root_candidates()
            root = candidates[0]
            tree = build_subtree(root)

        # Gom các node chưa được visit (orphans / disconnected components)
        orphans = [n for n in ctx.nodes if n.id not in visited]
        orphans.sort(key=lambda n: -n.importance_weight)

        if orphans:
            # Nếu tree thực sự nhỏ so với tổng nodes → wrap vào virtual root
            if len(orphans) > len(ctx.nodes) * 0.3:  # >30% nodes bị bỏ sót
                virtual_root = {
                    "id": -1,  # sentinel
                    "title": tree.get("title", "Tổng quan"),  # lấy title từ root thật
                    "node_type": "concept",
                    "difficulty_level": "basic",
                    "importance_weight": 10,
                    "description": "Node tổng hợp tự động",
                    "children": [tree] + [build_subtree(o) for o in orphans if o.id not in visited],
                }
                return virtual_root

        return tree


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
                access_logger.warning("LLM thay đổi cấu trúc cây, dùng tree gốc.", extra={"action_code": "MINDMAP"})
                return tree

            access_logger.info(f"[Mindmap] Enriched thành công cho root node id={tree.get('id')}", extra={"action_code": "MINDMAP"})
            access_logger.info(json.dumps(enriched_data, ensure_ascii=False, indent=2), extra={"action_code": "MINDMAP"})
            return enriched_data

        except Exception as e:
            traceback.print_exc()
            error_logger.error(f"[Mindmap] LLM enrichment thất bại: {e}", extra={"action_code": "MINDMAP_ERROR"})
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
            traceback.print_exc()
            error_logger.error(f"[Mindmap] Không thể sinh study order: {e}", extra={"action_code": "MINDMAP_ERROR"})
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
        min_importance: int = 1,
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
            .outerjoin(lesson_knowledge, KnowledgeNode.id == lesson_knowledge.c.knowledge_node_id)
            .filter(
                or_(
                    KnowledgeNode.lesson_id.in_(lesson_ids),
                    lesson_knowledge.c.lesson_id.in_(lesson_ids)
                )
            )
            .distinct()
            .all()
        )

        access_logger.debug(f"[Mindmap Debug] Queried {len(seed_nodes)} seed_nodes for lesson_ids: {lesson_ids}", extra={"action_code": "MINDMAP_DEBUG"})
        access_logger.debug(f"[Mindmap Debug] seed_nodes IDs: {[n.id for n in seed_nodes]}", extra={"action_code": "MINDMAP_DEBUG"})

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
        access_logger.debug(f"[Mindmap Debug] Queried {len(all_edges)} all_edges", extra={"action_code": "MINDMAP_DEBUG"})

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
        access_logger.debug(f"[Mindmap Debug] Queried {len(all_nodes)} neighbor nodes", extra={"action_code": "MINDMAP_DEBUG"})
        node_lookup = {n.id: n for n in all_nodes}
        for n in seed_nodes:
            node_lookup.setdefault(n.id, n)

        access_logger.debug(f"[Mindmap Debug] Calling extractor.extract_for_lessons with {len(seed_nodes)} seed_nodes, {len(all_edges)} edges, {len(node_lookup)} neighbor lookup...", extra={"action_code": "MINDMAP_DEBUG"})
        # ---- Bước 2: BFS Subgraph Extraction ----
        ctx = self.extractor.extract_for_lessons(
            lesson_nodes=seed_nodes,
            all_edges=all_edges,
            all_neighbor_nodes=node_lookup,
            max_depth=max_depth,
            min_importance=min_importance,
            difficulty_filter=difficulty_filter,
        )

        # ---- Bước 2.5: Tìm hoặc tạo virtual root node ----
        # Tìm virtual node đã tồn tại cho lesson này

        existing_virtual = (
            self.db.query(KnowledgeNode)
            .filter(
                KnowledgeNode.node_type == "virtual",
                KnowledgeNode.lesson_id == lesson_ids[0],
                KnowledgeNode.subject_id == seed_nodes[0].subject_id,
                KnowledgeNode.module_id == seed_nodes[0].module_id
            )
            .first()
        )

        if existing_virtual:
            virtual_root_id = existing_virtual.id
            access_logger.info(f"[Mindmap] Dùng virtual root node đã có id={virtual_root_id}",
                               extra={"action_code": "MINDMAP"})
        else:
            virtual_root_node = KnowledgeNode(
                title="Tổng quan",
                node_type="virtual",
                difficulty_level=DifficultyLevel.BASIC,
                importance_weight=10,
                description="Node tổng hợp tự động từ các bài học",
                lesson_id=lesson_ids[0],
                subject_id=seed_nodes[0].subject_id,
                module_id=seed_nodes[0].module_id,
                grade=seed_nodes[0].grade
            )
            self.db.add(virtual_root_node)
            self.db.flush()
            virtual_root_id = virtual_root_node.id
            access_logger.info(f"[Mindmap] Tạo virtual root node mới id={virtual_root_id}",
                               extra={"action_code": "MINDMAP"})

        access_logger.info(
            f"[Mindmap] Subgraph extracted: {ctx.total_nodes} nodes, "
            f"{ctx.total_edges} edges, depth={ctx.max_depth_reached}",
            extra={"action_code": "MINDMAP"}
        )
        # access_logger.info(json.dumps(ctx, ensure_ascii=False, indent=2), extra={"action_code": "MINDMAP"})

        # ---- Bước 3: Graph → Tree ----
        tree = self.tree_builder.build(ctx, root_node_id)

        if not tree:
            raise ValueError("Không thể tạo cây mindmap từ subgraph.")

        # ---- Bước 4: LLM Enrichment (tuỳ chọn) ----
        if enrich_with_llm:
            tree = await self.enricher.enrich(tree, ctx)
            
            # Khựng lại 2s để tránh bị Google API block hoặc 5xx Server Error 
            # do gọi AI liên tục trên gói Free Tier
            await asyncio.sleep(2)
            
            study_order = await self.enricher.generate_study_order(tree, ctx)
        else:
            study_order = []

        # ---- Bước 5: Tạo virtual root node nếu cần ----
        if tree.get("id") == -1:
            tree["id"] = virtual_root_id
            root_node_id_saved = virtual_root_id
        else:
            root_node_id_saved = tree.get("id")

        # ---- Bước 6: Lưu mindmap ----
        structure = {
            "tree": tree,
            "study_order": study_order,
            "metadata": {
                "total_nodes": ctx.total_nodes,
                "total_edges": ctx.total_edges,
                "lesson_ids": lesson_ids,
                "max_depth": max_depth,
                "enriched": enrich_with_llm,
                "has_virtual_root": root_node_id_saved != tree.get("id"),
            }
        }

        mindmap = GeneratedMindmap(
            user_id=user_id,
            root_node_id=root_node_id_saved,
            structure=structure,
        )
        self.db.add(mindmap)
        self.db.commit()  # commit cả virtual_root_node lẫn mindmap
        self.db.refresh(mindmap)

        access_logger.info(f"[Mindmap] Đã lưu GeneratedMindmap id={mindmap.id} cho user_id={user_id}", extra={"action_code": "MINDMAP"})
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