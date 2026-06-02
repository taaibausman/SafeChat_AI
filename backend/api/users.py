from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import backend.models.domain as models
import backend.schemas.domain as schemas
from backend.auth import get_current_admin, get_current_user, hash_password, verify_password
from backend.database.config import get_db


router = APIRouter()


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=schemas.UserResponse)
def update_me(
    payload: schemas.UserProfileUpdateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.username is not None:
        next_username = payload.username.strip() or None
        if next_username:
            duplicate_username = (
                db.query(models.User)
                .filter(models.User.username == next_username, models.User.id != current_user.id)
                .first()
            )
            if duplicate_username is not None:
                raise HTTPException(status_code=400, detail="Username already exists")
        current_user.username = next_username

    if payload.email is not None:
        next_email = payload.email.strip().lower()
        if not next_email:
            raise HTTPException(status_code=400, detail="Email is required")
        duplicate_email = (
            db.query(models.User)
            .filter(models.User.email == next_email, models.User.id != current_user.id)
            .first()
        )
        if duplicate_email is not None:
            raise HTTPException(status_code=400, detail="Email already exists")
        current_user.email = next_email

    if payload.name is not None:
        current_user.name = payload.name.strip() or None

    wants_password_change = payload.current_password is not None or payload.new_password is not None
    if wants_password_change:
        current_password = (payload.current_password or "").strip()
        next_password = (payload.new_password or "").strip()
        if not current_password:
            raise HTTPException(status_code=400, detail="Current password is required")
        if not verify_password(current_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        if len(next_password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        current_user.password_hash = hash_password(next_password)

    db.commit()
    db.refresh(current_user)
    return schemas.UserResponse.model_validate(current_user)


@router.get("", response_model=schemas.UserListResponse)
def list_users(
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(models.User)
    if search:
        query = query.filter(
            (models.User.email.ilike(f"%{search}%"))
            | (models.User.username.ilike(f"%{search}%"))
            | (models.User.name.ilike(f"%{search}%"))
        )

    total = query.count()
    users = (
        query.order_by(models.User.created_at.desc(), models.User.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return schemas.UserListResponse(
        total=total,
        limit=limit,
        offset=offset,
        users=[schemas.UserResponse.model_validate(user) for user in users],
    )


@router.patch("/{user_id}", response_model=schemas.UserResponse)
def update_user(
    user_id: int,
    payload: schemas.UserUpdateRequest,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.role is not None:
        if payload.role not in {"user", "admin"}:
            raise HTTPException(status_code=400, detail="Invalid role")
        user.role = payload.role
    if payload.is_active is not None:
        if user.id == admin.id and payload.is_active is False:
            raise HTTPException(status_code=400, detail="Admin cannot deactivate their own account")
        user.is_active = payload.is_active
    if payload.name is not None:
        user.name = payload.name.strip() or None

    db.commit()
    db.refresh(user)
    return schemas.UserResponse.model_validate(user)
