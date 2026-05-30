from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import backend.models.domain as models
import backend.schemas.domain as schemas
from backend.auth import create_access_token, hash_password, verify_password
from backend.database.config import get_db


router = APIRouter()


@router.post("/register", response_model=schemas.AuthResponse)
def register_user(payload: schemas.UserRegisterRequest, db: Session = Depends(get_db)):
    existing = (
        db.query(models.User)
        .filter((models.User.email == payload.email) | (models.User.username == payload.username))
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

    role = payload.role if payload.role in {"user", "admin"} else "user"
    user = models.User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=True,
        name=payload.name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return schemas.AuthResponse(
        access_token=create_access_token(user),
        token_type="bearer",
        user=schemas.UserResponse.model_validate(user),
    )


@router.post("/login", response_model=schemas.AuthResponse)
def login_user(payload: schemas.UserLoginRequest, db: Session = Depends(get_db)):
    user = (
        db.query(models.User)
        .filter((models.User.email == payload.email_or_username) | (models.User.username == payload.email_or_username))
        .first()
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return schemas.AuthResponse(
        access_token=create_access_token(user),
        token_type="bearer",
        user=schemas.UserResponse.model_validate(user),
    )
