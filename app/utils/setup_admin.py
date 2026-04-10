from sqlalchemy.orm import Session
from app.config import settings
from app.services.user_service import UserService
from app.core.logger import access_logger, error_logger

def create_initial_admin(db: Session):
    """
    Create initial admin user if not exists

    This should be called after running Alembic migrations
    """
    user_service = UserService(db)

    # Check if admin already exists (by email or username)
    admin = user_service.get_by_email(settings.ADMIN_EMAIL)

    if not admin:
        admin = user_service.get_by_username(settings.ADMIN_USERNAME)

    if not admin:
        access_logger.info(f"Creating admin user: {settings.ADMIN_USERNAME}", extra={"action_code": "SETUP"})

        admin = user_service.create_admin(
            username=settings.ADMIN_USERNAME,
            email=settings.ADMIN_EMAIL,
            password=settings.ADMIN_PASSWORD
        )

        access_logger.info(f"Admin user created successfully. Username: {admin.username}, Email: {admin.email}", extra={"action_code": "SETUP"})
    else:
        access_logger.info(f"Admin user already exists: {admin.email}", extra={"action_code": "SETUP"})


# Optional: Function to reset admin password if needed
def reset_admin_password(db: Session, new_password: str = None):
    """
    Reset admin password (useful for recovery)

    Args:
        db: Database session
        new_password: New password (uses config default if not provided)
    """
    user_service = UserService(db)

    admin = user_service.get_by_username(settings.ADMIN_USERNAME)
    if not admin:
        error_logger.error(f"Admin user '{settings.ADMIN_USERNAME}' not found!", extra={"action_code": "SETUP_ERROR"})
        return

    password = new_password or settings.ADMIN_PASSWORD
    user_service.update_password(admin.id, password)

    access_logger.info("Admin password reset successfully!", extra={"action_code": "SETUP"})