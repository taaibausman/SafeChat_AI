from datetime import datetime, timezone
import json
import os
from urllib import error, request

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.ai.engine import ai_engine
from backend.api.realtime import manager
from backend.database.config import get_db
import backend.models.domain as models
import backend.schemas.domain as schemas

router = APIRouter()
BRIDGE_CONTROL_URL = os.getenv("WHATSAPP_BRIDGE_CONTROL_URL", "http://127.0.0.1:3011")

_status_state = {
    "status": "disconnected",
    "reason": "WhatsApp bridge not started",
    "qr": None,
    "qr_updated_at": None,
}


def _resolve_timestamp(timestamp: int | None) -> datetime:
    if timestamp:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _bridge_request(path: str, method: str = "GET") -> tuple[bool, dict | None, str | None]:
    url = f"{BRIDGE_CONTROL_URL}{path}"
    req = request.Request(url=url, method=method)
    try:
        with request.urlopen(req, timeout=3) as response:
            payload = response.read().decode("utf-8")
            return True, json.loads(payload) if payload else {}, None
    except error.URLError as exc:
        return False, None, str(exc.reason)
    except Exception as exc:
        return False, None, str(exc)


def _get_or_create_live_chat(db: Session, payload: schemas.IncomingWhatsAppMessage) -> models.Chat:
    chat_name = payload.group_name or payload.group_id or "WhatsApp Live Chat"
    chat = (
        db.query(models.Chat)
        .filter(models.Chat.platform == "WhatsApp_Live", models.Chat.chat_name == chat_name)
        .first()
    )
    if chat:
        return chat

    chat = models.Chat(platform="WhatsApp_Live", chat_name=chat_name)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@router.get("/status", response_model=schemas.WhatsAppStatusResponse)
def get_whatsapp_status():
    return schemas.WhatsAppStatusResponse(**_status_state)


@router.get("/bridge-health", response_model=schemas.WhatsAppBridgeHealthResponse)
def get_bridge_health():
    reachable, payload, detail = _bridge_request("/health")
    if not reachable:
        return schemas.WhatsAppBridgeHealthResponse(reachable=False, detail=detail)
    return schemas.WhatsAppBridgeHealthResponse(
        reachable=True,
        status=(payload or {}).get("status"),
        detail=(payload or {}).get("detail"),
    )


@router.post("/bridge-restart", response_model=schemas.WhatsAppBridgeHealthResponse)
def restart_bridge():
    reachable, payload, detail = _bridge_request("/restart", method="POST")
    if not reachable:
        return schemas.WhatsAppBridgeHealthResponse(reachable=False, detail=detail)
    return schemas.WhatsAppBridgeHealthResponse(
        reachable=True,
        status=(payload or {}).get("status"),
        detail="Restart signal sent to WhatsApp bridge.",
    )


@router.post("/status", response_model=schemas.WhatsAppStatusResponse)
async def update_whatsapp_status(payload: schemas.WhatsAppStatusUpdate):
    _status_state["status"] = payload.status
    _status_state["reason"] = payload.reason
    _status_state["qr"] = payload.qr
    _status_state["qr_updated_at"] = datetime.now(timezone.utc) if payload.qr else _status_state["qr_updated_at"]
    if payload.status == "connected":
        _status_state["qr"] = None
    response = schemas.WhatsAppStatusResponse(**_status_state)
    await manager.broadcast(
        {
            "type": "status",
            "payload": response.model_dump(mode="json"),
        }
    )
    return response


@router.get("/qr", response_model=schemas.WhatsAppStatusResponse)
def get_whatsapp_qr():
    return schemas.WhatsAppStatusResponse(**_status_state)


