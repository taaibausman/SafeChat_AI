from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, Text, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.database.config import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    firebase_uid = Column(String, unique=True, index=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    chats = relationship("Chat", back_populates="owner")
    monitored_contacts = relationship("MonitoredContact", back_populates="user")

class Chat(Base):
    __tablename__ = "chats"
    __table_args__ = (
        Index("ix_chats_platform_external_chat_id", "platform", "external_chat_id"),
        Index("ix_chats_platform_last_message_at", "platform", "last_message_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    platform = Column(String)  # e.g., WhatsApp, Discord
    chat_name = Column(String)
    external_chat_id = Column(String, index=True, nullable=True)
    chat_type = Column(String, nullable=True)
    is_live = Column(Boolean, default=False)
    message_count = Column(Integer, default=0)
    flagged_message_count = Column(Integer, default=0)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="chats")
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
    sender_id = Column(String, nullable=True)
    sender_name = Column(String, nullable=True)
    message = Column(String)
    external_message_id = Column(String, index=True, nullable=True)
    source = Column(String, nullable=True)
    raw_payload = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    risk_score = Column(Float, nullable=True)
    label = Column(String, nullable=True)  # Safe, Unsafe, Toxic, etc.

    chat = relationship("Chat", back_populates="messages")
    alerts = relationship("Alert", back_populates="message")

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
    severity = Column(String)  # High, Medium, Low
    status = Column(String, default="open")
    notes = Column(Text, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    message = relationship("Message", back_populates="alerts")

class MonitoredContact(Base):
    __tablename__ = "monitored_contacts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    contact_name = Column(String)
    phone_number = Column(String)
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="monitored_contacts")


class WhatsAppBridgeState(Base):
    __tablename__ = "whatsapp_bridge_state"

    id = Column(Integer, primary_key=True, index=True)
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
        Index("ix_whatsapp_bridge_events_event_type_created_at", "event_type", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
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
        Index("ix_whatsapp_bridge_state_snapshots_status_created_at", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    connected_phone = Column(String, nullable=True)
    bridge_status = Column(String, nullable=True)
    bridge_detail = Column(String, nullable=True)
    bridge_reachable = Column(Boolean, nullable=True)
    qr_present = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
