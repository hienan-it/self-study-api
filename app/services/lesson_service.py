from sqlalchemy.orm import Session
from typing import Optional, List
from fastapi import HTTPException, status, Depends
from app.db.models.lesson import Lesson
from app.db.models.module import Module
from app.schemas.module_lesson import LessonCreate, LessonUpdate
from app.db.session import get_db


class LessonService:
    """Service layer for lesson-related business logic"""

    def __init__(self, db: Session):
        self.db = db

    # ============================================
    # READ OPERATIONS
    # ============================================

    def get_by_id(self, lesson_id: int) -> Optional[Lesson]:
        """Get lesson by ID"""
        return self.db.query(Lesson).filter(Lesson.id == lesson_id).first()

    def get_all(
            self,
            skip: int = 0,
            limit: int = 100,
            module_id: Optional[int] = None,
            search: Optional[str] = None
    ) -> List[Lesson]:
        """
        Get all lessons with optional filters

        Args:
            skip: Number of records to skip (pagination)
            limit: Maximum number of records to return
            module_id: Filter by module
            search: Search in name and content

        Returns:
            List of lessons matching the criteria
        """
        query = self.db.query(Lesson)

        # Apply filters
        if module_id is not None:
            query = query.filter(Lesson.module_id == module_id)

        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (Lesson.name.ilike(search_pattern)) |
                (Lesson.content.ilike(search_pattern))
            )

        # Order by display_order, then name
        return query.order_by(Lesson.display_order, Lesson.name).offset(skip).limit(limit).all()

    def get_by_module(self, module_id: int) -> List[Lesson]:
        """Get all lessons for a module"""
        return self.db.query(Lesson).filter(
            Lesson.module_id == module_id
        ).order_by(Lesson.display_order).all()

    def get_with_knowledge_count(self, lesson_id: int) -> dict:
        """
        Get lesson with knowledge node count

        Args:
            lesson_id: Lesson ID

        Returns:
            Dictionary with lesson data and knowledge node count
        """
        lesson = self.get_by_id(lesson_id)
        if not lesson:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lesson with id {lesson_id} not found"
            )

        # Count knowledge nodes linked to this lesson
        knowledge_node_count = len(lesson.knowledge_nodes)

        return {
            "id": lesson.id,
            "module_id": lesson.module_id,
            "name": lesson.name,
            "content": lesson.content,
            "display_order": lesson.display_order,
            "created_at": lesson.created_at,
            "updated_at": lesson.updated_at,
            "knowledge_node_count": knowledge_node_count
        }

    # ============================================
    # CREATE OPERATIONS
    # ============================================

    def create(self, lesson_data: LessonCreate) -> Lesson:
        """
        Create a new lesson

        Args:
            lesson_data: Lesson creation data

        Returns:
            Created lesson

        Raises:
            HTTPException: If module doesn't exist
        """
        # Verify module exists
        module = self.db.query(Module).filter(Module.id == lesson_data.module_id).first()
        if not module:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Module with id {lesson_data.module_id} not found"
            )

        # Create lesson
        lesson = Lesson(
            module_id=lesson_data.module_id,
            name=lesson_data.name,
            content=lesson_data.content,
            display_order=lesson_data.display_order
        )

        self.db.add(lesson)
        self.db.commit()
        self.db.refresh(lesson)

        return lesson

    # ============================================
    # UPDATE OPERATIONS
    # ============================================

    def update(self, lesson_id: int, lesson_data: LessonUpdate) -> Lesson:
        """
        Update lesson

        Args:
            lesson_id: Lesson ID to update
            lesson_data: Update data

        Returns:
            Updated lesson

        Raises:
            HTTPException: If lesson not found or validation fails
        """
        lesson = self.get_by_id(lesson_id)
        if not lesson:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lesson with id {lesson_id} not found"
            )

        # Get only fields that were actually provided
        update_data = lesson_data.model_dump(exclude_unset=True)

        # Verify module exists if being updated
        if "module_id" in update_data:
            module = self.db.query(Module).filter(Module.id == update_data["module_id"]).first()
            if not module:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Module with id {update_data['module_id']} not found"
                )

        # Update lesson fields
        for field, value in update_data.items():
            setattr(lesson, field, value)

        self.db.commit()
        self.db.refresh(lesson)

        return lesson

    def reorder(self, lesson_id: int, new_order: int) -> Lesson:
        """
        Update lesson display order

        Args:
            lesson_id: Lesson ID
            new_order: New display order

        Returns:
            Updated lesson
        """
        lesson = self.get_by_id(lesson_id)
        if not lesson:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lesson with id {lesson_id} not found"
            )

        lesson.display_order = new_order
        self.db.commit()
        self.db.refresh(lesson)

        return lesson

    # ============================================
    # DELETE OPERATIONS
    # ============================================

    def delete(self, lesson_id: int) -> None:
        """
        Delete lesson

        Args:
            lesson_id: Lesson ID to delete

        Raises:
            HTTPException: If lesson not found
        """
        lesson = self.get_by_id(lesson_id)
        if not lesson:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lesson with id {lesson_id} not found"
            )

        self.db.delete(lesson)
        self.db.commit()


# ============================================
# DEPENDENCY FOR GETTING SERVICE
# ============================================

def get_lesson_service(db: Session = Depends(get_db)) -> LessonService:
    """
    Dependency to get LessonService instance

    Usage in routes:
        lesson_service: LessonService = Depends(get_lesson_service)
    """
    return LessonService(db)