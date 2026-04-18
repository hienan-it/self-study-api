"""
app/ai/mindmap_generator.py

Mindmap Generator — Graph → Tree + LLM enrichment.

Pipeline:
  GraphContext (nodes + edges)
       ↓
  BFS Spanning Tree (loại bỏ chu trình, giữ cấu trúc cây)
       ↓
  LLM Enrichment (có cache: check DB trước, chỉ gọi LLM cho node chưa có)
       ↓
  JSON Mindmap (lưu vào GeneratedMindmap)
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
from app.db.models.knowledge import KnowledgeNode, KnowledgeEdge, KnowledgeNodeEnrichment, DifficultyLevel
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
# LLM ENRICHMENT (with DB cache)
# ============================================

class MindmapLLMEnricher:
    """
    Enrich mindmap tree theo batch nhỏ (2 nodes/batch).

    Cache-aside pattern:
      - Trước khi gọi LLM → check bảng knowledge_node_enrichments
      - Node đã có enrichment → lấy từ DB, không gọi LLM
      - Node chưa có → gọi LLM → lưu vào DB để dùng lại lần sau

    Lợi ích:
      - Lần đầu generate mindmap → gọi LLM bình thường
      - Từ lần 2 trở đi → 0 LLM call, trả về ngay từ DB
      - Nhiều user học cùng lesson → chỉ enrich 1 lần
    """

    def __init__(self, llm_client: LLMClient, db: DBSession):
        self.llm = llm_client
        self.db = db
        self.serializer = GraphContextSerializer()

    # ============================================
    # CACHE HELPERS
    # ============================================

    def _load_cached_enrichments(self, node_ids: List[int]) -> Dict[int, KnowledgeNodeEnrichment]:
        """
        Batch-load enrichments đã có trong DB.

        Returns:
            Dict[node_id → KnowledgeNodeEnrichment]
        """
        if not node_ids:
            return {}
        rows = (
            self.db.query(KnowledgeNodeEnrichment)
            .filter(KnowledgeNodeEnrichment.knowledge_node_id.in_(node_ids))
            .all()
        )
        return {row.knowledge_node_id: row for row in rows}

    def _save_enrichments(self, enrichment_data: List[dict]) -> None:
        """
        Bulk insert enrichments mới vào DB.

        Args:
            enrichment_data: List[{knowledge_node_id, learning_note, ...}]
        """
        for item in enrichment_data:
            self.db.add(KnowledgeNodeEnrichment(
                knowledge_node_id=item["knowledge_node_id"],
                learning_note=item.get("learning_note", ""),
                memory_tip=item.get("memory_tip", ""),
                key_formula=item.get("key_formula", ""),
                difficulty_note=item.get("difficulty_note", ""),
            ))
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            error_logger.error(
                f"[Mindmap] Lưu enrichment cache thất bại: {e}",
                extra={"action_code": "MINDMAP_ERROR"}
            )

    def _enrichment_to_dict(self, enrichment: KnowledgeNodeEnrichment) -> dict:
        return {
            "learning_note":  enrichment.learning_note  or "",
            "memory_tip":     enrichment.memory_tip     or "",
            "key_formula":    enrichment.key_formula    or "",
            "difficulty_note": enrichment.difficulty_note or "",
        }

    # ============================================
    # TREE HELPERS
    # ============================================

    def _flatten_tree(self, node: dict) -> List[dict]:
        result = [node]
        for child in node.get("children", []):
            result.extend(self._flatten_tree(child))
        return result

    def _rebuild_tree(self, node: dict, enriched_map: Dict[int, dict]) -> dict:
        enriched = enriched_map.get(node["id"], node).copy()
        enriched["children"] = [
            self._rebuild_tree(child, enriched_map)
            for child in node.get("children", [])
        ]
        return enriched

    # ============================================
    # LLM BATCH CALL
    # ============================================

    async def _call_llm_for_batch(self, batch: List[dict], ctx: GraphContext) -> Dict[int, dict]:
        """
        Gọi LLM để enrich một batch nodes. Không liên quan đến cache.

        Returns:
            Dict[node_id → {learning_note, memory_tip, key_formula, difficulty_note}]
        """
        nodes_info = []
        for node in batch:
            ctx_node = ctx.get_node_by_id(node["id"])
            description = ctx_node.description if ctx_node else node.get("description", "")
            nodes_info.append({
                "id": node["id"],
                "title": node["title"],
                "node_type": node["node_type"],
                "difficulty_level": node["difficulty_level"],
                "description": description,
            })

        nodes_json = json.dumps(nodes_info, ensure_ascii=False, indent=2)

        system_prompt = """Bạn là trợ lý giáo dục thông minh chuyên hỗ trợ học sinh Việt Nam.
