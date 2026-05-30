from datetime import datetime, timedelta, timezone
import json
import os
from urllib import error, request

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from backend.ai.engine import ai_engine
from backend.api.realtime import manager
from backend.database.config import get_db
import backend.models.domain as models
import backend.schemas.domain as schemas

router = APIRouter()
BRIDGE_CONTROL_URL = os.getenv("WHATSAPP_BRIDGE_CONTROL_URL", "http://127.0.0.1:3011")
BRIDGE_EVENT_RETENTION = max(int(os.getenv("WHATSAPP_BRIDGE_EVENT_RETENTION", "1000")), 1)
BRIDGE_STATE_SNAPSHOT_RETENTION = max(int(os.getenv("WHATSAPP_BRIDGE_STATE_SNAPSHOT_RETENTION", "1000")), 1)


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


def _get_or_create_bridge_state(db: Session) -> models.WhatsAppBridgeState:
    state = db.query(models.WhatsAppBridgeState).order_by(models.WhatsAppBridgeState.id.asc()).first()
    if state:
        return state

    state = models.WhatsAppBridgeState()
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def _serialize_status(state: models.WhatsAppBridgeState) -> schemas.WhatsAppStatusResponse:
    return schemas.WhatsAppStatusResponse(
        status=state.status,
        reason=state.reason,
        qr=state.qr,
        qr_updated_at=state.qr_updated_at,
        connected_phone=state.connected_phone,
        bridge_reachable=bool(state.bridge_reachable),
        bridge_status=state.bridge_status,
        bridge_detail=state.bridge_detail,
        last_event_at=state.last_event_at,
    )


