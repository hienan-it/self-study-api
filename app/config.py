from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Auth
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # bumped up for dev

    # Initial Admin
    ADMIN_USERNAME: str
    ADMIN_PASSWORD: str
    ADMIN_EMAIL: str

    # MinIO Storage
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False  # False for local dev/docker
    MINIO_BUCKET_NAME: str = "learning-assets"

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"  # Prevents crashing if extra vars are in .env
    }


settings = Settings()