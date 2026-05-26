from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

class ChatUploadResponse(BaseModel):
    chat_id: int
    message: str

class AnalysisResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    chat_id: int
    overall_score: float
    safe_percentage: float
    unsafe_percentage: float
    summary: str

class MessageBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sender: str
    message: str
    timestamp: datetime
    risk_score: Optional[float] = None
    label: Optional[str] = None

class ChatDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    platform: str
    chat_name: str
    analysis_results: Optional[AnalysisResultResponse] = None
    messages: List[MessageBase] = []

class UserCreate(BaseModel):
    email: str
    firebase_uid: str
    name: Optional[str] = None
