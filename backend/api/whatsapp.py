from datetime import datetime, timedelta, timezone
import json
import os
from urllib import error, request

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from backend.ai.engine import ai_engine
from backend.api.realtime import manager
from backend.auth import get_current_user, get_optional_current_user
from backend.database.config import get_db
import backend.models.domain as models
import backend.schemas.domain as schemas

router = APIRouter()
BRIDGE_CONTROL_URL = os.getenv("WHATSAPP_BRIDGE_CONTROL_URL", "http://127.0.0.1:3011")
BRIDGE_EVENT_RETENTION = max(int(os.getenv("WHATSAPP_BRIDGE_EVENT_RETENTION", "1000")), 1)
BRIDGE_STATE_SNAPSHOT_RETENTION = max(int(os.getenv("WHATSAPP_BRIDGE_STATE_SNAPSHOT_RETENTION", "1000")), 1)


def _env_flag(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def _single_account_mode_enabled() -> bool:
    return _env_flag("SAFECHAT_WHATSAPP_SINGLE_ACCOUNT_MODE", "0")


def _auto_forward_all_live_messages() -> bool:
    default = "1" if _single_account_mode_enabled() else "0"
    return _env_flag("SAFECHAT_WHATSAPP_AUTO_FORWARD_ALL", default)


def _demo_bridge_session_key() -> str:
    normalized = _normalize_chat_key(os.getenv("SAFECHAT_WHATSAPP_DEMO_SESSION_KEY", "safechat-demo"))
    return normalized or "safechat-demo"


def _demo_owner_email() -> str | None:
    value = str(
        os.getenv("SAFECHAT_WHATSAPP_DEMO_OWNER_EMAIL")
        or os.getenv("SAFECHAT_DEFAULT_ADMIN_EMAIL")
        or ""
    ).strip().lower()
    return value or None


def _resolve_timestamp(timestamp: int | None) -> datetime:
    if timestamp:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _bridge_session_key_for_user(user: models.User) -> str:
    if _single_account_mode_enabled():
        return _demo_bridge_session_key()
    return f"user-{user.id}"


def _bridge_user_id_from_session_key(session_key: str | None) -> int | None:
    raw = str(session_key or "").strip().lower()
    if not raw.startswith("user-"):
        return None
    try:
        return int(raw.split("-", 1)[1])
    except (TypeError, ValueError):
        return None


def _bridge_request(
    path: str,
    method: str = "GET",
    query: dict[str, str] | None = None,
) -> tuple[bool, dict | None, str | None]:
    url = f"{BRIDGE_CONTROL_URL}{path}"
    if query:
        from urllib.parse import urlencode

        url = f"{url}?{urlencode(query)}"
    req = request.Request(url=url, method=method)
    try:
        with request.urlopen(req, timeout=3) as response:
            payload = response.read().decode("utf-8")
            return True, json.loads(payload) if payload else {}, None
    except error.URLError as exc:
        return False, None, str(exc.reason)
    except Exception as exc:
        return False, None, str(exc)


def _get_or_create_bridge_state(
    db: Session,
    *,
    user_id: int | None = None,
    session_key: str | None = None,
) -> models.WhatsAppBridgeState:
    query = db.query(models.WhatsAppBridgeState)
    if session_key:
        state = query.filter(models.WhatsAppBridgeState.session_key == session_key).first()
    elif user_id is not None:
        state = query.filter(models.WhatsAppBridgeState.user_id == user_id).first()
    else:
        state = query.order_by(models.WhatsAppBridgeState.id.asc()).first()
    if state:
        return state

    state = models.WhatsAppBridgeState(user_id=user_id, session_key=session_key)
    db.add(state)
    try:
        db.commit()
        db.refresh(state)
        return state
    except IntegrityError:
        db.rollback()
        query = db.query(models.WhatsAppBridgeState)
        if session_key:
            existing = query.filter(models.WhatsAppBridgeState.session_key == session_key).first()
        elif user_id is not None:
            existing = query.filter(models.WhatsAppBridgeState.user_id == user_id).first()
        else:
            existing = query.order_by(models.WhatsAppBridgeState.id.asc()).first()
        if existing:
            return existing
        raise


def _serialize_status(state: models.WhatsAppBridgeState) -> schemas.WhatsAppStatusResponse:
    return schemas.WhatsAppStatusResponse(
        bridge_session_key=state.session_key,
        single_account_mode=_single_account_mode_enabled(),
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
        user_id=state.user_id,
        session_key=state.session_key,
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


def _resolve_demo_owner_user(db: Session) -> models.User | None:
    email = _demo_owner_email()
    if email:
        owner = (
            db.query(models.User)
            .filter(
                func.lower(models.User.email) == email,
                models.User.is_active.is_(True),
            )
            .first()
        )
        if owner is not None:
            return owner

    owner = (
        db.query(models.User)
        .filter(models.User.role == "admin", models.User.is_active.is_(True))
        .order_by(models.User.id.asc())
        .first()
    )
    if owner is not None:
        return owner

    return (
        db.query(models.User)
        .filter(models.User.is_active.is_(True))
        .order_by(models.User.id.asc())
        .first()
    )


def _resolve_bridge_owner_user(
    db: Session,
    *,
    session_key: str | None = None,
    fallback_user_id: int | None = None,
) -> models.User | None:
    user_id = _bridge_user_id_from_session_key(session_key)
    if user_id is not None:
        return (
            db.query(models.User)
            .filter(models.User.id == user_id, models.User.is_active.is_(True))
            .first()
        )
    if _single_account_mode_enabled():
        return _resolve_demo_owner_user(db)
    if fallback_user_id is None:
        return None
    return (
        db.query(models.User)
        .filter(models.User.id == fallback_user_id, models.User.is_active.is_(True))
        .first()
    )


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
    user_id: int | None = None,
    session_key: str | None = None,
    status: str | None = None,
    detail: str | None = None,
    connected_phone: str | None = None,
    bridge_reachable: bool | None = None,
    payload: dict | None = None,
) -> models.WhatsAppBridgeEvent:
    event = models.WhatsAppBridgeEvent(
        user_id=user_id,
        session_key=session_key,
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


def _get_or_create_live_chat(
    db: Session,
    payload: schemas.IncomingWhatsAppMessage,
    *,
    owner_user_id: int | None = None,
) -> models.Chat:
    chat = None
    if payload.group_id:
        chat = (
            db.query(models.Chat)
            .filter(
                models.Chat.platform == "WhatsApp_Live",
                models.Chat.user_id == owner_user_id,
                models.Chat.external_chat_id == payload.group_id,
            )
            .first()
        )

    if chat is None:
        chat = models.Chat(
            user_id=owner_user_id,
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
    if chat.user_id is None:
        chat.user_id = owner_user_id
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
        direction=message.direction,
        is_from_me=bool(message.is_from_me),
        timestamp=message.timestamp,
        risk_score=message.risk_score,
        label=message.label,
    )


def _normalize_chat_key(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or ch in {"-", "_"})


def _direct_key_matches(message_key: str, monitor_key: str) -> bool:
    return (
        message_key == monitor_key
        or message_key.endswith(monitor_key)
        or monitor_key.endswith(message_key)
    )


def _message_candidate_keys(payload: schemas.IncomingWhatsAppMessage) -> list[str]:
    return [
        value
        for value in (
            _normalize_chat_key(payload.group_id),
            _normalize_chat_key(payload.sender),
            _normalize_chat_key(payload.group_name),
            _normalize_chat_key(payload.sender_name),
        )
        if value
    ]


def _contact_matches_payload(contact: models.MonitoredContact, payload: schemas.IncomingWhatsAppMessage) -> bool:
    if not contact.is_active:
        return False
    if (contact.chat_type or "direct") != (payload.chat_type or "direct"):
        return False

    monitor_keys = [
        value
        for value in (
            _normalize_chat_key(contact.chat_key),
            _normalize_chat_key(contact.phone_number),
            _normalize_chat_key(contact.contact_name),
        )
        if value
    ]
    message_keys = _message_candidate_keys(payload)
    if not monitor_keys or not message_keys:
        return False

    if (payload.chat_type or "direct") == "direct":
        return any(_direct_key_matches(message_key, monitor_key) for monitor_key in monitor_keys for message_key in message_keys)
    return any(message_key == monitor_key for monitor_key in monitor_keys for message_key in message_keys)


def _get_live_chat_access_filter(current_user: models.User | None):
    if current_user is None or (current_user.role or "user") == "admin":
        return None
    return (
        (models.Chat.user_id == current_user.id)
        | (models.Chat.participants.any(models.User.id == current_user.id))
    )


def _serialize_monitored_contact(contact: models.MonitoredContact) -> schemas.MonitoredContactResponse:
    return schemas.MonitoredContactResponse(
        id=contact.id,
        user_id=contact.user_id,
        contact_name=contact.contact_name,
        phone_number=contact.phone_number,
        chat_key=contact.chat_key or contact.phone_number or "",
        chat_type=contact.chat_type or "direct",
        is_active=bool(contact.is_active),
        created_at=contact.created_at,
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


def _build_live_chat_window_aggregate_query(
    db: Session,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    current_user: models.User | None = None,
):
    query = (
        db.query(
            models.Message.chat_id.label("chat_id"),
            models.Chat.chat_type.label("chat_type"),
            func.count(models.Message.id).label("message_count"),
            func.sum(case((models.Message.risk_score > 50, 1), else_=0)).label("flagged_count"),
            func.max(models.Message.timestamp).label("last_message_at"),
        )
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live")
    )
    access_filter = _get_live_chat_access_filter(current_user)
    if access_filter is not None:
        query = query.filter(access_filter)
    if search:
        query = query.filter(models.Chat.chat_name.ilike(f"%{search}%"))
    if date_from:
        query = query.filter(models.Message.timestamp >= date_from)
    if date_to:
        query = query.filter(models.Message.timestamp <= date_to)
    return query.group_by(models.Message.chat_id, models.Chat.chat_type)


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
        direction=message.direction,
        is_from_me=bool(message.is_from_me),
        timestamp=message.timestamp,
        risk_score=message.risk_score,
        label=message.label,
    )


@router.get("/status", response_model=schemas.WhatsAppStatusResponse)
def get_whatsapp_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_key = _bridge_session_key_for_user(current_user)
    return _serialize_status(_get_or_create_bridge_state(db, user_id=current_user.id, session_key=session_key))


@router.get("/bridge-health", response_model=schemas.WhatsAppBridgeHealthResponse)
def get_bridge_health(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_key = _bridge_session_key_for_user(current_user)
    reachable, payload, detail = _bridge_request("/health", query={"session_key": session_key})
    payload_status = (payload or {}).get("status")
    payload_detail = detail or (payload or {}).get("detail")
    state = _get_or_create_bridge_state(db, user_id=current_user.id, session_key=session_key)
    if payload_status:
        state.status = payload_status
    state.reason = payload_detail
    state.bridge_reachable = reachable
    state.bridge_status = payload_status
    state.bridge_detail = payload_detail
    state.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(state)
    _record_bridge_state_snapshot(db, state)
    _record_bridge_event(
        db,
        event_type="health_check",
        user_id=current_user.id,
        session_key=session_key,
        status=payload_status,
        detail=payload_detail,
        connected_phone=state.connected_phone,
        bridge_reachable=reachable,
        payload=payload,
    )

    if not reachable:
        return schemas.WhatsAppBridgeHealthResponse(reachable=False, detail=detail)
    return schemas.WhatsAppBridgeHealthResponse(
        reachable=True,
        status=payload_status,
        detail=(payload or {}).get("detail"),
    )


@router.get("/chat-directory", response_model=schemas.WhatsAppChatDirectoryResponse)
def get_chat_directory(
    search: str | None = Query(default=None),
    limit: int = Query(default=40, ge=1, le=200),
    current_user: models.User = Depends(get_current_user),
):
    session_key = _bridge_session_key_for_user(current_user)
    reachable, payload, detail = _bridge_request(
        "/directory",
        query={
            "session_key": session_key,
            "search": (search or "").strip(),
            "limit": str(limit),
        },
    )
    if not reachable:
        return schemas.WhatsAppChatDirectoryResponse(
            reachable=False,
            status="disconnected",
            detail=detail,
            total=0,
            items=[],
        )

    payload = payload or {}
    raw_items = payload.get("items") or []
    items = [
        schemas.WhatsAppChatDirectoryEntry(
            chat_key=str(item.get("chat_key") or ""),
            chat_type=str(item.get("chat_type") or "direct"),
            display_name=str(item.get("display_name") or item.get("chat_key") or "Unknown chat"),
            phone_number=item.get("phone_number"),
            source=str(item.get("source") or "recent"),
            recent_message_count=int(item.get("recent_message_count") or 0),
            last_activity_at=datetime.fromisoformat(item["last_activity_at"])
            if item.get("last_activity_at")
            else None,
            is_monitored=bool(item.get("is_monitored")),
        )
        for item in raw_items
        if item.get("chat_key")
    ]
    return schemas.WhatsAppChatDirectoryResponse(
        reachable=True,
        status=payload.get("status"),
        detail=payload.get("detail"),
        total=int(payload.get("total") or len(items)),
        items=items,
    )


@router.post("/bridge-restart", response_model=schemas.WhatsAppBridgeHealthResponse)
def restart_bridge(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_key = _bridge_session_key_for_user(current_user)
    reachable, payload, detail = _bridge_request("/restart", method="POST", query={"session_key": session_key})
    payload_status = (payload or {}).get("status")
    state = _get_or_create_bridge_state(db, user_id=current_user.id, session_key=session_key)
    if payload_status:
        state.status = payload_status
    state.reason = detail or "Restart signal sent to WhatsApp bridge."
    state.bridge_reachable = reachable
    state.bridge_status = payload_status
    state.bridge_detail = detail or "Restart signal sent to WhatsApp bridge."
    state.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(state)
    _record_bridge_state_snapshot(db, state)
    _record_bridge_event(
        db,
        event_type="restart",
        user_id=current_user.id,
        session_key=session_key,
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
    session_key = payload.bridge_session_key or (_demo_bridge_session_key() if _single_account_mode_enabled() else None)
    owner = _resolve_bridge_owner_user(db, session_key=session_key)
    user_id = owner.id if owner is not None else _bridge_user_id_from_session_key(session_key)
    if session_key and user_id is not None:
        state = _get_or_create_bridge_state(db, user_id=user_id, session_key=session_key)
    else:
        state = _get_or_create_bridge_state(db)
    state.status = payload.status
    state.reason = payload.reason
    if payload.status == "connected":
        state.qr = None
    elif payload.qr:
        state.qr = payload.qr
    state.connected_phone = payload.connected_phone or state.connected_phone
    if payload.qr:
        state.qr_updated_at = datetime.now(timezone.utc)
    state.last_event_at = datetime.now(timezone.utc)
    state.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(state)
    _record_bridge_state_snapshot(db, state)
    _record_bridge_event(
        db,
        event_type="status_update",
        user_id=user_id,
        session_key=session_key,
        status=state.status,
        detail=state.reason,
        connected_phone=state.connected_phone,
        bridge_reachable=state.bridge_reachable,
        payload=payload.model_dump(exclude_none=True),
    )

    response = _serialize_status(state)
    await manager.broadcast(
        {"type": "status", "payload": response.model_dump(mode="json")},
        audience_user_ids=[user_id] if user_id is not None else None,
    )
    return response


@router.get("/qr", response_model=schemas.WhatsAppStatusResponse)
def get_whatsapp_qr(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_key = _bridge_session_key_for_user(current_user)
    return _serialize_status(_get_or_create_bridge_state(db, user_id=current_user.id, session_key=session_key))


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
    current_user: models.User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    is_admin = current_user is not None and (current_user.role or "user") == "admin"
    session_key = _bridge_session_key_for_user(current_user) if current_user is not None else None
    if current_user is not None and not is_admin:
        state = _get_or_create_bridge_state(db, user_id=current_user.id, session_key=session_key)
    else:
        state = _get_or_create_bridge_state(db)
    current_state = _serialize_status(state)
    event_query = db.query(models.WhatsAppBridgeEvent)
    snapshot_query = db.query(models.WhatsAppBridgeStateSnapshot)
    if current_user is not None and not is_admin:
        event_query = event_query.filter(models.WhatsAppBridgeEvent.user_id == current_user.id)
        snapshot_query = snapshot_query.filter(models.WhatsAppBridgeStateSnapshot.user_id == current_user.id)
    latest_event = event_query.order_by(models.WhatsAppBridgeEvent.created_at.desc(), models.WhatsAppBridgeEvent.id.desc()).first()
    latest_snapshot = snapshot_query.order_by(models.WhatsAppBridgeStateSnapshot.created_at.desc(), models.WhatsAppBridgeStateSnapshot.id.desc()).first()
    window_start = datetime.now(timezone.utc) - timedelta(hours=recent_window_hours)

    recent_event_count_query = db.query(func.count(models.WhatsAppBridgeEvent.id)).filter(models.WhatsAppBridgeEvent.created_at >= window_start)
    recent_snapshot_count_query = db.query(func.count(models.WhatsAppBridgeStateSnapshot.id)).filter(models.WhatsAppBridgeStateSnapshot.created_at >= window_start)
    if current_user is not None and not is_admin:
        recent_event_count_query = recent_event_count_query.filter(models.WhatsAppBridgeEvent.user_id == current_user.id)
        recent_snapshot_count_query = recent_snapshot_count_query.filter(models.WhatsAppBridgeStateSnapshot.user_id == current_user.id)
    recent_event_count = recent_event_count_query.scalar() or 0
    recent_snapshot_count = recent_snapshot_count_query.scalar() or 0
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


@router.get("/monitored-contacts", response_model=schemas.MonitoredContactListResponse)
def list_monitored_contacts(
    active_only: bool = Query(default=False),
    chat_type: str | None = Query(default=None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.MonitoredContact)
        .filter(models.MonitoredContact.user_id == current_user.id)
        .order_by(models.MonitoredContact.is_active.desc(), models.MonitoredContact.contact_name.asc())
    )
    if active_only:
        query = query.filter(models.MonitoredContact.is_active.is_(True))
    if chat_type:
        query = query.filter(models.MonitoredContact.chat_type == chat_type)
    contacts = query.all()
    return schemas.MonitoredContactListResponse(
        total=len(contacts),
        contacts=[_serialize_monitored_contact(contact) for contact in contacts],
    )


@router.get("/bridge/monitored-contacts", response_model=schemas.MonitoredContactListResponse)
def list_bridge_monitored_contacts(
    session_key: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    chat_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    owner = _resolve_bridge_owner_user(db, session_key=session_key)
    if owner is None:
        raise HTTPException(status_code=400, detail="Valid bridge session key is required")

    query = db.query(models.MonitoredContact).filter(models.MonitoredContact.user_id == owner.id)
    if active_only:
        query = query.filter(models.MonitoredContact.is_active.is_(True))
    if chat_type:
        query = query.filter(models.MonitoredContact.chat_type == chat_type)
    contacts = query.order_by(models.MonitoredContact.contact_name.asc()).all()
    return schemas.MonitoredContactListResponse(
        total=len(contacts),
        contacts=[_serialize_monitored_contact(contact) for contact in contacts],
    )


@router.post("/monitored-contacts", response_model=schemas.MonitoredContactResponse)
def create_monitored_contact(
    payload: schemas.MonitoredContactCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_key = _normalize_chat_key(payload.chat_key)
    if not normalized_key:
        raise HTTPException(status_code=400, detail="Chat key is required")

    existing = (
        db.query(models.MonitoredContact)
        .filter(
            models.MonitoredContact.user_id == current_user.id,
            models.MonitoredContact.chat_key == normalized_key,
            models.MonitoredContact.chat_type == payload.chat_type,
        )
        .first()
    )
    if existing:
        existing.contact_name = payload.contact_name.strip()
        existing.phone_number = normalized_key
        existing.is_active = payload.is_active
        db.commit()
        db.refresh(existing)
        return _serialize_monitored_contact(existing)

    contact = models.MonitoredContact(
        user_id=current_user.id,
        contact_name=payload.contact_name.strip(),
        phone_number=normalized_key,
        chat_key=normalized_key,
        chat_type=payload.chat_type,
        is_active=payload.is_active,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return _serialize_monitored_contact(contact)


@router.patch("/monitored-contacts/{contact_id}", response_model=schemas.MonitoredContactResponse)
def update_monitored_contact(
    contact_id: int,
    payload: schemas.MonitoredContactUpdateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact = (
        db.query(models.MonitoredContact)
        .filter(models.MonitoredContact.id == contact_id, models.MonitoredContact.user_id == current_user.id)
        .first()
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Monitored contact not found")

    if payload.contact_name is not None:
        contact.contact_name = payload.contact_name.strip()
    if payload.chat_key is not None:
        normalized_key = _normalize_chat_key(payload.chat_key)
        if not normalized_key:
            raise HTTPException(status_code=400, detail="Chat key is required")
        duplicate = (
            db.query(models.MonitoredContact)
            .filter(
                models.MonitoredContact.id != contact.id,
                models.MonitoredContact.user_id == current_user.id,
                models.MonitoredContact.chat_key == normalized_key,
                models.MonitoredContact.chat_type == (payload.chat_type or contact.chat_type),
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="A monitor for this chat already exists")
        contact.chat_key = normalized_key
        contact.phone_number = normalized_key
    if payload.chat_type is not None:
        contact.chat_type = payload.chat_type
    if payload.is_active is not None:
        contact.is_active = payload.is_active

    db.commit()
    db.refresh(contact)
    return _serialize_monitored_contact(contact)


@router.delete("/monitored-contacts/{contact_id}")
def delete_monitored_contact(
    contact_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact = (
        db.query(models.MonitoredContact)
        .filter(models.MonitoredContact.id == contact_id, models.MonitoredContact.user_id == current_user.id)
        .first()
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Monitored contact not found")
    db.delete(contact)
    db.commit()
    return {"ok": True}


@router.post("/messages/incoming")
async def receive_incoming_message(payload: schemas.IncomingWhatsAppMessage, db: Session = Depends(get_db)):
    bridge_session_key = payload.bridge_session_key
    bridge_user_id = _bridge_user_id_from_session_key(bridge_session_key)
    if bridge_user_id is not None:
        bridge_user = (
            db.query(models.User)
            .filter(models.User.id == bridge_user_id, models.User.is_active.is_(True))
            .first()
        )
        if bridge_user is None:
            raise HTTPException(status_code=404, detail="Bridge owner not found")

        matched_contacts = [
            contact
            for contact in db.query(models.MonitoredContact).filter(models.MonitoredContact.user_id == bridge_user_id).all()
            if _contact_matches_payload(contact, payload)
        ]
        if not matched_contacts:
            if not (_single_account_mode_enabled() and _auto_forward_all_live_messages()):
                return {"ignored": True, "reason": "no_matching_user_scope"}
            matched_user_ids = [bridge_user_id]
        else:
            matched_user_ids = [bridge_user_id]

        chat = _get_or_create_live_chat(db, payload, owner_user_id=bridge_user_id)
        existing_participant_ids = {participant.id for participant in chat.participants}
        if bridge_user.id not in existing_participant_ids:
            chat.participants.append(bridge_user)
        if chat.user_id is None:
            chat.user_id = bridge_user.id
    else:
        matched_contacts = [contact for contact in db.query(models.MonitoredContact).all() if _contact_matches_payload(contact, payload)]
        matched_user_ids = sorted({contact.user_id for contact in matched_contacts if contact.user_id})
        if not matched_user_ids:
            if not (_single_account_mode_enabled() and _auto_forward_all_live_messages()):
                return {"ignored": True, "reason": "no_matching_user_scope"}
            owner = _resolve_demo_owner_user(db)
            if owner is None:
                raise HTTPException(status_code=503, detail="No active demo owner is available for live WhatsApp ingestion")
            matched_users = [owner]
            matched_user_ids = [owner.id]
            owner_user_id = owner.id
        else:
            matched_users = (
                db.query(models.User)
                .filter(models.User.id.in_(matched_user_ids), models.User.is_active.is_(True))
                .all()
            )
            owner_user_id = matched_user_ids[0] if len(matched_user_ids) == 1 else None

        chat = _get_or_create_live_chat(db, payload, owner_user_id=owner_user_id)
        existing_participant_ids = {participant.id for participant in chat.participants}
        for user in matched_users:
            if user.id not in existing_participant_ids:
                chat.participants.append(user)
        if chat.user_id is None and len(matched_users) == 1:
            chat.user_id = matched_users[0].id
    db.commit()
    db.refresh(chat)

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
            "live_message": _serialize_live_message(existing, chat).model_dump(mode="json"),
            "chat": _serialize_chat_summary(db, chat).model_dump(mode="json"),
        }

    analysis = ai_engine.analyze_message(payload.text)
    action = analysis.get("action") or ai_engine.action_for_score(analysis["risk_score"])
    severity = analysis.get("severity") or ai_engine.severity_for_score(analysis["risk_score"])
    message = models.Message(
        chat_id=chat.id,
        sender=payload.sender_name or payload.sender,
        sender_id=payload.sender,
        sender_name=payload.sender_name,
        message=payload.text,
        content=payload.text,
        external_message_id=payload.message_id,
        source="whatsapp_bridge",
        direction=payload.direction or ("outgoing" if payload.is_from_me else "incoming"),
        is_from_me=payload.is_from_me,
        raw_payload=json.dumps(payload.raw_payload) if payload.raw_payload else None,
        timestamp=_resolve_timestamp(payload.timestamp),
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
    db.commit()

    if action in {"flag", "block"}:
        db.add(
            models.Alert(
                message_id=message.id,
                alert_type=message.label or "Unsafe",
                severity=severity,
                status="open",
            )
        )
        db.commit()

    result = _recompute_chat_metrics(db, chat)
    live_message = _serialize_live_message(message, chat)
    chat_summary = _serialize_chat_summary(db, chat)

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
        },
        audience_user_ids=matched_user_ids,
    )
    await manager.broadcast({"type": "message", "payload": live_message.model_dump(mode="json")}, audience_user_ids=matched_user_ids)

    return {
        "chat_id": chat.id,
        "message_id": message.id,
        "label": analysis["label"],
        "risk_score": analysis["risk_score"],
        "duplicate": False,
        "live_message": live_message.model_dump(mode="json"),
        "chat": chat_summary.model_dump(mode="json"),
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
    current_user: models.User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.Message, models.Chat)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live")
    )
    access_filter = _get_live_chat_access_filter(current_user)
    if access_filter is not None:
        query = query.filter(access_filter)
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
    current_user: models.User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    access_filter = _get_live_chat_access_filter(current_user)
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
        if access_filter is not None:
            aggregate_query = aggregate_query.filter(access_filter)
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
    if access_filter is not None:
        query = query.filter(access_filter)
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
    current_user: models.User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    access_filter = _get_live_chat_access_filter(current_user)
    if date_from or date_to:
        aggregate_subquery = _build_live_chat_window_aggregate_query(
            db,
            search=search,
            date_from=date_from,
            date_to=date_to,
            current_user=current_user,
        ).subquery()
        aggregate_query = db.query(aggregate_subquery)
        if flagged_only:
            aggregate_query = aggregate_query.filter(aggregate_subquery.c.flagged_count > 0)

        summary_row = aggregate_query.with_entities(
            func.count(aggregate_subquery.c.chat_id),
            func.coalesce(func.sum(aggregate_subquery.c.message_count), 0),
            func.coalesce(
                func.sum(case((aggregate_subquery.c.flagged_count > 0, 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                aggregate_subquery.c.flagged_count > 0,
                                aggregate_subquery.c.flagged_count * 2 >= aggregate_subquery.c.message_count,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.max(aggregate_subquery.c.last_message_at),
        ).one()
        by_chat_type_rows = aggregate_query.with_entities(
            aggregate_subquery.c.chat_type,
            func.count(aggregate_subquery.c.chat_id),
        ).group_by(aggregate_subquery.c.chat_type).all()
        total_chats = int(summary_row[0] or 0)
        flagged_chats = int(summary_row[2] or 0)
        high_risk_chats = int(summary_row[3] or 0)
        by_chat_type = {
            (chat_type or "unknown"): int(count or 0)
            for chat_type, count in by_chat_type_rows
        }
        return schemas.WhatsAppChatSummaryAggregateResponse(
            total_chats=total_chats,
            total_messages=int(summary_row[1] or 0),
            flagged_chats=flagged_chats,
            by_chat_type=by_chat_type,
            by_risk_state={
                "safe": max(total_chats - flagged_chats, 0),
                "flagged": flagged_chats,
                "high_risk": high_risk_chats,
            },
            latest_message_at=summary_row[4],
        )

    query = db.query(models.Chat).filter(models.Chat.platform == "WhatsApp_Live")
    if access_filter is not None:
        query = query.filter(access_filter)
    if search:
        query = query.filter(models.Chat.chat_name.ilike(f"%{search}%"))
    if flagged_only:
        query = query.filter(models.Chat.flagged_message_count > 0)

    summary_row = query.with_entities(
        func.count(models.Chat.id),
        func.coalesce(func.sum(models.Chat.message_count), 0),
        func.coalesce(
            func.sum(case((models.Chat.flagged_message_count > 0, 1), else_=0)),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            models.Chat.flagged_message_count > 0,
                            models.Chat.flagged_message_count * 2 >= models.Chat.message_count,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
        func.max(models.Chat.last_message_at),
    ).one()
    by_chat_type_rows = query.with_entities(
        models.Chat.chat_type,
        func.count(models.Chat.id),
    ).group_by(models.Chat.chat_type).all()
    total_chats = int(summary_row[0] or 0)
    flagged_chats = int(summary_row[2] or 0)
    high_risk_chats = int(summary_row[3] or 0)
    by_chat_type = {
        (chat_type or "unknown"): int(count or 0)
        for chat_type, count in by_chat_type_rows
    }

    return schemas.WhatsAppChatSummaryAggregateResponse(
        total_chats=total_chats,
        total_messages=int(summary_row[1] or 0),
        flagged_chats=flagged_chats,
        by_chat_type=by_chat_type,
        by_risk_state={
            "safe": max(total_chats - flagged_chats, 0),
            "flagged": flagged_chats,
            "high_risk": high_risk_chats,
        },
        latest_message_at=summary_row[4],
    )


@router.get("/chats/{chat_id}", response_model=schemas.LiveChatDetailResponse)
def get_live_chat_detail(
    chat_id: int,
    flagged_only: bool = Query(default=False),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: models.User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    chat = (
        db.query(models.Chat)
        .options(joinedload(models.Chat.analysis_results))
        .filter(models.Chat.id == chat_id, models.Chat.platform == "WhatsApp_Live")
        .first()
    )
    access_filter = _get_live_chat_access_filter(current_user)
    if chat and access_filter is not None:
        allowed = (
            db.query(models.Chat.id)
            .filter(models.Chat.id == chat.id, access_filter)
            .first()
        )
        if not allowed:
            chat = None
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
    current_user: models.User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.Alert, models.Message, models.Chat)
        .join(models.Message, models.Message.id == models.Alert.message_id)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live")
    )
    access_filter = _get_live_chat_access_filter(current_user)
    if access_filter is not None:
        query = query.filter(access_filter)
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
    current_user: models.User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.Alert)
        .join(models.Message, models.Message.id == models.Alert.message_id)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live")
    )
    access_filter = _get_live_chat_access_filter(current_user)
    if access_filter is not None:
        query = query.filter(access_filter)
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
def update_live_alert(
    alert_id: int,
    payload: schemas.AlertUpdateRequest,
    current_user: models.User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException

    row = (
        db.query(models.Alert, models.Message, models.Chat)
        .join(models.Message, models.Message.id == models.Alert.message_id)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Alert.id == alert_id, models.Chat.platform == "WhatsApp_Live")
        .first()
    )
    access_filter = _get_live_chat_access_filter(current_user)
    if row and access_filter is not None:
        allowed = (
            db.query(models.Chat.id)
            .filter(models.Chat.id == row[2].id, access_filter)
            .first()
        )
        if not allowed:
            row = None
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
    current_user: models.User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    if current_user is not None and (current_user.role or "user") != "admin":
        state = _get_or_create_bridge_state(
            db,
            user_id=current_user.id,
            session_key=_bridge_session_key_for_user(current_user),
        )
    else:
        state = _get_or_create_bridge_state(db)
    message_query = (
        db.query(models.Message)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live")
    )
    access_filter = _get_live_chat_access_filter(current_user)
    if access_filter is not None:
        message_query = message_query.filter(access_filter)
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
    if access_filter is not None:
        alert_query = alert_query.filter(access_filter)
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
            .filter(access_filter if access_filter is not None else True)
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
    current_user: models.User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    window_start = datetime.now(timezone.utc) - timedelta(hours=recent_window_hours)
    live_summary = get_live_summary(date_from=window_start, date_to=None, current_user=current_user, db=db)
    access_filter = _get_live_chat_access_filter(current_user)

    recent_feed_count = (
        db.query(func.count(models.Message.id))
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live", models.Message.timestamp >= window_start)
        .filter(access_filter if access_filter is not None else True)
        .scalar()
        or 0
    )
    recent_alert_count = (
        db.query(func.count(models.Alert.id))
        .join(models.Message, models.Message.id == models.Alert.message_id)
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live", models.Alert.created_at >= window_start)
        .filter(access_filter if access_filter is not None else True)
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
        .filter(access_filter if access_filter is not None else True)
        .scalar()
        or 0
    )

    recent_chat_stats = (
        db.query(
            models.Message.chat_id.label("chat_id"),
            func.count(models.Message.id).label("message_count"),
            func.sum(case((models.Message.risk_score > 50, 1), else_=0)).label("flagged_count"),
        )
        .join(models.Chat, models.Chat.id == models.Message.chat_id)
        .filter(models.Chat.platform == "WhatsApp_Live", models.Message.timestamp >= window_start)
        .filter(access_filter if access_filter is not None else True)
        .group_by(models.Message.chat_id)
        .subquery()
    )
    chat_risk_summary = db.query(
        func.coalesce(
            func.sum(case((recent_chat_stats.c.flagged_count > 0, 1), else_=0)),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            recent_chat_stats.c.flagged_count > 0,
                            recent_chat_stats.c.flagged_count * 2 >= recent_chat_stats.c.message_count,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
    ).one()
    flagged_chat_count = int(chat_risk_summary[0] or 0)
    high_risk_chat_count = int(chat_risk_summary[1] or 0)

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
    current_user: models.User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    bridge_ops = get_bridge_ops_summary(
        recent_window_hours=recent_window_hours,
        current_user=current_user,
        db=db,
    )
    live_ops = get_live_ops_summary(recent_window_hours=recent_window_hours, current_user=current_user, db=db)
    attention_required = bridge_ops.attention_required or live_ops.attention_required
    status = "attention" if attention_required else "healthy"
    return schemas.WhatsAppBackendHealthResponse(
        bridge_ops=bridge_ops,
        live_ops=live_ops,
        recent_window_hours=recent_window_hours,
        attention_required=attention_required,
        status=status,
    )
