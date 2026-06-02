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
    bridge_session_key: Optional[str] = None
    status: str
    reason: Optional[str] = None
    qr: Optional[str] = None
    connected_phone: Optional[str] = None

class WhatsAppStatusResponse(BaseModel):
    bridge_session_key: Optional[str] = None
    single_account_mode: bool = False
    status: str
    reason: Optional[str] = None
    qr: Optional[str] = None
    qr_updated_at: Optional[datetime] = None
    connected_phone: Optional[str] = None
    bridge_reachable: bool = False
    bridge_status: Optional[str] = None
    bridge_detail: Optional[str] = None
    last_event_at: Optional[datetime] = None

class IncomingWhatsAppMessage(BaseModel):
    bridge_session_key: Optional[str] = None
    message_id: Optional[str] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    chat_type: Optional[str] = None
    sender: str
    sender_name: Optional[str] = None
    text: str
    timestamp: Optional[int] = None
    direction: Optional[str] = None
    is_from_me: bool = False
    raw_payload: Optional[dict] = None

class LiveFeedMessage(BaseModel):
    id: int
    chat_id: int
    chat_name: str
    sender: str
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    message: str
    external_message_id: Optional[str] = None
    source: Optional[str] = None
    direction: Optional[str] = None
    is_from_me: bool = False
    timestamp: Optional[datetime] = None
    risk_score: Optional[float] = None
    label: Optional[str] = None

class LiveFeedResponse(BaseModel):
    total: int = 0
    limit: int = 0
    offset: int = 0
    messages: List[LiveFeedMessage]

class WhatsAppChatSummary(BaseModel):
    id: int
    chat_name: str
    platform: str
    external_chat_id: Optional[str] = None
    chat_type: Optional[str] = None
    is_live: bool = True
    message_count: int
    flagged_messages: int
    alert_count: int = 0
    open_alert_count: int = 0
    acknowledged_alert_count: int = 0
    resolved_alert_count: int = 0
    unsafe_percentage: float
    last_message_at: Optional[datetime] = None
    latest_message_preview: Optional[str] = None

class WhatsAppChatListResponse(BaseModel):
    total: int = 0
    limit: int = 0
    offset: int = 0
    chats: List[WhatsAppChatSummary]


class MonitoredContactCreateRequest(BaseModel):
    contact_name: str
    chat_key: str
    chat_type: str = "direct"
    is_active: bool = True


class MonitoredContactUpdateRequest(BaseModel):
    contact_name: Optional[str] = None
    chat_key: Optional[str] = None
    chat_type: Optional[str] = None
    is_active: Optional[bool] = None


class MonitoredContactResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    contact_name: str
    phone_number: Optional[str] = None
    chat_key: str
    chat_type: str = "direct"
    is_active: bool = True
    created_at: Optional[datetime] = None


class MonitoredContactListResponse(BaseModel):
    total: int = 0
    contacts: List[MonitoredContactResponse]


class WhatsAppChatSummaryAggregateResponse(BaseModel):
    total_chats: int = 0
    total_messages: int = 0
    flagged_chats: int = 0
    by_chat_type: dict[str, int] = {}
    by_risk_state: dict[str, int] = {}
    latest_message_at: Optional[datetime] = None


class WhatsAppBridgeHealthResponse(BaseModel):
    reachable: bool
    status: Optional[str] = None
    detail: Optional[str] = None


class WhatsAppBridgeEventResponse(BaseModel):
    id: int
    event_type: str
    status: Optional[str] = None
    detail: Optional[str] = None
    connected_phone: Optional[str] = None
    bridge_reachable: Optional[bool] = None
    created_at: datetime


class WhatsAppBridgeEventListResponse(BaseModel):
    total: int = 0
    limit: int = 0
    offset: int = 0
    events: List[WhatsAppBridgeEventResponse]


class WhatsAppBridgeEventSummaryResponse(BaseModel):
    total_events: int = 0
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    latest_event_at: Optional[datetime] = None


class WhatsAppBridgeStateSnapshotResponse(BaseModel):
    id: int
    status: Optional[str] = None
    reason: Optional[str] = None
    connected_phone: Optional[str] = None
    bridge_status: Optional[str] = None
    bridge_detail: Optional[str] = None
    bridge_reachable: Optional[bool] = None
    qr_present: bool = False
    created_at: datetime


class WhatsAppBridgeStateSnapshotListResponse(BaseModel):
    total: int = 0
    limit: int = 0
    offset: int = 0
    snapshots: List[WhatsAppBridgeStateSnapshotResponse]


class WhatsAppBridgeStateSnapshotSummaryResponse(BaseModel):
    total_snapshots: int = 0
    by_status: dict[str, int] = {}
    by_bridge_status: dict[str, int] = {}
    latest_snapshot_at: Optional[datetime] = None


class WhatsAppBridgeOpsSummaryResponse(BaseModel):
    current_state: WhatsAppStatusResponse
    latest_event: Optional[WhatsAppBridgeEventResponse] = None
    latest_snapshot: Optional[WhatsAppBridgeStateSnapshotResponse] = None
    recent_event_count: int = 0
    recent_snapshot_count: int = 0
    recent_window_hours: int = 24
    bridge_reachable: bool = False
    attention_required: bool = False


