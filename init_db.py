"""
Database initialization script
Creates tables and adds the admin user
"""
from app.database import engine, SessionLocal, Base
from app.models.user import User, UserRole
from app.core.security import get_password_hash
from app.config import settings


def init_db():
    # Create all tables
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✓ Tables created successfully")

    # Create admin user
    db = SessionLocal()
    try:
        # Check if admin already exists
        admin_user = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()

        if not admin_user:
            print(f"Creating admin user: {settings.ADMIN_USERNAME}")
            admin_user = User(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL,
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                role=UserRole.ADMIN,
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            print(f"✓ Admin user created successfully")
            print(f"  Username: {settings.ADMIN_USERNAME}")
            print(f"  Password: {settings.ADMIN_PASSWORD}")
            print(f"  Email: {settings.ADMIN_EMAIL}")
        else:
            print(f"Admin user '{settings.ADMIN_USERNAME}' already exists")

    except Exception as e:
        print(f"Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("\nDatabase initialization complete!")