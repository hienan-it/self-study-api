from collections import deque
from typing import Optional, List, Set, Dict

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import KnowledgeNode, NodeType, DifficultyLevel, KnowledgeEdge, lesson_knowledge, GeneratedMindmap, \
    Lesson
from app.schemas.knowledge import KnowledgeNodeCreate, KnowledgeNodeUpdate, KnowledgeEdgeCreate, SubgraphResponse


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
                KnowledgeNode.title.ilike(pattern) |
                KnowledgeNode.description.ilike(pattern)
            )

        return query.order_by(KnowledgeNode.importance_weight.desc()).offset(skip).limit(limit).all()

    def create_node(self, data: KnowledgeNodeCreate) -> KnowledgeNode:
        node = KnowledgeNode(**data.model_dump())
        self.db.add(node)
        self.db.commit()
        self.db.refresh(node)
        return node

    def update_node(self, node_id: int, data: KnowledgeNodeUpdate) -> KnowledgeNode:
        node = self.get_node_by_id(node_id)
        if not node:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Node {node_id} not found")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(node, field, value)
        self.db.commit()
        self.db.refresh(node)
        return node

    def delete_node(self, node_id: int) -> None:
        node = self.get_node_by_id(node_id)
        if not node:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Node {node_id} not found")
        self.db.delete(node)
        self.db.commit()

    # ============================================
    # EDGE CRUD
    # ============================================

    def get_edge_by_id(self, edge_id: int) -> Optional[KnowledgeEdge]:
        return self.db.query(KnowledgeEdge).filter(KnowledgeEdge.id == edge_id).first()

    def get_edges_for_node(self, node_id: int) -> List[KnowledgeEdge]:
        return self.db.query(KnowledgeEdge).filter(
            (KnowledgeEdge.from_node_id == node_id) |
            (KnowledgeEdge.to_node_id == node_id)
        ).all()

    def create_edge(self, data: KnowledgeEdgeCreate) -> KnowledgeEdge:
        # Validate both nodes exist
        for nid in [data.from_node_id, data.to_node_id]:
            if not self.get_node_by_id(nid):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Node {nid} not found")

        # Prevent duplicate edges
        existing = self.db.query(KnowledgeEdge).filter(
            KnowledgeEdge.from_node_id == data.from_node_id,
            KnowledgeEdge.to_node_id == data.to_node_id,
            KnowledgeEdge.relation_type == data.relation_type,
        ).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Edge already exists")

        edge = KnowledgeEdge(**data.model_dump())
        self.db.add(edge)
        self.db.commit()
        self.db.refresh(edge)
        return edge

    def delete_edge(self, edge_id: int) -> None:
        edge = self.get_edge_by_id(edge_id)
        if not edge:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Edge {edge_id} not found")
        self.db.delete(edge)
        self.db.commit()

    # ============================================
    # GRAPH OPERATIONS
    # ============================================

    def get_subgraph_for_lessons(
            self,
            lesson_ids: List[int],
            max_depth: int = 3,
            difficulty_filter: Optional[DifficultyLevel] = None,
    ) -> SubgraphResponse:
        """
        BFS subgraph extraction for given lessons.

        Steps:
        1. Find all KnowledgeNodes linked to the lessons (via lesson_knowledge table)
        2. BFS outward through KnowledgeEdges up to max_depth
        3. Optionally filter by difficulty
        4. Return nodes + edges forming the subgraph
        """
        # Step 1: Seed nodes from lessons
        seed_nodes: List[KnowledgeNode] = (
            self.db.query(KnowledgeNode)
            .join(lesson_knowledge, KnowledgeNode.id == lesson_knowledge.c.knowledge_node_id)
            .filter(lesson_knowledge.c.lesson_id.in_(lesson_ids))
            .all()
        )

        if not seed_nodes:
            return SubgraphResponse(nodes=[], edges=[])

        # Step 2: BFS expansion
        visited_ids: Set[int] = set()
        queue: deque = deque()

        for node in seed_nodes:
            visited_ids.add(node.id)
            queue.append((node, 0))

        all_nodes: Dict[int, KnowledgeNode] = {n.id: n for n in seed_nodes}
        all_edges: Dict[int, KnowledgeEdge] = {}

        while queue:
            current_node, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # Traverse outgoing + incoming edges
            edges = self.get_edges_for_node(current_node.id)
            for edge in edges:
                all_edges[edge.id] = edge
                neighbor_id = edge.to_node_id if edge.from_node_id == current_node.id else edge.from_node_id

                if neighbor_id not in visited_ids:
                    neighbor = self.get_node_by_id(neighbor_id)
                    if neighbor:
                        # Apply difficulty filter if set
                        if difficulty_filter and neighbor.difficulty_level != difficulty_filter:
                            continue
                        visited_ids.add(neighbor_id)
                        all_nodes[neighbor_id] = neighbor
                        queue.append((neighbor, depth + 1))

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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Root node {root_node_id} not found")

        visited: Set[int] = set()

        def build_tree(node: KnowledgeNode, depth: int) -> dict:
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
        return self.db.query(GeneratedMindmap).filter(GeneratedMindmap.user_id == user_id).all()

    # ============================================
    # LESSON ↔ NODE LINKING
    # ============================================

    def link_node_to_lesson(self, node_id: int, lesson_id: int) -> dict:
        node = self.get_node_by_id(node_id)
        if not node:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Node {node_id} not found")
        lesson = self.db.query(Lesson).filter(Lesson.id == lesson_id).first()
        if not lesson:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Lesson {lesson_id} not found")

        if lesson not in node.lessons:
            node.lessons.append(lesson)
            self.db.commit()

        return {"message": f"Node {node_id} linked to lesson {lesson_id}"}

    def unlink_node_from_lesson(self, node_id: int, lesson_id: int) -> dict:
        node = self.get_node_by_id(node_id)
        if not node:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Node {node_id} not found")
        lesson = self.db.query(Lesson).filter(Lesson.id == lesson_id).first()
        if not lesson:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Lesson {lesson_id} not found")

        if lesson in node.lessons:
            node.lessons.remove(lesson)
            self.db.commit()

        return {"message": f"Node {node_id} unlinked from lesson {lesson_id}"}


# ============================================
# DEPENDENCY
# ============================================

def get_knowledge_service(db: Session = Depends(get_db)) -> KnowledgeService:
    return KnowledgeService(db)