from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import relationship

from backend.database.config import Base


chat_participants = Table(
    "chat_participants",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("chat_id", Integer, ForeignKey("chats.id"), primary_key=True),
    Column("joined_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)
    role = Column(String, default="user")
    is_active = Column(Boolean, default=True)
    firebase_uid = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    chats = relationship("Chat", back_populates="owner")
    participating_chats = relationship("Chat", secondary=chat_participants, back_populates="participants")
    monitored_contacts = relationship("MonitoredContact", back_populates="user")
    image_scans = relationship("ImageScan", back_populates="user")
    reviewed_logs = relationship("ModerationLog", back_populates="reviewer")


class Chat(Base):
    __tablename__ = "chats"
    __table_args__ = (
        Index("ix_chats_platform_external_chat_id", "platform", "external_chat_id"),
        Index("ix_chats_platform_user_id_external_chat_id", "platform", "user_id", "external_chat_id"),
        Index("ix_chats_platform_last_message_at", "platform", "last_message_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    platform = Column(String)
    chat_name = Column(String)
    external_chat_id = Column(String, index=True, nullable=True)
    chat_type = Column(String, nullable=True)
    is_live = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    message_count = Column(Integer, default=0)
    flagged_message_count = Column(Integer, default=0)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="chats")
    participants = relationship("User", secondary=chat_participants, back_populates="participating_chats")
    messages = relationship("Message", back_populates="chat")
    analysis_results = relationship("AnalysisResult", back_populates="chat", uselist=False)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_chat_id_external_message_id", "chat_id", "external_message_id", unique=True),
        Index("ix_messages_chat_id_timestamp", "chat_id", "timestamp"),
        Index("ix_messages_source", "source"),
    )

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    sender = Column(String)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    sender_id = Column(String, nullable=True)
    sender_name = Column(String, nullable=True)
    message = Column(String)
    content = Column(Text, nullable=True)
    external_message_id = Column(String, index=True, nullable=True)
    source = Column(String, nullable=True)
    direction = Column(String, nullable=True)
    is_from_me = Column(Boolean, default=False)
    raw_payload = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    risk_score = Column(Float, nullable=True)
    toxicity_score = Column(Float, nullable=True)
    is_flagged = Column(Boolean, default=False)
    label = Column(String, nullable=True)

    chat = relationship("Chat", back_populates="messages")
    sender_user = relationship("User")
    alerts = relationship("Alert", back_populates="message")
    moderation_logs = relationship("ModerationLog", back_populates="message")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    overall_score = Column(Float)
    safe_percentage = Column(Float)
    unsafe_percentage = Column(Float)
    summary = Column(String)

    chat = relationship("Chat", back_populates="analysis_results")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"))
    alert_type = Column(String)
    severity = Column(String)
    status = Column(String, default="open")
    notes = Column(Text, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    message = relationship("Message", back_populates="alerts")


class ModerationLog(Base):
    __tablename__ = "moderation_logs"
    __table_args__ = (
        Index("ix_moderation_logs_message_id", "message_id"),
        Index("ix_moderation_logs_reviewed_by", "reviewed_by"),
    )

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    toxic = Column(Float, default=0.0)
    severe_toxic = Column(Float, default=0.0)
    obscene = Column(Float, default=0.0)
    threat = Column(Float, default=0.0)
    insult = Column(Float, default=0.0)
    identity_hate = Column(Float, default=0.0)
    action = Column(String, default="allow")
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    message = relationship("Message", back_populates="moderation_logs")
    reviewer = relationship("User", back_populates="reviewed_logs")


class ImageScan(Base):
    __tablename__ = "image_scans"
    __table_args__ = (
        Index("ix_image_scans_user_id", "user_id"),
        Index("ix_image_scans_scan_time", "scan_time"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    file_path = Column(String, nullable=False)
    ocr_text = Column(Text, nullable=True)
    is_flagged = Column(Boolean, default=False)
    toxicity_score = Column(Float, nullable=True)
    scan_time = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="image_scans")


class MonitoredContact(Base):
    __tablename__ = "monitored_contacts"
    __table_args__ = (
        Index("ix_monitored_contacts_user_id_is_active", "user_id", "is_active"),
        Index("ix_monitored_contacts_chat_key", "chat_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    contact_name = Column(String)
    phone_number = Column(String, nullable=True)
    chat_key = Column(String, nullable=True)
    chat_type = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="monitored_contacts")


class WhatsAppBridgeState(Base):
    __tablename__ = "whatsapp_bridge_state"
    __table_args__ = (
        Index("ix_whatsapp_bridge_state_user_id", "user_id"),
        Index("ix_whatsapp_bridge_state_session_key", "session_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_key = Column(String, nullable=True, unique=True)
    status = Column(String, default="disconnected")
    reason = Column(String, nullable=True)
    qr = Column(Text, nullable=True)
    qr_updated_at = Column(DateTime(timezone=True), nullable=True)
    connected_phone = Column(String, nullable=True)
    bridge_status = Column(String, nullable=True)
    bridge_detail = Column(String, nullable=True)
    bridge_reachable = Column(Boolean, default=False)
    last_event_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WhatsAppBridgeEvent(Base):
    __tablename__ = "whatsapp_bridge_events"
    __table_args__ = (
        Index("ix_whatsapp_bridge_events_user_id_created_at", "user_id", "created_at"),
        Index("ix_whatsapp_bridge_events_event_type_created_at", "event_type", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_key = Column(String, nullable=True)
    event_type = Column(String, index=True)
    status = Column(String, nullable=True)
    detail = Column(String, nullable=True)
    connected_phone = Column(String, nullable=True)
    bridge_reachable = Column(Boolean, nullable=True)
    payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WhatsAppBridgeStateSnapshot(Base):
    __tablename__ = "whatsapp_bridge_state_snapshots"
    __table_args__ = (
        Index("ix_whatsapp_bridge_state_snapshots_user_id_created_at", "user_id", "created_at"),
        Index("ix_whatsapp_bridge_state_snapshots_status_created_at", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_key = Column(String, nullable=True)
    status = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    connected_phone = Column(String, nullable=True)
    bridge_status = Column(String, nullable=True)
    bridge_detail = Column(String, nullable=True)
    bridge_reachable = Column(Boolean, nullable=True)
    qr_present = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
