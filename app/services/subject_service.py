from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from fastapi import HTTPException, status, Depends
from app.models.subject import Subject
from app.models.module import Module
from app.models.lesson import Lesson
from app.models.knowledge import KnowledgeNode
from app.schemas.subject import SubjectCreate, SubjectUpdate
from app.database import get_db


class SubjectService:
    """Service layer for subject-related business logic"""

    def __init__(self, db: Session):
        self.db = db

    # ============================================
    # READ OPERATIONS
    # ============================================

    def get_by_id(self, subject_id: int) -> Optional[Subject]:
        """Get subject by ID"""
        return self.db.query(Subject).filter(Subject.id == subject_id).first()

    def get_by_name(self, name: str) -> Optional[Subject]:
        """Get subject by name"""
        return self.db.query(Subject).filter(Subject.name == name).first()

    def get_all(
            self,
            skip: int = 0,
            limit: int = 100,
            is_active: Optional[bool] = None,
            search: Optional[str] = None
    ) -> List[Subject]:
        """
        Get all subjects with optional filters

        Args:
            skip: Number of records to skip (pagination)
            limit: Maximum number of records to return
            is_active: Filter by active status
            search: Search in name and description

        Returns:
            List of subjects matching the criteria
        """
        query = self.db.query(Subject)

        # Apply filters
        if is_active is not None:
            query = query.filter(Subject.is_active == is_active)

        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (Subject.name.ilike(search_pattern)) |
                (Subject.description.ilike(search_pattern))
            )

        # Order by name and apply pagination
        return query.order_by(Subject.name).offset(skip).limit(limit).all()

    def get_with_stats(self, subject_id: int) -> dict:
        """
        Get subject with statistics

        Args:
            subject_id: Subject ID

        Returns:
            Dictionary with subject data and statistics
        """
        subject = self.get_by_id(subject_id)
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subject with id {subject_id} not found"
            )

        # Get counts
        module_count = self.db.query(Module).filter(Module.subject_id == subject_id).count()

        lesson_count = self.db.query(Lesson).join(Module).filter(
            Module.subject_id == subject_id
        ).count()

        knowledge_node_count = self.db.query(KnowledgeNode).filter(
            KnowledgeNode.subject_id == subject_id
        ).count()

        return {
            "id": subject.id,
            "name": subject.name,
            "description": subject.description,
            "is_active": subject.is_active,
            "created_at": subject.created_at,
            "updated_at": subject.updated_at,
            "module_count": module_count,
            "lesson_count": lesson_count,
            "knowledge_node_count": knowledge_node_count
        }

    def exists_by_name(self, name: str, exclude_id: Optional[int] = None) -> bool:
        """
        Check if subject name exists

        Args:
            name: Subject name to check
            exclude_id: Exclude this subject ID from check (for updates)

        Returns:
            True if name exists, False otherwise
        """
        query = self.db.query(Subject).filter(Subject.name == name)
        if exclude_id:
            query = query.filter(Subject.id != exclude_id)
        return query.first() is not None

    # ============================================
    # CREATE OPERATIONS
    # ============================================

    def create(self, subject_data: SubjectCreate) -> Subject:
        """
        Create a new subject

        Args:
            subject_data: Subject creation data

        Returns:
            Created subject

        Raises:
            HTTPException: If subject name already exists
        """
        # Check if name exists
        if self.exists_by_name(subject_data.name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Subject with name '{subject_data.name}' already exists"
            )

        # Create subject
        subject = Subject(
            name=subject_data.name,
            description=subject_data.description,
            is_active=subject_data.is_active
        )

        self.db.add(subject)
        self.db.commit()
        self.db.refresh(subject)

        return subject

    # ============================================
    # UPDATE OPERATIONS
    # ============================================

    def update(self, subject_id: int, subject_data: SubjectUpdate) -> Subject:
        """
        Update subject

        Args:
            subject_id: Subject ID to update
            subject_data: Update data

        Returns:
            Updated subject

        Raises:
            HTTPException: If subject not found or validation fails
        """
        subject = self.get_by_id(subject_id)
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subject with id {subject_id} not found"
            )

        # Get only fields that were actually provided
        update_data = subject_data.model_dump(exclude_unset=True)

        # Check name uniqueness if being updated
        if "name" in update_data:
            if self.exists_by_name(update_data["name"], exclude_id=subject_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Subject with name '{update_data['name']}' already exists"
                )

        # Update subject fields
        for field, value in update_data.items():
            setattr(subject, field, value)

        self.db.commit()
        self.db.refresh(subject)

        return subject

    def toggle_active(self, subject_id: int) -> Subject:
        """
        Toggle subject active status

        Args:
            subject_id: Subject ID

        Returns:
            Updated subject
        """
        subject = self.get_by_id(subject_id)
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subject with id {subject_id} not found"
            )

        subject.is_active = not subject.is_active
        self.db.commit()
        self.db.refresh(subject)

        return subject

    # ============================================
    # DELETE OPERATIONS
    # ============================================

    def delete(self, subject_id: int) -> None:
        """
        Delete subject (will cascade to modules, lessons, etc.)

        Args:
            subject_id: Subject ID to delete

        Raises:
            HTTPException: If subject not found
        """
        subject = self.get_by_id(subject_id)
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subject with id {subject_id} not found"
            )

        # Check if subject has content
        module_count = self.db.query(Module).filter(Module.subject_id == subject_id).count()

        if module_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete subject with {module_count} module(s). Delete modules first or deactivate the subject."
            )

        self.db.delete(subject)
        self.db.commit()


# ============================================
# DEPENDENCY FOR GETTING SERVICE
# ============================================

def get_subject_service(db: Session = Depends(get_db)) -> SubjectService:
    """
    Dependency to get SubjectService instance

    Usage in routes:
        subject_service: SubjectService = Depends(get_subject_service)
    """
    return SubjectService(db)