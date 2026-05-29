from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class GoogleSignInRequest(BaseModel):
    id_token: str  # In real implementation this would be verified with Firebase

@router.post("/google")
async def google_sign_in(payload: GoogleSignInRequest):
    # For now we just echo back a mock JWT for development purposes
    if not payload.id_token:
        raise HTTPException(status_code=400, detail="Missing id_token")
    # Return a fake token and user info
    return {"access_token": "mock-jwt-token", "user": {"uid": "mock-uid", "email": "user@example.com"}}
