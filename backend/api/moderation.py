from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

import backend.models.domain as models
import backend.schemas.domain as schemas
from backend.ai.engine import ai_engine
from backend.api.image_analyzer import (
    extract_text_from_image_bytes,
    persist_image_analysis,
    _segment_ocr_text_into_messages,
)
from backend.api.chat_analyzer import _build_analysis_payload
from backend.auth import get_current_admin, get_current_user
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


@router.post("/text", response_model=schemas.ModerateTextResponse)
def moderate_text(
    payload: schemas.ModerateTextRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    analysis = ai_engine.analyze_message(text)
    action = analysis.get("action") or ai_engine.action_for_score(analysis["risk_score"])
    severity = analysis.get("severity") or ai_engine.severity_for_score(analysis["risk_score"])
    saved_chat_id = None
    saved_message_id = None

    if payload.persist_result:
        chat = models.Chat(
            user_id=current_user.id,
            platform="Moderation_Text",
            chat_name=(payload.chat_name or "Direct text moderation").strip(),
            chat_type="direct",
            is_active=True,
        )
        chat.participants.append(current_user)
        db.add(chat)
        db.commit()
        db.refresh(chat)

        message = models.Message(
            chat_id=chat.id,
            sender=current_user.username or current_user.name or current_user.email,
            sender_user_id=current_user.id,
            sender_id=str(current_user.id),
            sender_name=current_user.name or current_user.username or current_user.email,
            message=text,
            content=text,
            source="moderate_text",
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
        db.commit()
        saved_chat_id = chat.id
        saved_message_id = message.id

    return schemas.ModerateTextResponse(
        chat_id=saved_chat_id,
        message_id=saved_message_id,
        text=text,
        action=action,
        severity=severity,
        risk_score=analysis["risk_score"],
        label=analysis["label"],
        blocked=action == "block",
        saved=payload.persist_result,
        thresholds=analysis.get("thresholds", {}),
        details=analysis.get("details", {}),
    )


@router.post("/image", response_model=schemas.ModerateImageResponse)
async def moderate_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are supported")

    content = await file.read()
    extracted_text = extract_text_from_image_bytes(content)
    analysis = ai_engine.analyze_message(extracted_text)
    chat, _image_scan = persist_image_analysis(
        db=db,
        filename=file.filename or "uploaded-image",
        extracted_text=extracted_text,
    )
    parsed_messages = _segment_ocr_text_into_messages(extracted_text)
    _total_messages, analysis_result, _ = _build_analysis_payload(
        parsed_messages,
        chat.id,
        chat.chat_name,
        persist=True,
        db=db,
    )
    db.add(
        models.AnalysisResult(
            chat_id=chat.id,
            overall_score=analysis_result.overall_score,
            safe_percentage=analysis_result.safe_percentage,
            unsafe_percentage=analysis_result.unsafe_percentage,
            summary=analysis_result.summary,
        )
    )
    db.commit()
    message = (
        db.query(models.Message)
        .filter(models.Message.chat_id == chat.id)
        .order_by(models.Message.id.desc())
        .first()
    )
    return schemas.ModerateImageResponse(
        chat_id=chat.id,
        message_id=message.id if message else None,
        extracted_text=extracted_text,
        action=analysis.get("action") or ai_engine.action_for_score(analysis["risk_score"]),
        severity=analysis.get("severity") or ai_engine.severity_for_score(analysis["risk_score"]),
        risk_score=analysis["risk_score"],
        label=analysis["label"],
        blocked=(analysis.get("action") or ai_engine.action_for_score(analysis["risk_score"])) == "block",
        saved=True,
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
