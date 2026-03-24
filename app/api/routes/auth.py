from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.user import UserCreate, UserResponse, LoginRequest
from app.core.security import create_access_token
from app.core.responses import success_response
from app.config import settings
from app.services.user_service import UserService, get_user_service

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=None, status_code=status.HTTP_201_CREATED)
def register(
        user_data: UserCreate,
        user_service: UserService = Depends(get_user_service)
):
    """
    Register a new user

    - **username**: Unique username (3-50 characters)
    - **email**: Valid email address
    - **password**: Password (min 8 characters recommended)
    - **role**: User role (student, teacher, admin)
    """
    user = user_service.create(user_data)
    return success_response(UserResponse.model_validate(user).model_dump(by_alias=True))


@router.post("/login", response_model=None)
def login(
        login_data: LoginRequest,
        user_service: UserService = Depends(get_user_service)
):
    """
    Login to get access token

    Use the token in Authorization header: `Bearer <token>`
    """
    user = user_service.authenticate(login_data.username, login_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user_service.is_active(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )

    return success_response({"access_token": access_token, "token_type": "bearer"})