@router.post("/messages/incoming")
async def receive_incoming_message(payload: schemas.IncomingWhatsAppMessage, db: Session = Depends(get_db)):
    chat = _get_or_create_live_chat(db, payload)
    analysis = ai_engine.analyze_message(payload.text)

    message = models.Message(
        chat_id=chat.id,
        sender=payload.sender_name or payload.sender,
        message=payload.text,
        timestamp=_resolve_timestamp(payload.timestamp),
        risk_score=analysis["risk_score"],
        label=analysis["label"],
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    messages = db.query(models.Message).filter(models.Message.chat_id == chat.id).all()
    total_messages = len(messages)
    flagged_messages = sum(1 for item in messages if (item.risk_score or 0) > 50)
    total_score = sum((item.risk_score or 0) for item in messages)

    result = (
        db.query(models.AnalysisResult)
        .filter(models.AnalysisResult.chat_id == chat.id)
        .first()
    )
    safe_percentage = ((total_messages - flagged_messages) / total_messages * 100) if total_messages else 100.0
    unsafe_percentage = (flagged_messages / total_messages * 100) if total_messages else 0.0
    summary = f"Live monitoring has flagged {flagged_messages} messages out of {total_messages} in this chat."

    if result is None:
        result = models.AnalysisResult(
            chat_id=chat.id,
            overall_score=(total_score / total_messages) if total_messages else 0.0,
            safe_percentage=safe_percentage,
            unsafe_percentage=unsafe_percentage,
            summary=summary,
        )
        db.add(result)
    else:
        result.overall_score = (total_score / total_messages) if total_messages else 0.0
        result.safe_percentage = safe_percentage
        result.unsafe_percentage = unsafe_percentage
        result.summary = summary

    db.commit()

    live_message = schemas.LiveFeedMessage(
        id=message.id,
        chat_id=chat.id,
        chat_name=chat.chat_name,
        sender=message.sender,
        message=message.message,
        timestamp=message.timestamp,
        risk_score=message.risk_score,
        label=message.label,
    )
    await manager.broadcast(
        {
            "type": "message",
            "payload": live_message.model_dump(mode="json"),
        }
    )

    return {
        "chat_id": chat.id,
        "message_id": message.id,
        "label": analysis["label"],
        "risk_score": analysis["risk_score"],
    }


@router.get("/live-feed", response_model=schemas.LiveFeedResponse)
def get_live_feed(chat_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    query = (
        db.query(models.Message, models.Chat)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live")
    )
    if chat_id is not None:
        query = query.filter(models.Chat.id == chat_id)

    recent_messages = query.order_by(
        models.Message.timestamp.desc().nullslast(), models.Message.id.desc()
    ).limit(50).all()

    messages = [
        schemas.LiveFeedMessage(
            id=message.id,
            chat_id=chat.id,
            chat_name=chat.chat_name,
            sender=message.sender,
            message=message.message,
            timestamp=message.timestamp,
            risk_score=message.risk_score,
            label=message.label,
        )
        for message, chat in recent_messages
    ]
    return schemas.LiveFeedResponse(messages=messages)


@router.get("/chats", response_model=schemas.WhatsAppChatListResponse)
def get_live_chats(db: Session = Depends(get_db)):
    chats = (
        db.query(models.Chat)
        .filter(models.Chat.platform == "WhatsApp_Live")
        .order_by(models.Chat.created_at.desc(), models.Chat.id.desc())
        .all()
    )

    payload: list[schemas.WhatsAppChatSummary] = []
    for chat in chats:
        messages = list(chat.messages)
        message_count = len(messages)
        flagged_messages = sum(1 for item in messages if (item.risk_score or 0) > 50)
        unsafe_percentage = (flagged_messages / message_count * 100) if message_count else 0.0
        last_message_at = max((item.timestamp for item in messages if item.timestamp), default=None)
        payload.append(
            schemas.WhatsAppChatSummary(
                id=chat.id,
                chat_name=chat.chat_name,
                platform=chat.platform,
                message_count=message_count,
                flagged_messages=flagged_messages,
                unsafe_percentage=unsafe_percentage,
                last_message_at=last_message_at,
            )
        )

    return schemas.WhatsAppChatListResponse(chats=payload)