Viết bằng tiếng Việt, ngắn gọn, dễ hiểu. CHỈ dùng thông tin được cung cấp, không bịa thêm."""

        user_prompt = f"""Dưới đây là danh sách các node kiến thức cần làm phong phú:

{nodes_json}

Hãy thêm các trường sau cho MỖI node và trả về JSON theo format:
{{
  "results": [
    {{
      "id": <node_id>,
      "learning_note": "Ghi chú học tập 1–2 câu, giải thích đơn giản cho học sinh",
      "memory_tip": "Mẹo ghi nhớ sáng tạo (câu thơ, viết tắt, liên tưởng hình ảnh)",
      "key_formula": "Công thức/định nghĩa quan trọng nhất (để trống nếu không có)",
      "difficulty_note": "1 câu về tại sao node này khó/dễ"
    }}
  ]
}}

Trả về đúng {len(batch)} phần tử trong results, theo đúng thứ tự id."""

        result = await self.llm.complete_json_fast(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.4,
            max_tokens=8000,
        )

        return {
            item["id"]: {
                "learning_note":  item.get("learning_note", ""),
                "memory_tip":     item.get("memory_tip", ""),
                "key_formula":    item.get("key_formula", ""),
                "difficulty_note": item.get("difficulty_note", ""),
            }
            for item in result.get("results", [])
            if item.get("id") is not None
        }

    # ============================================
    # BATCH WITH CACHE-ASIDE
    # ============================================

    async def _enrich_batch(self, batch: List[dict], ctx: GraphContext) -> Dict[int, dict]:
        """
        Cache-aside logic cho 1 batch:
          1. Tách hit (đã có trong DB) / miss (chưa có)
          2. Miss → gọi LLM → lưu DB
          3. Merge tất cả lại

        Virtual nodes (id < 0) bỏ qua cache, không lưu DB.

        Returns:
            Dict[node_id → enriched_node_dict]
        """
        # Virtual nodes không cache
        real_nodes  = [n for n in batch if n["id"] > 0]
        virtual_nodes = [n for n in batch if n["id"] <= 0]

        # ---- Step 1: Check cache ----
        cached = self._load_cached_enrichments([n["id"] for n in real_nodes])
        hit_ids   = set(cached.keys())
        miss_nodes = [n for n in real_nodes if n["id"] not in hit_ids]

        access_logger.info(
            f"[Mindmap] Cache check — hit: {sorted(hit_ids)}, "
            f"miss: {[n['id'] for n in miss_nodes]}, "
            f"virtual: {[n['id'] for n in virtual_nodes]}",
            extra={"action_code": "MINDMAP"}
        )

        enriched_map: Dict[int, dict] = {}

        # ---- Step 2: Merge cache hits ----
        for node in real_nodes:
            if node["id"] in hit_ids:
                enriched_map[node["id"]] = {**node, **self._enrichment_to_dict(cached[node["id"]])}

        # ---- Step 3: LLM call cho miss + virtual ----
        llm_targets = miss_nodes + virtual_nodes
        if llm_targets:
            try:
                llm_results = await self._call_llm_for_batch(llm_targets, ctx)

                # Lưu cache chỉ cho miss nodes (không lưu virtual)
                to_save = [
                    {"knowledge_node_id": n["id"], **llm_results[n["id"]]}
                    for n in miss_nodes
                    if n["id"] in llm_results
                ]
                if to_save:
                    self._save_enrichments(to_save)
                    access_logger.info(
                        f"[Mindmap] Đã cache {len(to_save)} enrichments mới vào DB",
                        extra={"action_code": "MINDMAP"}
                    )

                # Merge kết quả LLM
                for node in llm_targets:
                    enriched_map[node["id"]] = {**node, **llm_results.get(node["id"], {})}

            except Exception as e:
                traceback.print_exc()
                error_logger.error(
                    f"[Mindmap] LLM batch thất bại (nodes={[n['id'] for n in llm_targets]}): {e}",
                    extra={"action_code": "MINDMAP_ERROR"}
                )
                # Fallback: giữ nguyên node gốc
                for node in llm_targets:
                    enriched_map[node["id"]] = node

        return enriched_map

    # ============================================
    # MAIN ENRICH
    # ============================================

    async def enrich(self, tree: dict, ctx: GraphContext) -> dict:
        """
        Enrich toàn bộ mindmap tree với cache-aside + batch LLM.

        Sleep chỉ xảy ra giữa các batch — nếu toàn bộ là cache hit
        thì vẫn sleep (đơn giản, an toàn với Free Tier).
        """
        if not tree:
            return tree

        BATCH_SIZE = 2
        SLEEP_BETWEEN_BATCHES = 2

        all_nodes = self._flatten_tree(tree)
        total_batches = (len(all_nodes) + BATCH_SIZE - 1) // BATCH_SIZE

        access_logger.info(
            f"[Mindmap] Bắt đầu enrich {len(all_nodes)} nodes "
            f"({total_batches} batches, size={BATCH_SIZE})",
            extra={"action_code": "MINDMAP"}
        )

        enriched_map: Dict[int, dict] = {}

        for i in range(0, len(all_nodes), BATCH_SIZE):
            batch = all_nodes[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1

            access_logger.info(
                f"[Mindmap] Batch {batch_num}/{total_batches} "
                f"(node ids: {[n['id'] for n in batch]})",
                extra={"action_code": "MINDMAP"}
            )

            batch_result = await self._enrich_batch(batch, ctx)
            enriched_map.update(batch_result)

            if i + BATCH_SIZE < len(all_nodes):
                await asyncio.sleep(SLEEP_BETWEEN_BATCHES)

        enriched_tree = self._rebuild_tree(tree, enriched_map)

        access_logger.info(
            f"[Mindmap] Enrich hoàn tất: {len(enriched_map)}/{len(all_nodes)} nodes processed",
            extra={"action_code": "MINDMAP"}
        )
        return enriched_tree

    async def generate_study_order(self, tree: dict, ctx: GraphContext) -> List[str]:
        """Sinh thứ tự học tập tối ưu dựa trên cấu trúc graph."""
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
        self.enricher = MindmapLLMEnricher(llm_client, db)  # db truyền vào để cache
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

        all_nodes_list: List[KnowledgeNode] = (
            self.db.query(KnowledgeNode)
            .filter(KnowledgeNode.id.in_(neighbor_ids))
            .all()
        )
        access_logger.debug(f"[Mindmap Debug] Queried {len(all_nodes_list)} neighbor nodes",
                            extra={"action_code": "MINDMAP_DEBUG"})
        node_lookup = {n.id: n for n in all_nodes_list}
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
        self.db.commit()
        self.db.refresh(mindmap)

        access_logger.info(
            f"[Mindmap] Đã lưu GeneratedMindmap id={mindmap.id} cho user_id={user_id}",
            extra={"action_code": "MINDMAP"}
        )
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