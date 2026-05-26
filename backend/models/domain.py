from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database.config import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    firebase_uid = Column(String, unique=True, index=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    chats = relationship("Chat", back_populates="owner")
    monitored_contacts = relationship("MonitoredContact", back_populates="user")

class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    platform = Column(String)  # e.g., WhatsApp, Discord
    chat_name = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat")
    analysis_results = relationship("AnalysisResult", back_populates="chat", uselist=False)

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    sender = Column(String)
    message = Column(String)
    timestamp = Column(DateTime)
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    message = relationship("Message", back_populates="alerts")

class MonitoredContact(Base):
    __tablename__ = "monitored_contacts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    contact_name = Column(String)
    phone_number = Column(String)
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="monitored_contacts")
