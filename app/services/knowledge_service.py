"""
app/services/knowledge_service.py

Knowledge Graph service — CRUD + graph operations.

BFS Optimization (V6 fix):
  Original: N+1 queries — 1 query per node for edges, 1 per neighbor for node data.
  Optimized: Batch-load edges and nodes per BFS frontier in O(depth) total round-trips.
  Result: ~100+ queries → 2 * depth queries (typically 6–8 for max_depth=3).
"""

from typing import Optional, List, Set, Dict

from fastapi import Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import (
    KnowledgeNode,
    NodeType,
    DifficultyLevel,
    KnowledgeEdge,
    lesson_knowledge,
    GeneratedMindmap,
    Lesson,
)
from app.core.exceptions import ResourceNotFoundException, DuplicateResourceException
from app.schemas.knowledge import (
    KnowledgeNodeCreate,
    KnowledgeNodeUpdate,
    KnowledgeEdgeCreate,
    SubgraphResponse,
)


class KnowledgeService:
    """Service layer for Knowledge Graph operations"""

    def __init__(self, db: Session):
        self.db = db

    # ============================================
    # NODE CRUD
    # ============================================

    def get_node_by_id(self, node_id: int) -> Optional[KnowledgeNode]:
        return self.db.query(KnowledgeNode).filter(KnowledgeNode.id == node_id).first()

    def get_nodes(
        self,
        skip: int = 0,
        limit: int = 100,
        subject_id: Optional[int] = None,
        module_id: Optional[int] = None,
        lesson_id: Optional[int] = None,
        grade: Optional[int] = None,
        node_type: Optional[NodeType] = None,
        difficulty_level: Optional[DifficultyLevel] = None,
        search: Optional[str] = None,
    ) -> List[KnowledgeNode]:
        query = self.db.query(KnowledgeNode)

        if subject_id:
            query = query.filter(KnowledgeNode.subject_id == subject_id)
        if module_id:
            query = query.filter(KnowledgeNode.module_id == module_id)
        if lesson_id:
            query = query.filter(KnowledgeNode.lesson_id == lesson_id)
        if grade:
            query = query.filter(KnowledgeNode.grade == grade)
        if node_type:
            query = query.filter(KnowledgeNode.node_type == node_type)
        if difficulty_level:
            query = query.filter(KnowledgeNode.difficulty_level == difficulty_level)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                KnowledgeNode.title.ilike(pattern)
                | KnowledgeNode.description.ilike(pattern)
            )

        return (
            query.order_by(KnowledgeNode.importance_weight.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create_node(self, data: KnowledgeNodeCreate) -> KnowledgeNode:
        node = KnowledgeNode(**data.model_dump())
        self.db.add(node)
        self.db.commit()
        self.db.refresh(node)
        return node

    def update_node(self, node_id: int, data: KnowledgeNodeUpdate) -> KnowledgeNode:
        node = self.get_node_by_id(node_id)
        if not node:
            raise ResourceNotFoundException("KnowledgeNode", node_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(node, field, value)
        self.db.commit()
        self.db.refresh(node)
        return node

    def delete_node(self, node_id: int) -> None:
        node = self.get_node_by_id(node_id)
        if not node:
            raise ResourceNotFoundException("KnowledgeNode", node_id)
        self.db.delete(node)
        self.db.commit()

    # ============================================
    # EDGE CRUD
    # ============================================

    def get_edge_by_id(self, edge_id: int) -> Optional[KnowledgeEdge]:
        return self.db.query(KnowledgeEdge).filter(KnowledgeEdge.id == edge_id).first()

    def get_edges_for_node(self, node_id: int) -> List[KnowledgeEdge]:
        return (
            self.db.query(KnowledgeEdge)
            .filter(
                (KnowledgeEdge.from_node_id == node_id)
                | (KnowledgeEdge.to_node_id == node_id)
            )
            .all()
        )

    def create_edge(self, data: KnowledgeEdgeCreate) -> KnowledgeEdge:
        # Validate both nodes exist
        for nid in [data.from_node_id, data.to_node_id]:
            if not self.get_node_by_id(nid):
                raise ResourceNotFoundException("KnowledgeNode", nid)

        # Prevent duplicate edges
        existing = (
            self.db.query(KnowledgeEdge)
            .filter(
                KnowledgeEdge.from_node_id == data.from_node_id,
                KnowledgeEdge.to_node_id == data.to_node_id,
                KnowledgeEdge.relation_type == data.relation_type,
            )
            .first()
        )
        if existing:
            raise DuplicateResourceException(
                "KnowledgeEdge", "from_node_id+to_node_id+relation_type", "same edge"
            )

        edge = KnowledgeEdge(**data.model_dump())
        self.db.add(edge)
        self.db.commit()
        self.db.refresh(edge)
        return edge

    def delete_edge(self, edge_id: int) -> None:
        edge = self.get_edge_by_id(edge_id)
        if not edge:
            raise ResourceNotFoundException("KnowledgeEdge", edge_id)
        self.db.delete(edge)
        self.db.commit()

    # ============================================
    # GRAPH OPERATIONS — OPTIMIZED BFS
    # ============================================

    def _batch_load_edges(self, node_ids: Set[int]) -> List[KnowledgeEdge]:
        """
        Batch-load all edges where from_node_id OR to_node_id is in node_ids.
        Single IN-clause query replaces per-node lookups.
        """
        if not node_ids:
            return []
        id_list = list(node_ids)
        return (
            self.db.query(KnowledgeEdge)
            .filter(
                or_(
                    KnowledgeEdge.from_node_id.in_(id_list),
                    KnowledgeEdge.to_node_id.in_(id_list),
                )
            )
            .all()
        )

    def _batch_load_nodes(self, node_ids: Set[int]) -> List[KnowledgeNode]:
        """Batch-load nodes by ID set — single query."""
        if not node_ids:
            return []
        return (
            self.db.query(KnowledgeNode)
            .filter(KnowledgeNode.id.in_(list(node_ids)))
            .all()
        )

    def get_subgraph_for_lessons(
        self,
        lesson_ids: List[int],
        max_depth: int = 3,
        difficulty_filter: Optional[DifficultyLevel] = None,
    ) -> SubgraphResponse:
        """
        Optimized BFS subgraph extraction for given lessons.

        Complexity: O(depth) DB round-trips (was O(nodes * 2)).

        Steps:
        1. Batch-load seed nodes from lesson_knowledge JOIN (1 query)
        2. Per BFS frontier: 1 batch edge query + 1 batch node query
        3. Apply difficulty filter in Python (avoids per-node filter round-trips)
        4. Return deduplicated nodes + edges
        """
        # Step 1: seed nodes (1 query)
        seed_nodes: List[KnowledgeNode] = (
            self.db.query(KnowledgeNode)
            .join(
                lesson_knowledge,
                KnowledgeNode.id == lesson_knowledge.c.knowledge_node_id,
            )
            .filter(lesson_knowledge.c.lesson_id.in_(lesson_ids))
            .all()
        )

        if not seed_nodes:
            return SubgraphResponse(nodes=[], edges=[])

        # Accumulated state
        all_nodes: Dict[int, KnowledgeNode] = {n.id: n for n in seed_nodes}
        all_edges: Dict[int, KnowledgeEdge] = {}
        visited_ids: Set[int] = set(all_nodes.keys())

        # Current frontier: node IDs to expand in this BFS level
        frontier: Set[int] = set(all_nodes.keys())

        for _depth in range(max_depth):
            if not frontier:
                break

            # Batch load all edges touching frontier nodes (1 query per depth level)
            edges = self._batch_load_edges(frontier)
            for edge in edges:
                all_edges[edge.id] = edge

            # Collect neighbor IDs not yet visited
            new_ids: Set[int] = set()
            for edge in edges:
                for neighbor_id in (edge.from_node_id, edge.to_node_id):
                    if neighbor_id not in visited_ids:
                        new_ids.add(neighbor_id)

            if not new_ids:
                break

            # Batch load all neighbor nodes (1 query per depth level)
            neighbors = self._batch_load_nodes(new_ids)
            next_frontier: Set[int] = set()

            for neighbor in neighbors:
                # Apply difficulty filter in-memory
                if difficulty_filter and neighbor.difficulty_level != difficulty_filter:
                    continue
                visited_ids.add(neighbor.id)
                all_nodes[neighbor.id] = neighbor
                next_frontier.add(neighbor.id)

            frontier = next_frontier

        return SubgraphResponse(
            nodes=list(all_nodes.values()),
            edges=list(all_edges.values()),
        )

    def generate_mindmap(
        self,
        user_id: int,
        root_node_id: int,
        max_depth: int = 4,
    ) -> GeneratedMindmap:
        """
        Convert graph → tree structure for mindmap.

        Uses DFS from root node, avoiding cycles.
        Saves result to GeneratedMindmap table.
        """
        root = self.get_node_by_id(root_node_id)
        if not root:
            raise ResourceNotFoundException("KnowledgeNode", root_node_id)

        visited: Set[int] = set()

        def build_tree(node: KnowledgeNode, depth: int) -> Optional[dict]:
            if depth > max_depth or node.id in visited:
                return None
            visited.add(node.id)

            children = []
            for edge in node.outgoing_edges:
                child = edge.to_node
                subtree = build_tree(child, depth + 1)
                if subtree:
                    children.append(subtree)

            return {
                "id": node.id,
                "title": node.title,
                "node_type": node.node_type,
                "difficulty_level": node.difficulty_level,
                "importance_weight": node.importance_weight,
                "children": children,
            }

        structure = build_tree(root, 0)

        mindmap = GeneratedMindmap(
            user_id=user_id,
            root_node_id=root_node_id,
            structure=structure,
        )
        self.db.add(mindmap)
        self.db.commit()
        self.db.refresh(mindmap)
        return mindmap

    def get_mindmaps_for_user(self, user_id: int) -> List[GeneratedMindmap]:
        return (
            self.db.query(GeneratedMindmap)
            .filter(GeneratedMindmap.user_id == user_id)
            .all()
        )

    # ============================================
    # LESSON ↔ NODE LINKING
    # ============================================

    def link_node_to_lesson(self, node_id: int, lesson_id: int) -> dict:
        node = self.get_node_by_id(node_id)
        if not node:
            raise ResourceNotFoundException("KnowledgeNode", node_id)
        lesson = self.db.query(Lesson).filter(Lesson.id == lesson_id).first()
        if not lesson:
            raise ResourceNotFoundException("Lesson", lesson_id)

        if lesson not in node.lessons:
            node.lessons.append(lesson)
            self.db.commit()

        return {"message": f"Node {node_id} linked to lesson {lesson_id}"}

    def unlink_node_from_lesson(self, node_id: int, lesson_id: int) -> dict:
        node = self.get_node_by_id(node_id)
        if not node:
            raise ResourceNotFoundException("KnowledgeNode", node_id)
        lesson = self.db.query(Lesson).filter(Lesson.id == lesson_id).first()
        if not lesson:
            raise ResourceNotFoundException("Lesson", lesson_id)

        if lesson in node.lessons:
            node.lessons.remove(lesson)
            self.db.commit()

        return {"message": f"Node {node_id} unlinked from lesson {lesson_id}"}


# ============================================
# DEPENDENCY
# ============================================


def get_knowledge_service(db: Session = Depends(get_db)) -> KnowledgeService:
    return KnowledgeService(db)
