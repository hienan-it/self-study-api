"""
app/ai/graph_rag.py

GraphRAG Context Builder — trái tim của hệ thống.

Nguyên lý hoạt động:
  Graph (KnowledgeNodes + KnowledgeEdges)
       ↓
  Subgraph Extraction (BFS + Filter)
       ↓
  Context Serialization (Graph → Text/JSON cho LLM)
       ↓
  LLM chỉ được sinh nội dung DỰA TRÊN graph context này
  (không hallucinate kiến thức ngoài graph)

Đây là phần "RAG" trong GraphRAG:
  thay vì dùng vector similarity search,
  ta dùng graph traversal để lấy context.
"""

from typing import List, Optional, Dict, Set
from collections import deque
from dataclasses import dataclass

from app.db.models.knowledge import KnowledgeNode, KnowledgeEdge, DifficultyLevel, RelationType


# ============================================
# DATA STRUCTURES
# ============================================

@dataclass
class GraphContext:
    """
    Context đã được extract từ knowledge graph.
    Dùng làm input cho mindmap_generator và exam_generator.
    """
    nodes: List[KnowledgeNode]
    edges: List[KnowledgeEdge]

    # Thống kê để log / debug
    total_nodes: int = 0
    total_edges: int = 0
    max_depth_reached: int = 0

    def __post_init__(self):
        self.total_nodes = len(self.nodes)
        self.total_edges = len(self.edges)

    def is_empty(self) -> bool:
        return self.total_nodes == 0

    def get_node_by_id(self, node_id: int) -> Optional[KnowledgeNode]:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def get_edges_for_node(self, node_id: int) -> List[KnowledgeEdge]:
        return [
            e for e in self.edges
            if e.from_node_id == node_id or e.to_node_id == node_id
        ]

    def get_children(self, node_id: int) -> List[KnowledgeNode]:
        """Lấy các node mà node_id trỏ tới (outgoing edges)."""
        child_ids = [e.to_node_id for e in self.edges if e.from_node_id == node_id]
        return [n for n in self.nodes if n.id in child_ids]

    def get_root_candidates(self) -> List[KnowledgeNode]:
        """
        Node nào không có incoming edge trong subgraph → candidate làm root cho mindmap.
        Nếu có nhiều, chọn node có importance_weight cao nhất.
        """
        has_incoming = {e.to_node_id for e in self.edges}
        candidates = [n for n in self.nodes if n.id not in has_incoming]

        if not candidates:
            # Fallback: node quan trọng nhất
            candidates = self.nodes

        return sorted(candidates, key=lambda n: n.importance_weight, reverse=True)


# ============================================
# SUBGRAPH EXTRACTOR
# ============================================

class SubgraphExtractor:
    """
    BFS-based subgraph extraction từ knowledge graph.

    Thuật toán:
    1. Seed từ các lesson_ids → lấy tất cả KnowledgeNode linked
    2. BFS mở rộng qua KnowledgeEdge đến max_depth
    3. Filter theo difficulty, importance_weight, grade
    4. Trả về GraphContext chứa nodes + edges của subgraph
    """

    def extract_for_lessons(
        self,
        lesson_nodes: List[KnowledgeNode],   # Nodes từ lesson (đã query từ DB)
        all_edges: List[KnowledgeEdge],       # Tất cả edges liên quan (đã query từ DB)
        all_neighbor_nodes: Dict[int, KnowledgeNode],  # Lookup node by ID
        max_depth: int = 3,
        min_importance: int = 1,
        difficulty_filter: Optional[DifficultyLevel] = None,
        grade_filter: Optional[int] = None,
    ) -> GraphContext:
        """
        Extract subgraph bằng BFS từ seed nodes.

        Args:
            lesson_nodes: Các KnowledgeNode gắn với lessons đã chọn
            all_edges: Tất cả edges liên quan đến các nodes trong graph
            all_neighbor_nodes: Dict[node_id → KnowledgeNode] để lookup nhanh
            max_depth: Số bước BFS tối đa (depth 2–3 là hợp lý)
            min_importance: Chỉ lấy node có importance_weight >= giá trị này
            difficulty_filter: Chỉ lấy node có difficulty nhất định
            grade_filter: Chỉ lấy node cùng khối lớp

        Returns:
            GraphContext với nodes và edges của subgraph
        """
        if not lesson_nodes:
            return GraphContext(nodes=[], edges=[])

        # Build edge lookup: node_id → list of edges
        edge_map: Dict[int, List[KnowledgeEdge]] = {}
        for edge in all_edges:
            edge_map.setdefault(edge.from_node_id, []).append(edge)
            edge_map.setdefault(edge.to_node_id, []).append(edge)

        # BFS
        visited_ids: Set[int] = set()
        selected_nodes: Dict[int, KnowledgeNode] = {}
        selected_edge_ids: Set[int] = set()
        selected_edges: List[KnowledgeEdge] = []
        max_depth_reached = 0

        queue: deque = deque()

        # Seed: các node từ lesson đã chọn
        for node in lesson_nodes:
            if self._passes_filter(node, min_importance, difficulty_filter, grade_filter):
                visited_ids.add(node.id)
                selected_nodes[node.id] = node
                queue.append((node, 0))

        while queue:
            current, depth = queue.popleft()
            max_depth_reached = max(max_depth_reached, depth)

            if depth >= max_depth:
                continue

            for edge in edge_map.get(current.id, []):
                neighbor_id = edge.to_node_id if edge.from_node_id == current.id else edge.from_node_id
                neighbor = all_neighbor_nodes.get(neighbor_id)

                if neighbor is None:
                    continue

                # Thêm edge nếu cả 2 đầu đều nằm trong subgraph hoặc sẽ được thêm
                if edge.id not in selected_edge_ids:
                    selected_edge_ids.add(edge.id)
                    selected_edges.append(edge)

                if neighbor_id not in visited_ids:
                    if self._passes_filter(neighbor, min_importance, difficulty_filter, grade_filter):
                        visited_ids.add(neighbor_id)
                        selected_nodes[neighbor_id] = neighbor
                        queue.append((neighbor, depth + 1))

        # Chỉ giữ edges có cả 2 đầu trong subgraph
        final_edges = [
            e for e in selected_edges
            if e.from_node_id in selected_nodes and e.to_node_id in selected_nodes
        ]

        ctx = GraphContext(
            nodes=list(selected_nodes.values()),
            edges=final_edges,
        )
        ctx.max_depth_reached = max_depth_reached
        return ctx

    def _passes_filter(
        self,
        node: KnowledgeNode,
        min_importance: int,
        difficulty_filter: Optional[DifficultyLevel],
        grade_filter: Optional[int],
    ) -> bool:
        if node.importance_weight < min_importance:
            return False
        if difficulty_filter and node.difficulty_level != difficulty_filter:
            return False
        if grade_filter and node.grade != grade_filter:
            return False
        return True


