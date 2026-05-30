from fastapi import APIRouter, Depends

import backend.models.domain as models
import backend.schemas.domain as schemas
from backend.auth import get_current_user


router = APIRouter()


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user