class LiveAlertResponse(BaseModel):
    id: int
    message_id: int
    chat_id: int
    chat_name: str
    alert_type: str
    severity: str
    status: str
    notes: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    sender: str
    message: str
    risk_score: Optional[float] = None
    label: Optional[str] = None
    timestamp: Optional[datetime] = None


class LiveAlertListResponse(BaseModel):
    total: int = 0
    limit: int = 0
    offset: int = 0
    alerts: List[LiveAlertResponse]


class LiveAlertSummaryResponse(BaseModel):
    total_alerts: int = 0
    by_severity: dict[str, int] = {}
    by_status: dict[str, int] = {}
    latest_alert_at: Optional[datetime] = None


class AlertUpdateRequest(BaseModel):
    status: str
    notes: Optional[str] = None


class WhatsAppLiveSummaryResponse(BaseModel):
    bridge_status: str
    bridge_reachable: bool
    connected_phone: Optional[str] = None
    total_live_chats: int
    total_live_messages: int
    flagged_live_messages: int
    total_alerts: int
    open_alerts: int = 0
    acknowledged_alerts: int = 0
    resolved_alerts: int = 0
    safe_ratio: float
    last_message_at: Optional[datetime] = None


class WhatsAppLiveOpsSummaryResponse(BaseModel):
    live_summary: WhatsAppLiveSummaryResponse
    recent_feed_count: int = 0
    recent_alert_count: int = 0
    recent_flagged_message_count: int = 0
    flagged_chat_count: int = 0
    high_risk_chat_count: int = 0
    recent_window_hours: int = 24
    attention_required: bool = False


class WhatsAppBackendHealthResponse(BaseModel):
    bridge_ops: WhatsAppBridgeOpsSummaryResponse
    live_ops: WhatsAppLiveOpsSummaryResponse
    recent_window_hours: int = 24
    attention_required: bool = False
    status: str = "healthy"

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
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    message: str
    external_message_id: Optional[str] = None
    source: Optional[str] = None
    direction: Optional[str] = None
    is_from_me: bool = False
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


class GuestChatUploadResponse(BaseModel):
    message: str
    report: ChatDetailResponse


class LiveChatDetailResponse(BaseModel):
    id: int
    platform: str
    chat_name: str
    external_chat_id: Optional[str] = None
    chat_type: Optional[str] = None
    is_live: bool = True
    last_message_at: Optional[datetime] = None
    analysis_results: Optional[AnalysisResultResponse] = None
    total_messages: int = 0
    alert_count: int = 0
    open_alert_count: int = 0
    acknowledged_alert_count: int = 0
    resolved_alert_count: int = 0
    limit: int = 0
    offset: int = 0
    messages: List[MessageBase] = []


class MessageSendRequest(BaseModel):
    chat_id: Optional[int] = None
    chat_name: Optional[str] = None
    platform: str = "SafeChat_Direct"
    content: str


class MessageSendResponse(BaseModel):
    chat_id: int
    message_id: int
    action: str
    severity: str
    blocked: bool = False
    risk_score: float
    label: str


class MessageListResponse(BaseModel):
    chat_id: int
    chat_name: str
    platform: str
    total_messages: int = 0
    messages: List[MessageBase] = []


class ModerateTextRequest(BaseModel):
    text: str
    persist_result: bool = False
    chat_name: Optional[str] = None


class ModerateImageResponse(BaseModel):
    chat_id: Optional[int] = None
    message_id: Optional[int] = None
    extracted_text: str
    action: str
    severity: str
    risk_score: float
    label: str
    blocked: bool = False
    saved: bool = True


class ModerateTextResponse(BaseModel):
    chat_id: Optional[int] = None
    message_id: Optional[int] = None
    text: str
    action: str
    severity: str
    risk_score: float
    label: str
    blocked: bool = False
    saved: bool = False
    thresholds: dict[str, float] = {}
    details: dict = {}

class UserCreate(BaseModel):
    email: str
    firebase_uid: str
    name: Optional[str] = None


class UserRegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    name: Optional[str] = None


class UserLoginRequest(BaseModel):
    email_or_username: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: Optional[str] = None
    email: str
    role: str = "user"
    is_active: bool = True
    name: Optional[str] = None
    created_at: datetime


class UserListResponse(BaseModel):
    total: int = 0
    limit: int = 0
    offset: int = 0
    users: List[UserResponse]


class UserUpdateRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    name: Optional[str] = None


class UserProfileUpdateRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ModerationLogResponse(BaseModel):
    id: int
    message_id: int
    chat_id: int
    chat_name: str
    sender: str
    message: str
    toxic: float = 0.0
    severe_toxic: float = 0.0
    obscene: float = 0.0
    threat: float = 0.0
    insult: float = 0.0
    identity_hate: float = 0.0
    action: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime


class ModerationLogListResponse(BaseModel):
    total: int = 0
    limit: int = 0
    offset: int = 0
    logs: List[ModerationLogResponse]


class ModerationLogUpdateRequest(BaseModel):
    action: str