# ============================================
# CONTEXT SERIALIZER
# ============================================

class GraphContextSerializer:
    """
    Chuyển GraphContext thành text/JSON để đưa vào LLM prompt.

    LLM nhận context này và BỊ RÀNG BUỘC chỉ dùng thông tin
    có trong context — không được bịa thêm kiến thức.
    """

    def to_prompt_text(self, ctx: GraphContext) -> str:
        """
        Serialize thành plain text cho LLM prompt.
        Format dễ đọc, tối ưu token.

        Ví dụ output:
            === KNOWLEDGE GRAPH CONTEXT ===
            [Node #1] Định lý Pythagore (concept, basic, độ quan trọng: 9)
            Mô tả: Trong tam giác vuông, bình phương cạnh huyền...
            Liên kết: → Tam giác vuông [prerequisite] | → Căn bậc hai [builds_on]

            [Node #2] ...
        """
        if ctx.is_empty():
            return "Không có dữ liệu knowledge graph."

        lines = ["=== NGỮ CẢNH KNOWLEDGE GRAPH ===\n"]

        # Tạo lookup edge theo node
        node_edges: Dict[int, List[KnowledgeEdge]] = {}
        for edge in ctx.edges:
            node_edges.setdefault(edge.from_node_id, []).append(edge)

        # Map node_id → title để hiển thị tên trong phần liên kết
        id_to_title = {n.id: n.title for n in ctx.nodes}

        for node in sorted(ctx.nodes, key=lambda n: -n.importance_weight):
            lines.append(
                f"[Node #{node.id}] {node.title} "
                f"(loại: {node.node_type}, độ khó: {node.difficulty_level}, "
                f"độ quan trọng: {node.importance_weight}/10)"
            )
            if node.description:
                lines.append(f"  Mô tả: {node.description}")

            # Các mối quan hệ outgoing
            outgoing = node_edges.get(node.id, [])
            if outgoing:
                rel_parts = []
                for edge in outgoing:
                    target_title = id_to_title.get(edge.to_node_id, f"Node #{edge.to_node_id}")
                    rel_parts.append(f"→ {target_title} [{edge.relation_type}]")
                lines.append(f"  Liên kết: {' | '.join(rel_parts)}")

            lines.append("")

        lines.append(f"Tổng: {ctx.total_nodes} nodes, {ctx.total_edges} edges\n")
        return "\n".join(lines)

    def to_node_list_json(self, ctx: GraphContext) -> List[dict]:
        """
        Serialize nodes thành list of dict — dùng trong exam generation prompt.
        Gọn hơn to_prompt_text, tối ưu token hơn.
        """
        return [
            {
                "id": n.id,
                "title": n.title,
                "description": n.description or "",
                "node_type": n.node_type,
                "difficulty_level": n.difficulty_level,
                "importance_weight": n.importance_weight,
            }
            for n in sorted(ctx.nodes, key=lambda n: -n.importance_weight)
        ]

    def to_adjacency_summary(self, ctx: GraphContext) -> str:
        """
        Tóm tắt cấu trúc đồ thị dạng ngắn gọn.
        Dùng để debug hoặc thêm vào prompt như metadata.
        """
        if ctx.is_empty():
            return "Graph rỗng."

        difficulty_counts: Dict[str, int] = {}
        type_counts: Dict[str, int] = {}

        for n in ctx.nodes:
            difficulty_counts[n.difficulty_level] = difficulty_counts.get(n.difficulty_level, 0) + 1
            type_counts[n.node_type] = type_counts.get(n.node_type, 0) + 1

        diff_str = ", ".join(f"{k}: {v}" for k, v in difficulty_counts.items())
        type_str = ", ".join(f"{k}: {v}" for k, v in type_counts.items())

        return (
            f"Subgraph: {ctx.total_nodes} nodes ({diff_str}) | "
            f"Loại node: {type_str} | "
            f"Số quan hệ: {ctx.total_edges}"
        )


# ============================================
# FACTORY — tạo extractor + serializer
# ============================================

def create_graph_rag() -> tuple[SubgraphExtractor, GraphContextSerializer]:
    """Trả về (extractor, serializer) đã khởi tạo."""
    return SubgraphExtractor(), GraphContextSerializer()