from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

class ChatUploadResponse(BaseModel):
    chat_id: int
    message: str

class DashboardRecentChat(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    chat_name: str
    platform: str
    created_at: datetime
    unsafe_percentage: Optional[float] = None
    flagged_messages: int = 0

class DashboardSummaryResponse(BaseModel):
    total_chats: int
    total_messages: int
    flagged_messages: int
    safe_ratio: float
    recent_chats: List[DashboardRecentChat]

class WhatsAppStatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None
    qr: Optional[str] = None

class WhatsAppStatusResponse(BaseModel):
    status: str
    reason: Optional[str] = None
    qr: Optional[str] = None
    qr_updated_at: Optional[datetime] = None

class IncomingWhatsAppMessage(BaseModel):
    message_id: Optional[str] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    sender: str
    sender_name: Optional[str] = None
    text: str
    timestamp: Optional[int] = None

class LiveFeedMessage(BaseModel):
    id: int
    chat_id: int
    chat_name: str
    sender: str
    message: str
    timestamp: Optional[datetime] = None
    risk_score: Optional[float] = None
    label: Optional[str] = None

class LiveFeedResponse(BaseModel):
    messages: List[LiveFeedMessage]

class WhatsAppChatSummary(BaseModel):
    id: int
    chat_name: str
    platform: str
    message_count: int
    flagged_messages: int
    unsafe_percentage: float
    last_message_at: Optional[datetime] = None

class WhatsAppChatListResponse(BaseModel):
    chats: List[WhatsAppChatSummary]

class WhatsAppBridgeHealthResponse(BaseModel):
    reachable: bool
    status: Optional[str] = None
    detail: Optional[str] = None

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
    timestamp: Optional[datetime] = None
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