def _record_bridge_state_snapshot(db: Session, state: models.WhatsAppBridgeState) -> models.WhatsAppBridgeStateSnapshot:
    snapshot = models.WhatsAppBridgeStateSnapshot(
        status=state.status,
        reason=state.reason,
        connected_phone=state.connected_phone,
        bridge_status=state.bridge_status,
        bridge_detail=state.bridge_detail,
        bridge_reachable=state.bridge_reachable,
        qr_present=bool(state.qr),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    _prune_bridge_state_snapshots(db)
    return snapshot


def _prune_bridge_state_snapshots(db: Session, keep_latest: int | None = None) -> None:
    retention = keep_latest or BRIDGE_STATE_SNAPSHOT_RETENTION
    retained_ids = [
        snapshot_id
        for (snapshot_id,) in (
            db.query(models.WhatsAppBridgeStateSnapshot.id)
            .order_by(models.WhatsAppBridgeStateSnapshot.created_at.desc(), models.WhatsAppBridgeStateSnapshot.id.desc())
            .limit(retention)
            .all()
        )
    ]
    if not retained_ids:
        return

    (
        db.query(models.WhatsAppBridgeStateSnapshot)
        .filter(~models.WhatsAppBridgeStateSnapshot.id.in_(retained_ids))
        .delete(synchronize_session=False)
    )
    db.commit()


def _record_bridge_event(
    db: Session,
    event_type: str,
    status: str | None = None,
    detail: str | None = None,
    connected_phone: str | None = None,
    bridge_reachable: bool | None = None,
    payload: dict | None = None,
) -> models.WhatsAppBridgeEvent:
    event = models.WhatsAppBridgeEvent(
        event_type=event_type,
        status=status,
        detail=detail,
        connected_phone=connected_phone,
        bridge_reachable=bridge_reachable,
        payload=json.dumps(payload) if payload else None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    _prune_bridge_events(db)
    return event


def _prune_bridge_events(db: Session, keep_latest: int | None = None) -> None:
    retention = keep_latest or BRIDGE_EVENT_RETENTION
    retained_ids = [
        event_id
        for (event_id,) in (
            db.query(models.WhatsAppBridgeEvent.id)
            .order_by(models.WhatsAppBridgeEvent.created_at.desc(), models.WhatsAppBridgeEvent.id.desc())
            .limit(retention)
            .all()
        )
    ]
    if not retained_ids:
        return

    (
        db.query(models.WhatsAppBridgeEvent)
        .filter(~models.WhatsAppBridgeEvent.id.in_(retained_ids))
        .delete(synchronize_session=False)
    )
    db.commit()


def _serialize_bridge_event(event: models.WhatsAppBridgeEvent) -> schemas.WhatsAppBridgeEventResponse:
    return schemas.WhatsAppBridgeEventResponse(
        id=event.id,
        event_type=event.event_type,
        status=event.status,
        detail=event.detail,
        connected_phone=event.connected_phone,
        bridge_reachable=event.bridge_reachable,
        created_at=event.created_at,
    )


def _serialize_bridge_state_snapshot(
    snapshot: models.WhatsAppBridgeStateSnapshot,
) -> schemas.WhatsAppBridgeStateSnapshotResponse:
    return schemas.WhatsAppBridgeStateSnapshotResponse(
        id=snapshot.id,
        status=snapshot.status,
        reason=snapshot.reason,
        connected_phone=snapshot.connected_phone,
        bridge_status=snapshot.bridge_status,
        bridge_detail=snapshot.bridge_detail,
        bridge_reachable=snapshot.bridge_reachable,
        qr_present=bool(snapshot.qr_present),
        created_at=snapshot.created_at,
    )


def _latest_bridge_event(db: Session) -> models.WhatsAppBridgeEvent | None:
    return (
        db.query(models.WhatsAppBridgeEvent)
        .order_by(models.WhatsAppBridgeEvent.created_at.desc(), models.WhatsAppBridgeEvent.id.desc())
        .first()
    )


def _latest_bridge_state_snapshot(db: Session) -> models.WhatsAppBridgeStateSnapshot | None:
    return (
        db.query(models.WhatsAppBridgeStateSnapshot)
        .order_by(models.WhatsAppBridgeStateSnapshot.created_at.desc(), models.WhatsAppBridgeStateSnapshot.id.desc())
        .first()
    )


def _derive_chat_name(payload: schemas.IncomingWhatsAppMessage) -> str:
    if payload.group_name and payload.group_name != payload.group_id:
        return payload.group_name
    if payload.chat_type == "direct" and payload.sender_name:
        return payload.sender_name
    return payload.group_name or payload.group_id or payload.sender_name or payload.sender or "WhatsApp Live Chat"


def _get_or_create_live_chat(db: Session, payload: schemas.IncomingWhatsAppMessage) -> models.Chat:
    chat = None
    if payload.group_id:
        chat = (
            db.query(models.Chat)
            .filter(
                models.Chat.platform == "WhatsApp_Live",
                models.Chat.external_chat_id == payload.group_id,
            )
            .first()
        )

    if chat is None:
        chat = models.Chat(
            platform="WhatsApp_Live",
            chat_name=_derive_chat_name(payload),
            external_chat_id=payload.group_id,
            chat_type=payload.chat_type or "group",
            is_live=True,
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)
        return chat

    chat.chat_name = _derive_chat_name(payload)
    chat.chat_type = payload.chat_type or chat.chat_type or "group"
    chat.is_live = True
    db.commit()
    db.refresh(chat)
    return chat


def _recompute_chat_metrics(db: Session, chat: models.Chat) -> models.AnalysisResult:
    messages = (
        db.query(models.Message)
        .filter(models.Message.chat_id == chat.id)
        .order_by(models.Message.timestamp.asc(), models.Message.id.asc())
        .all()
    )
    total_messages = len(messages)
    flagged_messages = sum(1 for item in messages if (item.risk_score or 0) > 50)
    total_score = sum((item.risk_score or 0) for item in messages)
    latest_message_at = max((item.timestamp for item in messages if item.timestamp), default=None)

    chat.message_count = total_messages
    chat.flagged_message_count = flagged_messages
    chat.last_message_at = latest_message_at

    safe_percentage = ((total_messages - flagged_messages) / total_messages * 100) if total_messages else 100.0
    unsafe_percentage = (flagged_messages / total_messages * 100) if total_messages else 0.0
    summary = f"Live monitoring has flagged {flagged_messages} messages out of {total_messages} in this chat."

    result = db.query(models.AnalysisResult).filter(models.AnalysisResult.chat_id == chat.id).first()
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
    db.refresh(chat)
    db.refresh(result)
    return result


def _serialize_live_message(message: models.Message, chat: models.Chat) -> schemas.LiveFeedMessage:
    return schemas.LiveFeedMessage(
        id=message.id,
        chat_id=chat.id,
        chat_name=chat.chat_name,
        sender=message.sender,
        sender_id=message.sender_id,
        sender_name=message.sender_name,
        message=message.message,
        external_message_id=message.external_message_id,
        source=message.source,
        timestamp=message.timestamp,
        risk_score=message.risk_score,
        label=message.label,
    )


def _get_chat_alert_counts(db: Session, chat_id: int) -> dict[str, int]:
    rows = (
        db.query(models.Alert.status, func.count(models.Alert.id))
        .join(models.Message, models.Message.id == models.Alert.message_id)
        .filter(models.Message.chat_id == chat_id)
        .group_by(models.Alert.status)
        .all()
    )
    counts = {"total": 0, "open": 0, "acknowledged": 0, "resolved": 0}
    for status, count in rows:
        normalized = status or "open"
        counts["total"] += count
        if normalized in counts:
            counts[normalized] += count
    return counts


def _get_chat_alert_counts_in_window(
    db: Session,
    chat_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, int]:
    query = (
        db.query(models.Alert.status, func.count(models.Alert.id))
        .join(models.Message, models.Message.id == models.Alert.message_id)
        .filter(models.Message.chat_id == chat_id)
    )
    if date_from:
        query = query.filter(models.Message.timestamp >= date_from)
    if date_to:
        query = query.filter(models.Message.timestamp <= date_to)
    rows = query.group_by(models.Alert.status).all()
    counts = {"total": 0, "open": 0, "acknowledged": 0, "resolved": 0}
    for status, count in rows:
        normalized = status or "open"
        counts["total"] += count
        if normalized in counts:
            counts[normalized] += count
    return counts


def _get_chat_alert_counts_map(
    db: Session,
    chat_ids: list[int],
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[int, dict[str, int]]:
    counts_map = {
        chat_id: {"total": 0, "open": 0, "acknowledged": 0, "resolved": 0}
        for chat_id in chat_ids
    }
    if not chat_ids:
        return counts_map

    query = (
        db.query(models.Message.chat_id, models.Alert.status, func.count(models.Alert.id))
        .join(models.Alert, models.Alert.message_id == models.Message.id)
        .filter(models.Message.chat_id.in_(chat_ids))
    )
    if date_from:
        query = query.filter(models.Message.timestamp >= date_from)
    if date_to:
        query = query.filter(models.Message.timestamp <= date_to)
    rows = query.group_by(models.Message.chat_id, models.Alert.status).all()
    for chat_id, status, count in rows:
        normalized = status or "open"
        counts_map[chat_id]["total"] += count
        if normalized in counts_map[chat_id]:
            counts_map[chat_id][normalized] += count
    return counts_map


def _get_latest_message_preview_map(
    db: Session,
    chat_ids: list[int],
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[int, str | None]:
    previews = {chat_id: None for chat_id in chat_ids}
    if not chat_ids:
        return previews

    query = (
        db.query(models.Message)
        .filter(models.Message.chat_id.in_(chat_ids))
    )
    if date_from:
        query = query.filter(models.Message.timestamp >= date_from)
    if date_to:
        query = query.filter(models.Message.timestamp <= date_to)
    rows = query.order_by(
        models.Message.chat_id.asc(), models.Message.timestamp.desc().nullslast(), models.Message.id.desc()
    ).all()
    for message in rows:
        if previews.get(message.chat_id) is None:
            previews[message.chat_id] = message.message
    return previews


def _serialize_chat_summary(
    db: Session,
    chat: models.Chat,
    alert_counts: dict[str, int] | None = None,
    latest_message_preview: str | None = None,
) -> schemas.WhatsAppChatSummary:
    if latest_message_preview is None:
        latest_message = (
            db.query(models.Message)
            .filter(models.Message.chat_id == chat.id)
            .order_by(models.Message.timestamp.desc().nullslast(), models.Message.id.desc())
            .first()
        )
        latest_message_preview = latest_message.message if latest_message else None
    alert_counts = alert_counts or _get_chat_alert_counts(db, chat.id)
    unsafe_percentage = (chat.flagged_message_count / chat.message_count * 100) if chat.message_count else 0.0
    return schemas.WhatsAppChatSummary(
        id=chat.id,
        chat_name=chat.chat_name,
        platform=chat.platform,
        external_chat_id=chat.external_chat_id,
        chat_type=chat.chat_type,
        is_live=chat.is_live,
        message_count=chat.message_count or 0,
        flagged_messages=chat.flagged_message_count or 0,
        alert_count=alert_counts["total"],
        open_alert_count=alert_counts["open"],
        acknowledged_alert_count=alert_counts["acknowledged"],
        resolved_alert_count=alert_counts["resolved"],
        unsafe_percentage=unsafe_percentage,
        last_message_at=chat.last_message_at,
        latest_message_preview=latest_message_preview,
    )


def _serialize_alert(alert: models.Alert, message: models.Message, chat: models.Chat) -> schemas.LiveAlertResponse:
    return schemas.LiveAlertResponse(
        id=alert.id,
        message_id=message.id,
        chat_id=chat.id,
        chat_name=chat.chat_name,
        alert_type=alert.alert_type,
        severity=alert.severity,
        status=alert.status,
        notes=alert.notes,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
        created_at=alert.created_at,
        sender=message.sender,
        message=message.message,
        risk_score=message.risk_score,
        label=message.label,
        timestamp=message.timestamp,
    )


def _serialize_message_base(message: models.Message) -> schemas.MessageBase:
    return schemas.MessageBase(
        sender=message.sender,
        sender_id=message.sender_id,
        sender_name=message.sender_name,
        message=message.message,
        external_message_id=message.external_message_id,
        source=message.source,
        timestamp=message.timestamp,
        risk_score=message.risk_score,
        label=message.label,
    )


@router.get("/status", response_model=schemas.WhatsAppStatusResponse)
def get_whatsapp_status(db: Session = Depends(get_db)):
    return _serialize_status(_get_or_create_bridge_state(db))


@router.get("/bridge-health", response_model=schemas.WhatsAppBridgeHealthResponse)
def get_bridge_health(db: Session = Depends(get_db)):
    reachable, payload, detail = _bridge_request("/health")
    state = _get_or_create_bridge_state(db)
    state.bridge_reachable = reachable
    state.bridge_status = (payload or {}).get("status")
    state.bridge_detail = detail or (payload or {}).get("detail")
    state.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(state)
    _record_bridge_state_snapshot(db, state)
    _record_bridge_event(
        db,
        event_type="health_check",
        status=(payload or {}).get("status"),
        detail=detail or (payload or {}).get("detail"),
        connected_phone=state.connected_phone,
        bridge_reachable=reachable,
        payload=payload,
    )

    if not reachable:
        return schemas.WhatsAppBridgeHealthResponse(reachable=False, detail=detail)
    return schemas.WhatsAppBridgeHealthResponse(
        reachable=True,
        status=(payload or {}).get("status"),
        detail=(payload or {}).get("detail"),
    )


@router.post("/bridge-restart", response_model=schemas.WhatsAppBridgeHealthResponse)
def restart_bridge(db: Session = Depends(get_db)):
    reachable, payload, detail = _bridge_request("/restart", method="POST")
    state = _get_or_create_bridge_state(db)
    state.bridge_reachable = reachable
    state.bridge_status = (payload or {}).get("status")
    state.bridge_detail = detail or "Restart signal sent to WhatsApp bridge."
    state.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(state)
    _record_bridge_state_snapshot(db, state)
    _record_bridge_event(
        db,
        event_type="restart",
        status=(payload or {}).get("status"),
        detail=detail or "Restart signal sent to WhatsApp bridge.",
        connected_phone=state.connected_phone,
        bridge_reachable=reachable,
        payload=payload,
    )

    if not reachable:
        return schemas.WhatsAppBridgeHealthResponse(reachable=False, detail=detail)
    return schemas.WhatsAppBridgeHealthResponse(
        reachable=True,
        status=(payload or {}).get("status"),
        detail="Restart signal sent to WhatsApp bridge.",
    )


@router.post("/status", response_model=schemas.WhatsAppStatusResponse)
async def update_whatsapp_status(payload: schemas.WhatsAppStatusUpdate, db: Session = Depends(get_db)):
    state = _get_or_create_bridge_state(db)
    state.status = payload.status
    state.reason = payload.reason
    state.qr = payload.qr if payload.status != "connected" else None
    state.connected_phone = payload.connected_phone or state.connected_phone
    if payload.qr:
        state.qr_updated_at = datetime.now(timezone.utc)
    if payload.status == "connected":
        state.qr = None
    state.last_event_at = datetime.now(timezone.utc)
    state.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(state)
    _record_bridge_state_snapshot(db, state)
    _record_bridge_event(
        db,
        event_type="status_update",
        status=state.status,
        detail=state.reason,
        connected_phone=state.connected_phone,
        bridge_reachable=state.bridge_reachable,
        payload=payload.model_dump(exclude_none=True),
    )

    response = _serialize_status(state)
    await manager.broadcast({"type": "status", "payload": response.model_dump(mode="json")})
    return response


@router.get("/qr", response_model=schemas.WhatsAppStatusResponse)
def get_whatsapp_qr(db: Session = Depends(get_db)):
    return _serialize_status(_get_or_create_bridge_state(db))


@router.get("/bridge-events", response_model=schemas.WhatsAppBridgeEventListResponse)
def get_bridge_events(
    event_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(models.WhatsAppBridgeEvent)
    if event_type:
        query = query.filter(models.WhatsAppBridgeEvent.event_type == event_type)
    if status:
        query = query.filter(models.WhatsAppBridgeEvent.status == status)
    if date_from:
        query = query.filter(models.WhatsAppBridgeEvent.created_at >= date_from)
    if date_to:
        query = query.filter(models.WhatsAppBridgeEvent.created_at <= date_to)

    total = query.count()
    events = (
        query.order_by(models.WhatsAppBridgeEvent.created_at.desc(), models.WhatsAppBridgeEvent.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return schemas.WhatsAppBridgeEventListResponse(
        total=total,
        limit=limit,
        offset=offset,
        events=[_serialize_bridge_event(event) for event in events],
    )


@router.get("/bridge-events/summary", response_model=schemas.WhatsAppBridgeEventSummaryResponse)
def get_bridge_event_summary(
    event_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(models.WhatsAppBridgeEvent)
    if event_type:
        query = query.filter(models.WhatsAppBridgeEvent.event_type == event_type)
    if status:
        query = query.filter(models.WhatsAppBridgeEvent.status == status)
    if date_from:
        query = query.filter(models.WhatsAppBridgeEvent.created_at >= date_from)
    if date_to:
        query = query.filter(models.WhatsAppBridgeEvent.created_at <= date_to)

    rows = query.all()
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    latest_event_at = None

    for event in rows:
        by_type[event.event_type] = by_type.get(event.event_type, 0) + 1
        normalized_status = event.status or "unknown"
        by_status[normalized_status] = by_status.get(normalized_status, 0) + 1
        if latest_event_at is None or (event.created_at and event.created_at > latest_event_at):
            latest_event_at = event.created_at

    return schemas.WhatsAppBridgeEventSummaryResponse(
        total_events=len(rows),
        by_type=by_type,
        by_status=by_status,
        latest_event_at=latest_event_at,
    )


@router.get("/bridge-state-history", response_model=schemas.WhatsAppBridgeStateSnapshotListResponse)
def get_bridge_state_history(
    status: str | None = Query(default=None),
    bridge_status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(models.WhatsAppBridgeStateSnapshot)
    if status:
        query = query.filter(models.WhatsAppBridgeStateSnapshot.status == status)
    if bridge_status:
        query = query.filter(models.WhatsAppBridgeStateSnapshot.bridge_status == bridge_status)
    if date_from:
        query = query.filter(models.WhatsAppBridgeStateSnapshot.created_at >= date_from)
    if date_to:
        query = query.filter(models.WhatsAppBridgeStateSnapshot.created_at <= date_to)

    total = query.count()
    snapshots = (
        query.order_by(models.WhatsAppBridgeStateSnapshot.created_at.desc(), models.WhatsAppBridgeStateSnapshot.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return schemas.WhatsAppBridgeStateSnapshotListResponse(
        total=total,
        limit=limit,
        offset=offset,
        snapshots=[_serialize_bridge_state_snapshot(snapshot) for snapshot in snapshots],
    )


@router.get("/bridge-state-history/summary", response_model=schemas.WhatsAppBridgeStateSnapshotSummaryResponse)
def get_bridge_state_history_summary(
    status: str | None = Query(default=None),
    bridge_status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(models.WhatsAppBridgeStateSnapshot)
    if status:
        query = query.filter(models.WhatsAppBridgeStateSnapshot.status == status)
    if bridge_status:
        query = query.filter(models.WhatsAppBridgeStateSnapshot.bridge_status == bridge_status)
    if date_from:
        query = query.filter(models.WhatsAppBridgeStateSnapshot.created_at >= date_from)
    if date_to:
        query = query.filter(models.WhatsAppBridgeStateSnapshot.created_at <= date_to)

    snapshots = query.all()
    by_status: dict[str, int] = {}
    by_bridge_status: dict[str, int] = {}
    latest_snapshot_at = None

    for snapshot in snapshots:
        normalized_status = snapshot.status or "unknown"
        normalized_bridge_status = snapshot.bridge_status or "unknown"
        by_status[normalized_status] = by_status.get(normalized_status, 0) + 1
        by_bridge_status[normalized_bridge_status] = by_bridge_status.get(normalized_bridge_status, 0) + 1
        if latest_snapshot_at is None or (snapshot.created_at and snapshot.created_at > latest_snapshot_at):
            latest_snapshot_at = snapshot.created_at

    return schemas.WhatsAppBridgeStateSnapshotSummaryResponse(
        total_snapshots=len(snapshots),
        by_status=by_status,
        by_bridge_status=by_bridge_status,
        latest_snapshot_at=latest_snapshot_at,
    )


@router.get("/bridge-ops-summary", response_model=schemas.WhatsAppBridgeOpsSummaryResponse)
def get_bridge_ops_summary(
    recent_window_hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    state = _get_or_create_bridge_state(db)
    current_state = _serialize_status(state)
    latest_event = _latest_bridge_event(db)
    latest_snapshot = _latest_bridge_state_snapshot(db)
    window_start = datetime.now(timezone.utc) - timedelta(hours=recent_window_hours)

    recent_event_count = (
        db.query(func.count(models.WhatsAppBridgeEvent.id))
        .filter(models.WhatsAppBridgeEvent.created_at >= window_start)
        .scalar()
        or 0
    )
    recent_snapshot_count = (
        db.query(func.count(models.WhatsAppBridgeStateSnapshot.id))
        .filter(models.WhatsAppBridgeStateSnapshot.created_at >= window_start)
        .scalar()
        or 0
    )
    attention_required = (
        state.status not in {"connected"}
        or not bool(state.bridge_reachable)
        or state.bridge_status not in {None, "connected", "ready"}
    )

    return schemas.WhatsAppBridgeOpsSummaryResponse(
        current_state=current_state,
        latest_event=_serialize_bridge_event(latest_event) if latest_event else None,
        latest_snapshot=_serialize_bridge_state_snapshot(latest_snapshot) if latest_snapshot else None,
        recent_event_count=recent_event_count,
        recent_snapshot_count=recent_snapshot_count,
        recent_window_hours=recent_window_hours,
        bridge_reachable=bool(state.bridge_reachable),
        attention_required=attention_required,
    )


@router.post("/messages/incoming")
async def receive_incoming_message(payload: schemas.IncomingWhatsAppMessage, db: Session = Depends(get_db)):
    chat = _get_or_create_live_chat(db, payload)

    existing = None
    if payload.message_id:
        existing = (
            db.query(models.Message)
            .filter(
                models.Message.chat_id == chat.id,
                models.Message.external_message_id == payload.message_id,
            )
            .first()
        )
    if existing:
        return {
            "chat_id": chat.id,
            "message_id": existing.id,
            "label": existing.label,
            "risk_score": existing.risk_score,
            "duplicate": True,
        }

    analysis = ai_engine.analyze_message(payload.text)
    message = models.Message(
        chat_id=chat.id,
        sender=payload.sender_name or payload.sender,
        sender_id=payload.sender,
        sender_name=payload.sender_name,
        message=payload.text,
        external_message_id=payload.message_id,
        source="whatsapp_bridge",
        raw_payload=json.dumps(payload.raw_payload) if payload.raw_payload else None,
        timestamp=_resolve_timestamp(payload.timestamp),
        risk_score=analysis["risk_score"],
        label=analysis["label"],
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    if (message.risk_score or 0) > 50:
        severity = "High" if (message.risk_score or 0) >= 80 else "Medium"
        db.add(models.Alert(message_id=message.id, alert_type=message.label or "Unsafe", severity=severity, status="open"))
        db.commit()

    result = _recompute_chat_metrics(db, chat)
    live_message = _serialize_live_message(message, chat)
    chat_summary = _serialize_chat_summary(db, chat)

    await manager.broadcast({"type": "message", "payload": live_message.model_dump(mode="json")})
    await manager.broadcast(
        {
            "type": "chat_updated",
            "payload": {
                "chat": chat_summary.model_dump(mode="json"),
                "analysis": {
                    "chat_id": result.chat_id,
                    "overall_score": result.overall_score,
                    "safe_percentage": result.safe_percentage,
                    "unsafe_percentage": result.unsafe_percentage,
                    "summary": result.summary,
                },
            },
        }
    )

    return {
        "chat_id": chat.id,
        "message_id": message.id,
        "label": analysis["label"],
        "risk_score": analysis["risk_score"],
        "duplicate": False,
    }


@router.get("/live-feed", response_model=schemas.LiveFeedResponse)
def get_live_feed(
    chat_id: int | None = Query(default=None),
    flagged_only: bool = Query(default=False),
    sender: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.Message, models.Chat)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live")
    )
    if chat_id is not None:
        query = query.filter(models.Chat.id == chat_id)
    if flagged_only:
        query = query.filter(models.Message.risk_score > 50)
    if sender:
        query = query.filter(
            (models.Message.sender == sender)
            | (models.Message.sender_id == sender)
            | (models.Message.sender_name == sender)
        )
    if date_from:
        query = query.filter(models.Message.timestamp >= date_from)
    if date_to:
        query = query.filter(models.Message.timestamp <= date_to)

    total = query.count()
    recent_messages = query.order_by(
        models.Message.timestamp.desc().nullslast(), models.Message.id.desc()
    ).offset(offset).limit(limit).all()

    messages = [_serialize_live_message(message, chat) for message, chat in recent_messages]
    return schemas.LiveFeedResponse(total=total, limit=limit, offset=offset, messages=messages)


@router.get("/chats", response_model=schemas.WhatsAppChatListResponse)
def get_live_chats(
    search: str | None = Query(default=None),
    flagged_only: bool = Query(default=False),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if date_from or date_to:
        aggregate_query = (
            db.query(
                models.Message.chat_id.label("chat_id"),
                func.count(models.Message.id).label("message_count"),
                func.sum(case((models.Message.risk_score > 50, 1), else_=0)).label("flagged_count"),
                func.max(models.Message.timestamp).label("last_message_at"),
            )
            .join(models.Chat, models.Chat.id == models.Message.chat_id)
            .filter(models.Chat.platform == "WhatsApp_Live")
        )
        if search:
            aggregate_query = aggregate_query.filter(models.Chat.chat_name.ilike(f"%{search}%"))
        if date_from:
            aggregate_query = aggregate_query.filter(models.Message.timestamp >= date_from)
        if date_to:
            aggregate_query = aggregate_query.filter(models.Message.timestamp <= date_to)

        aggregate_subquery = aggregate_query.group_by(models.Message.chat_id).subquery()
        windowed_query = (
            db.query(
                models.Chat,
                aggregate_subquery.c.message_count,
                aggregate_subquery.c.flagged_count,
                aggregate_subquery.c.last_message_at,
            )
            .join(aggregate_subquery, aggregate_subquery.c.chat_id == models.Chat.id)
        )
        if flagged_only:
            windowed_query = windowed_query.filter(aggregate_subquery.c.flagged_count > 0)

        total = windowed_query.count()
        rows = (
            windowed_query.order_by(
                aggregate_subquery.c.last_message_at.desc().nullslast(),
                models.Chat.id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        chat_ids = [chat.id for chat, _, _, _ in rows]
        alert_counts_map = _get_chat_alert_counts_map(db, chat_ids, date_from=date_from, date_to=date_to)
        latest_preview_map = _get_latest_message_preview_map(db, chat_ids, date_from=date_from, date_to=date_to)

        chats = []
        for chat, message_count, flagged_count, last_message_at in rows:
            message_count = int(message_count or 0)
            flagged_count = int(flagged_count or 0)
            unsafe_percentage = (flagged_count / message_count * 100) if message_count else 0.0
            alert_counts = alert_counts_map.get(chat.id, {"total": 0, "open": 0, "acknowledged": 0, "resolved": 0})
            chats.append(
                schemas.WhatsAppChatSummary(
                    id=chat.id,
                    chat_name=chat.chat_name,
                    platform=chat.platform,
                    external_chat_id=chat.external_chat_id,
                    chat_type=chat.chat_type,
                    is_live=chat.is_live,
                    message_count=message_count,
                    flagged_messages=flagged_count,
                    alert_count=alert_counts["total"],
                    open_alert_count=alert_counts["open"],
                    acknowledged_alert_count=alert_counts["acknowledged"],
                    resolved_alert_count=alert_counts["resolved"],
                    unsafe_percentage=unsafe_percentage,
                    last_message_at=last_message_at,
                    latest_message_preview=latest_preview_map.get(chat.id),
                )
            )

        return schemas.WhatsAppChatListResponse(total=total, limit=limit, offset=offset, chats=chats)

    query = db.query(models.Chat).filter(models.Chat.platform == "WhatsApp_Live")
    if search:
        query = query.filter(models.Chat.chat_name.ilike(f"%{search}%"))
    if flagged_only:
        query = query.filter(models.Chat.flagged_message_count > 0)
    total = query.count()
    chats = query.order_by(models.Chat.last_message_at.desc().nullslast(), models.Chat.id.desc()).offset(offset).limit(limit).all()
    chat_ids = [chat.id for chat in chats]
    alert_counts_map = _get_chat_alert_counts_map(db, chat_ids)
    latest_preview_map = _get_latest_message_preview_map(db, chat_ids)
    return schemas.WhatsAppChatListResponse(
        total=total,
        limit=limit,
        offset=offset,
        chats=[
            _serialize_chat_summary(
                db,
                chat,
                alert_counts=alert_counts_map.get(chat.id),
                latest_message_preview=latest_preview_map.get(chat.id),
            )
            for chat in chats
        ],
    )


@router.get("/chats/summary", response_model=schemas.WhatsAppChatSummaryAggregateResponse)
def get_live_chat_summary(
    search: str | None = Query(default=None),
    flagged_only: bool = Query(default=False),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(models.Chat).filter(models.Chat.platform == "WhatsApp_Live")
    if search:
        query = query.filter(models.Chat.chat_name.ilike(f"%{search}%"))

    chats = query.all()
    if date_from or date_to:
        message_query = (
            db.query(models.Message, models.Chat)
            .join(models.Chat, models.Chat.id == models.Message.chat_id)
            .filter(models.Chat.platform == "WhatsApp_Live")
        )
        if search:
            message_query = message_query.filter(models.Chat.chat_name.ilike(f"%{search}%"))
        if date_from:
            message_query = message_query.filter(models.Message.timestamp >= date_from)
        if date_to:
            message_query = message_query.filter(models.Message.timestamp <= date_to)

        rows = message_query.all()
        by_chat_id: dict[int, dict[str, object]] = {}
        for message, chat in rows:
            chat_bucket = by_chat_id.setdefault(
                chat.id,
                {
                    "chat": chat,
                    "message_count": 0,
                    "flagged_count": 0,
                    "latest_message_at": None,
                },
            )
            chat_bucket["message_count"] = int(chat_bucket["message_count"]) + 1
            if (message.risk_score or 0) > 50:
                chat_bucket["flagged_count"] = int(chat_bucket["flagged_count"]) + 1
            if chat_bucket["latest_message_at"] is None or (
                message.timestamp and message.timestamp > chat_bucket["latest_message_at"]
            ):
                chat_bucket["latest_message_at"] = message.timestamp

        if flagged_only:
            by_chat_id = {
                chat_id: bucket for chat_id, bucket in by_chat_id.items() if int(bucket["flagged_count"]) > 0
            }

        by_chat_type: dict[str, int] = {}
        by_risk_state = {"safe": 0, "flagged": 0, "high_risk": 0}
        latest_message_at = None
        total_messages = 0

        for bucket in by_chat_id.values():
            chat = bucket["chat"]
            message_count = int(bucket["message_count"])
            flagged_messages = int(bucket["flagged_count"])
            bucket_latest = bucket["latest_message_at"]
            normalized_chat_type = chat.chat_type or "unknown"
            by_chat_type[normalized_chat_type] = by_chat_type.get(normalized_chat_type, 0) + 1
            total_messages += message_count

            if flagged_messages <= 0:
                by_risk_state["safe"] += 1
            else:
                by_risk_state["flagged"] += 1
                if message_count and flagged_messages / message_count >= 0.5:
                    by_risk_state["high_risk"] += 1

            if latest_message_at is None or (bucket_latest and bucket_latest > latest_message_at):
                latest_message_at = bucket_latest

        return schemas.WhatsAppChatSummaryAggregateResponse(
            total_chats=len(by_chat_id),
            total_messages=total_messages,
            flagged_chats=by_risk_state["flagged"],
            by_chat_type=by_chat_type,
            by_risk_state=by_risk_state,
            latest_message_at=latest_message_at,
        )

    if flagged_only:
        chats = [chat for chat in chats if (chat.flagged_message_count or 0) > 0]

    by_chat_type: dict[str, int] = {}
    by_risk_state = {"safe": 0, "flagged": 0, "high_risk": 0}
    latest_message_at = None
    total_messages = 0

    for chat in chats:
        normalized_chat_type = chat.chat_type or "unknown"
        by_chat_type[normalized_chat_type] = by_chat_type.get(normalized_chat_type, 0) + 1
        total_messages += chat.message_count or 0

        flagged_messages = chat.flagged_message_count or 0
        if flagged_messages <= 0:
            by_risk_state["safe"] += 1
        else:
            by_risk_state["flagged"] += 1
            if (chat.message_count or 0) and flagged_messages / (chat.message_count or 1) >= 0.5:
                by_risk_state["high_risk"] += 1

        if latest_message_at is None or (chat.last_message_at and chat.last_message_at > latest_message_at):
            latest_message_at = chat.last_message_at

    return schemas.WhatsAppChatSummaryAggregateResponse(
        total_chats=len(chats),
        total_messages=total_messages,
        flagged_chats=by_risk_state["flagged"],
        by_chat_type=by_chat_type,
        by_risk_state=by_risk_state,
        latest_message_at=latest_message_at,
    )


@router.get("/chats/{chat_id}", response_model=schemas.LiveChatDetailResponse)
def get_live_chat_detail(
    chat_id: int,
    flagged_only: bool = Query(default=False),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    chat = (
        db.query(models.Chat)
        .options(joinedload(models.Chat.analysis_results))
        .filter(models.Chat.id == chat_id, models.Chat.platform == "WhatsApp_Live")
        .first()
    )
    if not chat:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="WhatsApp live chat not found")
    message_query = db.query(models.Message).filter(models.Message.chat_id == chat.id)
    if date_from:
        message_query = message_query.filter(models.Message.timestamp >= date_from)
    if date_to:
        message_query = message_query.filter(models.Message.timestamp <= date_to)
    if flagged_only:
        message_query = message_query.filter(models.Message.risk_score > 50)
        total_messages = message_query.count()
    elif date_from or date_to:
        total_messages = message_query.count()
    else:
        total_messages = chat.message_count or 0
    messages = (
        message_query.order_by(models.Message.timestamp.desc().nullslast(), models.Message.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    if date_from or date_to:
        alert_counts = _get_chat_alert_counts_in_window(db, chat.id, date_from=date_from, date_to=date_to)
        last_message_query = db.query(func.max(models.Message.timestamp)).filter(models.Message.chat_id == chat.id)
        if date_from:
            last_message_query = last_message_query.filter(models.Message.timestamp >= date_from)
        if date_to:
            last_message_query = last_message_query.filter(models.Message.timestamp <= date_to)
        last_message_at = last_message_query.scalar()
    else:
        alert_counts = _get_chat_alert_counts(db, chat.id)
        last_message_at = chat.last_message_at
    return schemas.LiveChatDetailResponse(
        id=chat.id,
        platform=chat.platform,
        chat_name=chat.chat_name,
        external_chat_id=chat.external_chat_id,
        chat_type=chat.chat_type,
        is_live=chat.is_live,
        last_message_at=last_message_at,
        analysis_results=chat.analysis_results,
        total_messages=total_messages,
        alert_count=alert_counts["total"],
        open_alert_count=alert_counts["open"],
        acknowledged_alert_count=alert_counts["acknowledged"],
        resolved_alert_count=alert_counts["resolved"],
        limit=limit,
        offset=offset,
        messages=[_serialize_message_base(message) for message in messages],
    )


@router.get("/alerts", response_model=schemas.LiveAlertListResponse)
def get_live_alerts(
    chat_id: int | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.Alert, models.Message, models.Chat)
        .join(models.Message, models.Message.id == models.Alert.message_id)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live")
    )
    if chat_id is not None:
        query = query.filter(models.Chat.id == chat_id)
    if severity:
        query = query.filter(models.Alert.severity == severity)
    if status:
        query = query.filter(models.Alert.status == status)
    if date_from:
        query = query.filter(models.Alert.created_at >= date_from)
    if date_to:
        query = query.filter(models.Alert.created_at <= date_to)

    total = query.count()
    rows = query.order_by(models.Alert.created_at.desc(), models.Alert.id.desc()).offset(offset).limit(limit).all()
    alerts = [_serialize_alert(alert, message, chat) for alert, message, chat in rows]
    return schemas.LiveAlertListResponse(total=total, limit=limit, offset=offset, alerts=alerts)


@router.get("/alerts/summary", response_model=schemas.LiveAlertSummaryResponse)
def get_live_alert_summary(
    chat_id: int | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.Alert)
        .join(models.Message, models.Message.id == models.Alert.message_id)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live")
    )
    if chat_id is not None:
        query = query.filter(models.Chat.id == chat_id)
    if severity:
        query = query.filter(models.Alert.severity == severity)
    if status:
        query = query.filter(models.Alert.status == status)
    if date_from:
        query = query.filter(models.Alert.created_at >= date_from)
    if date_to:
        query = query.filter(models.Alert.created_at <= date_to)

    alerts = query.all()
    by_severity: dict[str, int] = {}
    by_status: dict[str, int] = {}
    latest_alert_at = None

    for alert in alerts:
        normalized_severity = alert.severity or "unknown"
        normalized_status = alert.status or "open"
        by_severity[normalized_severity] = by_severity.get(normalized_severity, 0) + 1
        by_status[normalized_status] = by_status.get(normalized_status, 0) + 1
        if latest_alert_at is None or (alert.created_at and alert.created_at > latest_alert_at):
            latest_alert_at = alert.created_at

    return schemas.LiveAlertSummaryResponse(
        total_alerts=len(alerts),
        by_severity=by_severity,
        by_status=by_status,
        latest_alert_at=latest_alert_at,
    )


@router.patch("/alerts/{alert_id}", response_model=schemas.LiveAlertResponse)
def update_live_alert(alert_id: int, payload: schemas.AlertUpdateRequest, db: Session = Depends(get_db)):
    from fastapi import HTTPException

    row = (
        db.query(models.Alert, models.Message, models.Chat)
        .join(models.Message, models.Message.id == models.Alert.message_id)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Alert.id == alert_id, models.Chat.platform == "WhatsApp_Live")
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Live alert not found")

    alert, message, chat = row
    now = datetime.now(timezone.utc)
    alert.status = payload.status
    alert.notes = payload.notes
    if payload.status == "acknowledged":
        alert.acknowledged_at = alert.acknowledged_at or now
        alert.resolved_at = None
    elif payload.status == "resolved":
        alert.acknowledged_at = alert.acknowledged_at or now
        alert.resolved_at = now
    else:
        alert.acknowledged_at = None
        alert.resolved_at = None
    db.commit()
    db.refresh(alert)
    return _serialize_alert(alert, message, chat)


@router.get("/summary", response_model=schemas.WhatsAppLiveSummaryResponse)
def get_live_summary(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    state = _get_or_create_bridge_state(db)
    message_query = (
        db.query(models.Message)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live")
    )
    if date_from:
        message_query = message_query.filter(models.Message.timestamp >= date_from)
    if date_to:
        message_query = message_query.filter(models.Message.timestamp <= date_to)

    alert_query = (
        db.query(models.Alert)
        .join(models.Message, models.Message.id == models.Alert.message_id)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live")
    )
    if date_from:
        alert_query = alert_query.filter(models.Alert.created_at >= date_from)
    if date_to:
        alert_query = alert_query.filter(models.Alert.created_at <= date_to)

    if date_from or date_to:
        total_live_chats = (
            message_query.with_entities(func.count(func.distinct(models.Message.chat_id))).scalar()
            or 0
        )
    else:
        total_live_chats = (
            db.query(func.count(models.Chat.id))
            .filter(models.Chat.platform == "WhatsApp_Live")
            .scalar()
            or 0
        )

    total_live_messages = message_query.with_entities(func.count(models.Message.id)).scalar() or 0
    flagged_live_messages = (
        message_query.filter(models.Message.risk_score > 50)
        .with_entities(func.count(models.Message.id))
        .scalar()
        or 0
    )
    total_alerts = alert_query.with_entities(func.count(models.Alert.id)).scalar() or 0
    open_alerts = (
        alert_query.filter(models.Alert.status == "open")
        .with_entities(func.count(models.Alert.id))
        .scalar()
        or 0
    )
    acknowledged_alerts = (
        alert_query.filter(models.Alert.status == "acknowledged")
        .with_entities(func.count(models.Alert.id))
        .scalar()
        or 0
    )
    resolved_alerts = (
        alert_query.filter(models.Alert.status == "resolved")
        .with_entities(func.count(models.Alert.id))
        .scalar()
        or 0
    )
    last_message_at = message_query.with_entities(func.max(models.Message.timestamp)).scalar()
    safe_ratio = ((total_live_messages - flagged_live_messages) / total_live_messages * 100) if total_live_messages else 100.0

    return schemas.WhatsAppLiveSummaryResponse(
        bridge_status=state.status,
        bridge_reachable=bool(state.bridge_reachable),
        connected_phone=state.connected_phone,
        total_live_chats=total_live_chats,
        total_live_messages=total_live_messages,
        flagged_live_messages=flagged_live_messages,
        total_alerts=total_alerts,
        open_alerts=open_alerts,
        acknowledged_alerts=acknowledged_alerts,
        resolved_alerts=resolved_alerts,
        safe_ratio=round(safe_ratio, 1),
        last_message_at=last_message_at,
    )


@router.get("/ops-summary", response_model=schemas.WhatsAppLiveOpsSummaryResponse)
def get_live_ops_summary(
    recent_window_hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    window_start = datetime.now(timezone.utc) - timedelta(hours=recent_window_hours)
    live_summary = get_live_summary(date_from=window_start, date_to=None, db=db)

    recent_feed_count = (
        db.query(func.count(models.Message.id))
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live", models.Message.timestamp >= window_start)
        .scalar()
        or 0
    )
    recent_alert_count = (
        db.query(func.count(models.Alert.id))
        .join(models.Message, models.Message.id == models.Alert.message_id)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live", models.Alert.created_at >= window_start)
        .scalar()
        or 0
    )
    recent_flagged_message_count = (
        db.query(func.count(models.Message.id))
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(
            models.Chat.platform == "WhatsApp_Live",
            models.Message.timestamp >= window_start,
            models.Message.risk_score > 50,
        )
        .scalar()
        or 0
    )

    recent_chats = (
        db.query(models.Chat)
        .join(models.Message, models.Message.chat_id == models.Chat.id)
        .filter(models.Chat.platform == "WhatsApp_Live", models.Message.timestamp >= window_start)
        .distinct()
        .all()
    )
    flagged_chat_count = 0
    high_risk_chat_count = 0
    for chat in recent_chats:
        message_count = (
            db.query(func.count(models.Message.id))
            .filter(models.Message.chat_id == chat.id, models.Message.timestamp >= window_start)
            .scalar()
            or 0
        )
        flagged_count = (
            db.query(func.count(models.Message.id))
            .filter(
                models.Message.chat_id == chat.id,
                models.Message.timestamp >= window_start,
                models.Message.risk_score > 50,
            )
            .scalar()
            or 0
        )
        if flagged_count > 0:
            flagged_chat_count += 1
            if message_count and flagged_count / message_count >= 0.5:
                high_risk_chat_count += 1

    attention_required = (
        live_summary.bridge_status != "connected"
        or not live_summary.bridge_reachable
        or live_summary.flagged_live_messages > 0
        or live_summary.open_alerts > 0
    )

    return schemas.WhatsAppLiveOpsSummaryResponse(
        live_summary=live_summary,
        recent_feed_count=recent_feed_count,
        recent_alert_count=recent_alert_count,
        recent_flagged_message_count=recent_flagged_message_count,
        flagged_chat_count=flagged_chat_count,
        high_risk_chat_count=high_risk_chat_count,
        recent_window_hours=recent_window_hours,
        attention_required=attention_required,
    )


@router.get("/health-summary", response_model=schemas.WhatsAppBackendHealthResponse)
def get_backend_health_summary(
    recent_window_hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    bridge_ops = get_bridge_ops_summary(recent_window_hours=recent_window_hours, db=db)
    live_ops = get_live_ops_summary(recent_window_hours=recent_window_hours, db=db)
    attention_required = bridge_ops.attention_required or live_ops.attention_required
    status = "attention" if attention_required else "healthy"
    return schemas.WhatsAppBackendHealthResponse(
        bridge_ops=bridge_ops,
        live_ops=live_ops,
        recent_window_hours=recent_window_hours,
        attention_required=attention_required,
        status=status,
    )
