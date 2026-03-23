from sqlalchemy.orm import Session
from app.config import settings
from app.services.user_service import UserService


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
        print(f"--- Creating admin user: {settings.ADMIN_USERNAME} ---")

        admin = user_service.create_admin(
            username=settings.ADMIN_USERNAME,
            email=settings.ADMIN_EMAIL,
            password=settings.ADMIN_PASSWORD
        )

        print(f"✓ Admin user created successfully!")
        print(f"  Username: {admin.username}")
        print(f"  Email: {admin.email}")
        print(f"  Role: {admin.role.value}")
        print(f"--- Admin setup complete! ---")
    else:
        print(f"--- Admin user already exists: {admin.email} ---")


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
        print(f"❌ Admin user '{settings.ADMIN_USERNAME}' not found!")
        return

    password = new_password or settings.ADMIN_PASSWORD
    user_service.update_password(admin.id, password)

    print(f"✓ Admin password reset successfully!")
    print(f"  Username: {admin.username}")
    print(f"  New password: {'***' if new_password else settings.ADMIN_PASSWORD}")