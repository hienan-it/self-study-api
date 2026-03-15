from fastapi import APIRouter, Depends, Query, status
from typing import List, Optional
from app.models.user import User, UserRole
from app.models.knowledge import NodeType, DifficultyLevel
from app.api.deps import get_current_active_user, get_admin_user, require_any_role
from app.schemas.knowledge import KnowledgeNodeResponse, KnowledgeEdgeResponse, MindmapResponse
from app.services.knowledge_service import (
    KnowledgeService, get_knowledge_service,
    KnowledgeNodeCreate, KnowledgeNodeUpdate, KnowledgeEdgeCreate, SubgraphResponse,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

get_teacher_or_admin = require_any_role([UserRole.TEACHER, UserRole.ADMIN])


# ============================================
# KNOWLEDGE NODES
# ============================================

@router.get("/nodes", response_model=List[KnowledgeNodeResponse])
async def list_nodes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    subject_id: Optional[int] = Query(None),
    module_id: Optional[int] = Query(None),
    lesson_id: Optional[int] = Query(None),
    grade: Optional[int] = Query(None),
    node_type: Optional[NodeType] = Query(None),
    difficulty_level: Optional[DifficultyLevel] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(get_current_active_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """List knowledge nodes with filters. Accessible by all authenticated users."""
    return svc.get_nodes(
        skip=skip, limit=limit,
        subject_id=subject_id, module_id=module_id, lesson_id=lesson_id,
        grade=grade, node_type=node_type, difficulty_level=difficulty_level,
        search=search,
    )


@router.get("/nodes/{node_id}", response_model=KnowledgeNodeResponse)
async def get_node(
    node_id: int,
    current_user: User = Depends(get_current_active_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    from fastapi import HTTPException
    node = svc.get_node_by_id(node_id)
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Node {node_id} not found")
    return node


@router.post("/nodes", response_model=KnowledgeNodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(
    data: KnowledgeNodeCreate,
    current_user: User = Depends(get_teacher_or_admin),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Create a knowledge node. Requires Teacher or Admin."""
    return svc.create_node(data)


@router.patch("/nodes/{node_id}", response_model=KnowledgeNodeResponse)
async def update_node(
    node_id: int,
    data: KnowledgeNodeUpdate,
    current_user: User = Depends(get_teacher_or_admin),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Update a knowledge node. Requires Teacher or Admin."""
    return svc.update_node(node_id, data)


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: int,
    current_user: User = Depends(get_admin_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Delete a knowledge node. Admin only."""
    svc.delete_node(node_id)


# ============================================
# LESSON ↔ NODE LINKING
# ============================================

@router.post("/nodes/{node_id}/lessons/{lesson_id}", status_code=status.HTTP_200_OK)
async def link_to_lesson(
    node_id: int,
    lesson_id: int,
    current_user: User = Depends(get_teacher_or_admin),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Link a knowledge node to a lesson."""
    return svc.link_node_to_lesson(node_id, lesson_id)


@router.delete("/nodes/{node_id}/lessons/{lesson_id}", status_code=status.HTTP_200_OK)
async def unlink_from_lesson(
    node_id: int,
    lesson_id: int,
    current_user: User = Depends(get_teacher_or_admin),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Unlink a knowledge node from a lesson."""
    return svc.unlink_node_from_lesson(node_id, lesson_id)


# ============================================
# KNOWLEDGE EDGES
# ============================================

@router.get("/nodes/{node_id}/edges", response_model=List[KnowledgeEdgeResponse])
async def get_node_edges(
    node_id: int,
    current_user: User = Depends(get_current_active_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Get all edges for a knowledge node."""
    return svc.get_edges_for_node(node_id)


@router.post("/edges", response_model=KnowledgeEdgeResponse, status_code=status.HTTP_201_CREATED)
async def create_edge(
    data: KnowledgeEdgeCreate,
    current_user: User = Depends(get_teacher_or_admin),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Create an edge between two knowledge nodes. Requires Teacher or Admin."""
    return svc.create_edge(data)


@router.delete("/edges/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(
    edge_id: int,
    current_user: User = Depends(get_admin_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Delete a knowledge edge. Admin only."""
    svc.delete_edge(edge_id)


# ============================================
# GRAPH OPERATIONS
# ============================================

@router.post("/subgraph", response_model=SubgraphResponse)
async def extract_subgraph(
    lesson_ids: List[int],
    max_depth: int = Query(default=3, ge=1, le=6),
    difficulty_filter: Optional[DifficultyLevel] = Query(None),
    current_user: User = Depends(get_current_active_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """
    BFS subgraph extraction from lessons.
    Returns all related knowledge nodes and edges up to max_depth hops.
    """
    return svc.get_subgraph_for_lessons(lesson_ids, max_depth, difficulty_filter)


@router.post("/mindmap/{root_node_id}", response_model=MindmapResponse)
async def generate_mindmap(
    root_node_id: int,
    max_depth: int = Query(default=4, ge=1, le=6),
    current_user: User = Depends(get_current_active_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """
    Generate and save a mindmap tree rooted at a knowledge node.
    Converts graph → tree via DFS.
    """
    return svc.generate_mindmap(current_user.id, root_node_id, max_depth)


@router.get("/mindmaps/me", response_model=List[MindmapResponse])
async def my_mindmaps(
    current_user: User = Depends(get_current_active_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Get all mindmaps generated by the current user."""
    return svc.get_mindmaps_for_user(current_user.id)