from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import backend.models.domain as models
import backend.schemas.domain as schemas
from backend.auth import get_current_admin
from backend.database.config import get_db


router = APIRouter()


def _serialize_log(row: models.ModerationLog) -> schemas.ModerationLogResponse:
    message = row.message
    chat = message.chat if message else None
    return schemas.ModerationLogResponse(
        id=row.id,
        message_id=row.message_id,
        chat_id=chat.id if chat else 0,
        chat_name=chat.chat_name if chat else "Unknown chat",
        sender=message.sender if message else "Unknown sender",
        message=message.message if message else "",
        toxic=row.toxic,
        severe_toxic=row.severe_toxic,
        obscene=row.obscene,
        threat=row.threat,
        insult=row.insult,
        identity_hate=row.identity_hate,
        action=row.action,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
    )


@router.get("/logs", response_model=schemas.ModerationLogListResponse)
def list_moderation_logs(
    action: str | None = Query(default=None),
    reviewed_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_admin),
):
    query = db.query(models.ModerationLog)
    if action:
        query = query.filter(models.ModerationLog.action == action)
    if reviewed_only:
        query = query.filter(models.ModerationLog.reviewed_at.isnot(None))

    total = query.count()
    logs = (
        query.order_by(models.ModerationLog.created_at.desc(), models.ModerationLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return schemas.ModerationLogListResponse(
        total=total,
        limit=limit,
        offset=offset,
        logs=[_serialize_log(log) for log in logs],
    )


@router.patch("/logs/{log_id}", response_model=schemas.ModerationLogResponse)
def update_moderation_log(
    log_id: int,
    payload: schemas.ModerationLogUpdateRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    log = db.query(models.ModerationLog).filter(models.ModerationLog.id == log_id).first()
    if log is None:
        raise HTTPException(status_code=404, detail="Moderation log not found")

    log.action = payload.action
    log.reviewed_by = admin.id
    log.reviewed_at = datetime.now(timezone.utc)

    message = db.query(models.Message).filter(models.Message.id == log.message_id).first()
    if message is not None:
        message.is_flagged = payload.action in {"flag", "block"}
        message.label = "Blocked" if payload.action == "block" else message.label

        for alert in message.alerts:
            if payload.action == "allow":
                alert.status = "resolved"
                alert.resolved_at = log.reviewed_at
                alert.acknowledged_at = alert.acknowledged_at or log.reviewed_at
            elif payload.action == "flag":
                alert.status = "acknowledged"
                alert.acknowledged_at = alert.acknowledged_at or log.reviewed_at
                alert.resolved_at = None
            elif payload.action == "block":
                alert.status = "open"
                alert.resolved_at = None

    db.commit()
    db.refresh(log)
    return _serialize_log(log)
