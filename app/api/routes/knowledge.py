from fastapi import APIRouter, Depends, Query, status
from typing import List, Optional
from app.db.models.user import User, UserRole
from app.db.models.knowledge import NodeType, DifficultyLevel
from app.api.deps import get_current_active_user, get_admin_user, require_any_role
from app.schemas.knowledge import (
    KnowledgeNodeResponse, KnowledgeEdgeResponse, MindmapResponse, SubgraphResponse
)
from app.core.responses import success_response
from app.core.exceptions import ResourceNotFoundException
from app.services.knowledge_service import (
    KnowledgeService, get_knowledge_service,
    KnowledgeNodeCreate, KnowledgeNodeUpdate, KnowledgeEdgeCreate,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

get_teacher_or_admin = require_any_role([UserRole.TEACHER, UserRole.ADMIN])


# ============================================
# KNOWLEDGE NODES
# ============================================

@router.get("/nodes", response_model=None)
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
    nodes = svc.get_nodes(
        skip=skip, limit=limit,
        subject_id=subject_id, module_id=module_id, lesson_id=lesson_id,
        grade=grade, node_type=node_type, difficulty_level=difficulty_level,
        search=search,
    )
    return success_response([KnowledgeNodeResponse.model_validate(n).model_dump(by_alias=True) for n in nodes])


@router.get("/nodes/{node_id}", response_model=None)
async def get_node(
    node_id: int,
    current_user: User = Depends(get_current_active_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Get a single knowledge node by ID."""
    node = svc.get_node_by_id(node_id)
    if not node:
        raise ResourceNotFoundException("KnowledgeNode", node_id)
    return success_response(KnowledgeNodeResponse.model_validate(node).model_dump(by_alias=True))


@router.post("/nodes", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_node(
    data: KnowledgeNodeCreate,
    current_user: User = Depends(get_teacher_or_admin),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Create a knowledge node. Requires Teacher or Admin."""
    node = svc.create_node(data)
    return success_response(KnowledgeNodeResponse.model_validate(node).model_dump(by_alias=True))


@router.patch("/nodes/{node_id}", response_model=None)
async def update_node(
    node_id: int,
    data: KnowledgeNodeUpdate,
    current_user: User = Depends(get_teacher_or_admin),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Update a knowledge node. Requires Teacher or Admin."""
    node = svc.update_node(node_id, data)
    return success_response(KnowledgeNodeResponse.model_validate(node).model_dump(by_alias=True))


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: int,
    current_user: User = Depends(get_admin_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Delete a knowledge node. Admin only."""
    svc.delete_node(node_id)
    return None


# ============================================
# LESSON ↔ NODE LINKING
# ============================================

@router.post("/nodes/{node_id}/lessons/{lesson_id}", response_model=None, status_code=status.HTTP_200_OK)
async def link_to_lesson(
    node_id: int,
    lesson_id: int,
    current_user: User = Depends(get_teacher_or_admin),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Link a knowledge node to a lesson."""
    result = svc.link_node_to_lesson(node_id, lesson_id)
    return success_response(result)


@router.delete("/nodes/{node_id}/lessons/{lesson_id}", response_model=None, status_code=status.HTTP_200_OK)
async def unlink_from_lesson(
    node_id: int,
    lesson_id: int,
    current_user: User = Depends(get_teacher_or_admin),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Unlink a knowledge node from a lesson."""
    result = svc.unlink_node_from_lesson(node_id, lesson_id)
    return success_response(result)


# ============================================
# KNOWLEDGE EDGES
# ============================================

@router.get("/nodes/{node_id}/edges", response_model=None)
async def get_node_edges(
    node_id: int,
    current_user: User = Depends(get_current_active_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Get all edges for a knowledge node."""
    edges = svc.get_edges_for_node(node_id)
    return success_response([KnowledgeEdgeResponse.model_validate(e).model_dump(by_alias=True) for e in edges])


@router.post("/edges", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_edge(
    data: KnowledgeEdgeCreate,
    current_user: User = Depends(get_teacher_or_admin),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Create an edge between two knowledge nodes. Requires Teacher or Admin."""
    edge = svc.create_edge(data)
    return success_response(KnowledgeEdgeResponse.model_validate(edge).model_dump(by_alias=True))


@router.delete("/edges/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(
    edge_id: int,
    current_user: User = Depends(get_admin_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Delete a knowledge edge. Admin only."""
    svc.delete_edge(edge_id)
    return None


# ============================================
# GRAPH OPERATIONS
# ============================================

@router.post("/subgraph", response_model=None)
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
    subgraph = svc.get_subgraph_for_lessons(lesson_ids, max_depth, difficulty_filter)
    return success_response(SubgraphResponse.model_validate(subgraph).model_dump(by_alias=True))


@router.post("/mindmap/{root_node_id}", response_model=None)
async def generate_mindmap(
    root_node_id: int,
    max_depth: int = Query(default=4, ge=1, le=6),
    current_user: User = Depends(get_current_active_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Generate and save a mindmap tree rooted at a knowledge node (DFS spanning tree)."""
    mindmap = svc.generate_mindmap(current_user.id, root_node_id, max_depth)
    return success_response(MindmapResponse.model_validate(mindmap).model_dump(by_alias=True))


@router.get("/mindmaps/me", response_model=None)
async def my_mindmaps(
    current_user: User = Depends(get_current_active_user),
    svc: KnowledgeService = Depends(get_knowledge_service),
):
    """Get all mindmaps generated by the current user."""
    mindmaps = svc.get_mindmaps_for_user(current_user.id)
    return success_response([MindmapResponse.model_validate(m).model_dump(by_alias=True) for m in mindmaps])