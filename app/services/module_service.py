from sqlalchemy.orm import Session
from typing import Optional, List
from fastapi import HTTPException, status, Depends
from app.db.models.module import Module
from app.db.models.subject import Subject
from app.db.models.lesson import Lesson
from app.schemas.module_lesson import ModuleCreate, ModuleUpdate
from app.db.session import get_db


class ModuleService:
    """Service layer for module-related business logic"""

    def __init__(self, db: Session):
        self.db = db

    # ============================================
    # READ OPERATIONS
    # ============================================

    def get_by_id(self, module_id: int) -> Optional[Module]:
        """Get module by ID"""
        return self.db.query(Module).filter(Module.id == module_id).first()

    def get_all(
            self,
            skip: int = 0,
            limit: int = 100,
            subject_id: Optional[int] = None,
            grade: Optional[int] = None,
            search: Optional[str] = None
    ) -> List[Module]:
        """
        Get all modules with optional filters

        Args:
            skip: Number of records to skip (pagination)
            limit: Maximum number of records to return
            subject_id: Filter by subject
            grade: Filter by grade
            search: Search in name and description

        Returns:
            List of modules matching the criteria
        """
        query = self.db.query(Module)

        # Apply filters
        if subject_id is not None:
            query = query.filter(Module.subject_id == subject_id)

        if grade is not None:
            query = query.filter(Module.grade == grade)

        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (Module.name.ilike(search_pattern)) |
                (Module.description.ilike(search_pattern))
            )

        # Order by display_order, then name
        return query.order_by(Module.display_order, Module.name).offset(skip).limit(limit).all()

    def get_by_subject(self, subject_id: int) -> List[Module]:
        """Get all modules for a subject"""
        return self.db.query(Module).filter(
            Module.subject_id == subject_id
        ).order_by(Module.grade, Module.display_order).all()

    def get_by_grade(self, grade: int) -> List[Module]:
        """Get all modules for a specific grade"""
        return self.db.query(Module).filter(
            Module.grade == grade
        ).order_by(Module.subject_id, Module.display_order).all()

    def get_with_lesson_count(self, module_id: int) -> dict:
        """
        Get module with lesson count

        Args:
            module_id: Module ID

        Returns:
            Dictionary with module data and lesson count
        """
        module = self.get_by_id(module_id)
        if not module:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Module with id {module_id} not found"
            )

        lesson_count = self.db.query(Lesson).filter(Lesson.module_id == module_id).count()

        return {
            "id": module.id,
            "subject_id": module.subject_id,
            "grade": module.grade,
            "name": module.name,
            "description": module.description,
            "display_order": module.display_order,
            "created_at": module.created_at,
            "updated_at": module.updated_at,
            "lesson_count": lesson_count
        }

    # ============================================
    # CREATE OPERATIONS
    # ============================================

    def create(self, module_data: ModuleCreate) -> Module:
        """
        Create a new module

        Args:
            module_data: Module creation data

        Returns:
            Created module

        Raises:
            HTTPException: If subject doesn't exist
        """
        # Verify subject exists
        subject = self.db.query(Subject).filter(Subject.id == module_data.subject_id).first()
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subject with id {module_data.subject_id} not found"
            )

        # Create module
        module = Module(
            subject_id=module_data.subject_id,
            grade=module_data.grade,
            name=module_data.name,
            description=module_data.description,
            display_order=module_data.display_order
        )

        self.db.add(module)
        self.db.commit()
        self.db.refresh(module)

        return module

    # ============================================
    # UPDATE OPERATIONS
    # ============================================

    def update(self, module_id: int, module_data: ModuleUpdate) -> Module:
        """
        Update module

        Args:
            module_id: Module ID to update
            module_data: Update data

        Returns:
            Updated module

        Raises:
            HTTPException: If module not found or validation fails
        """
        module = self.get_by_id(module_id)
        if not module:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Module with id {module_id} not found"
            )

        # Get only fields that were actually provided
        update_data = module_data.model_dump(exclude_unset=True)

        # Verify subject exists if being updated
        if "subject_id" in update_data:
            subject = self.db.query(Subject).filter(Subject.id == update_data["subject_id"]).first()
            if not subject:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Subject with id {update_data['subject_id']} not found"
                )

        # Update module fields
        for field, value in update_data.items():
            setattr(module, field, value)

        self.db.commit()
        self.db.refresh(module)

        return module

    def reorder(self, module_id: int, new_order: int) -> Module:
        """
        Update module display order

        Args:
            module_id: Module ID
            new_order: New display order

        Returns:
            Updated module
        """
        module = self.get_by_id(module_id)
        if not module:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Module with id {module_id} not found"
            )

        module.display_order = new_order
        self.db.commit()
        self.db.refresh(module)

        return module

    # ============================================
    # DELETE OPERATIONS
    # ============================================

    def delete(self, module_id: int) -> None:
        """
        Delete module (will cascade to lessons)

        Args:
            module_id: Module ID to delete

        Raises:
            HTTPException: If module not found
        """
        module = self.get_by_id(module_id)
        if not module:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Module with id {module_id} not found"
            )

        # Check if module has lessons
        lesson_count = self.db.query(Lesson).filter(Lesson.module_id == module_id).count()

        if lesson_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete module with {lesson_count} lesson(s). Delete lessons first."
            )

        self.db.delete(module)
        self.db.commit()


# ============================================
# DEPENDENCY FOR GETTING SERVICE
# ============================================

def get_module_service(db: Session = Depends(get_db)) -> ModuleService:
    """
    Dependency to get ModuleService instance

    Usage in routes:
        module_service: ModuleService = Depends(get_module_service)
    """
    return ModuleService(db)