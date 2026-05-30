from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.ai.engine import ai_engine
from backend.auth import get_current_user
from backend.database.config import get_db
import backend.models.domain as models
import backend.schemas.domain as schemas


router = APIRouter()


def _message_base(message: models.Message) -> schemas.MessageBase:
    return schemas.MessageBase(
        sender=message.sender,
        sender_id=message.sender_id,
        sender_name=message.sender_name,
        message=message.message,
        external_message_id=message.external_message_id,
        source=message.source,
        direction=message.direction,
        is_from_me=bool(message.is_from_me),
        timestamp=message.timestamp,
        risk_score=message.risk_score,
        label=message.label,
    )


def _ensure_chat_access(chat: models.Chat | None, user: models.User) -> models.Chat:
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    if chat.user_id == user.id or any(participant.id == user.id for participant in chat.participants):
        return chat
    raise HTTPException(status_code=403, detail="You do not have access to this chat")


@router.post("/send", response_model=schemas.MessageSendResponse)
def send_message(
    payload: schemas.MessageSendRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required")

    chat = None
    if payload.chat_id is not None:
        chat = _ensure_chat_access(
            db.query(models.Chat).filter(models.Chat.id == payload.chat_id).first(),
            current_user,
        )
    else:
        chat_name = (payload.chat_name or "Direct moderation chat").strip()
        chat = models.Chat(
            user_id=current_user.id,
            platform=payload.platform,
            chat_name=chat_name,
            chat_type="direct",
            is_live=False,
            is_active=True,
        )
        chat.participants.append(current_user)
        db.add(chat)
        db.commit()
        db.refresh(chat)

    analysis = ai_engine.analyze_message(content)
    action = analysis.get("action") or ai_engine.action_for_score(analysis["risk_score"])
    severity = analysis.get("severity") or ai_engine.severity_for_score(analysis["risk_score"])
    blocked = action == "block"

    message = models.Message(
        chat_id=chat.id,
        sender=current_user.username or current_user.name or current_user.email,
        sender_user_id=current_user.id,
        sender_id=str(current_user.id),
        sender_name=current_user.name or current_user.username or current_user.email,
        message=content,
        content=content,
        source="api_messages_send",
        direction="outgoing",
        is_from_me=True,
        timestamp=datetime.now(timezone.utc),
        risk_score=analysis["risk_score"],
        toxicity_score=analysis["risk_score"],
        is_flagged=action in {"flag", "block"},
        label=analysis["label"],
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    toxicity_details = analysis.get("details", {}).get("toxicity", {})
    db.add(
        models.ModerationLog(
            message_id=message.id,
            toxic=toxicity_details.get("toxicity", 0.0),
            severe_toxic=toxicity_details.get("severe_toxic", 0.0),
            obscene=toxicity_details.get("obscene", 0.0),
            threat=toxicity_details.get("threat", 0.0),
            insult=toxicity_details.get("insult", 0.0),
            identity_hate=toxicity_details.get("identity_hate", 0.0),
            action=action,
        )
    )

    if action in {"flag", "block"}:
        db.add(
            models.Alert(
                message_id=message.id,
                alert_type=analysis["label"] or "Unsafe",
                severity=severity,
                status="open",
            )
        )
    chat.message_count = (chat.message_count or 0) + 1
    if action in {"flag", "block"}:
        chat.flagged_message_count = (chat.flagged_message_count or 0) + 1
    chat.last_message_at = message.timestamp
    db.commit()

    return schemas.MessageSendResponse(
        chat_id=chat.id,
        message_id=message.id,
        action=action,
        severity=severity,
        blocked=blocked,
        risk_score=analysis["risk_score"],
        label=analysis["label"],
    )


@router.get("/{chat_id}", response_model=schemas.MessageListResponse)
def get_messages(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    chat = _ensure_chat_access(
        db.query(models.Chat).filter(models.Chat.id == chat_id).first(),
        current_user,
    )
    messages = (
        db.query(models.Message)
        .filter(models.Message.chat_id == chat.id)
        .order_by(models.Message.timestamp.asc(), models.Message.id.asc())
        .all()
    )
    return schemas.MessageListResponse(
        chat_id=chat.id,
        chat_name=chat.chat_name,
        platform=chat.platform,
        total_messages=len(messages),
        messages=[_message_base(message) for message in messages],
    )
