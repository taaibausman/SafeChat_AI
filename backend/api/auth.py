from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

import backend.models.domain as models
import backend.schemas.domain as schemas
from backend.auth import create_access_token, hash_password, verify_password
from backend.database.config import get_db


router = APIRouter()


@router.post("/register", response_model=schemas.AuthResponse)
def register_user(payload: schemas.UserRegisterRequest, db: Session = Depends(get_db)):
    normalized_username = payload.username.strip()
    normalized_email = payload.email.strip().lower()
    existing = (
        db.query(models.User)
        .filter(
            (func.lower(models.User.email) == normalized_email)
            | (func.lower(models.User.username) == normalized_username.lower())
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

    user = models.User(
        username=normalized_username,
        email=normalized_email,
        password_hash=hash_password(payload.password),
        role="user",
        is_active=True,
        name=payload.name.strip() if payload.name else None,
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
    credential = payload.email_or_username.strip()
    user = (
        db.query(models.User)
        .filter(
            (func.lower(models.User.email) == credential.lower())
            | (func.lower(models.User.username) == credential.lower())
        )
        .first()
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return schemas.AuthResponse(
        access_token=create_access_token(user),
        token_type="bearer",
        user=schemas.UserResponse.model_validate(user),
    )
