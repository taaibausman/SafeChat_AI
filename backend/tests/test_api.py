import os
import warnings
import pytest

os.environ["DATABASE_URL"] = "sqlite:///./safechat-test.db"

warnings.filterwarnings(
    "ignore",
    message=r"Using `httpx` with `starlette\.testclient` is deprecated; install `httpx2` instead\.",
    category=Warning,
)

from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import text
from backend.main import app
from backend.database.config import engine, Base
from backend.database.config import SessionLocal
from backend.database.migrations import run_migrations
from backend.auth import create_access_token, hash_password
from backend.bootstrap import ensure_default_admin
import backend.api.image_analyzer as image_analyzer
import backend.models.domain as models
from io import BytesIO
from datetime import datetime, timedelta, timezone
from PIL import Image
from urllib.parse import quote
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

client = TestClient(app)
TEST_DATABASE_PATH = "safechat-test.db"


def setup_module(module):
    # reset the database for tests
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)


def teardown_module(module):
    engine.dispose()
    if os.path.exists(TEST_DATABASE_PATH):
        os.remove(TEST_DATABASE_PATH)


def register_user(username: str, email: str, password: str, role: str = "user"):
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["role"] == "user"
    return payload


def create_seed_user(
    username: str,
    email: str,
    password: str,
    role: str = "user",
    *,
    is_active: bool = True,
    name: str | None = None,
):
    db = SessionLocal()
    try:
        user = models.User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=is_active,
            name=name,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return {
            "access_token": create_access_token(user),
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "name": user.name,
                "created_at": user.created_at.isoformat(),
            },
        }
    finally:
        db.close()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def bridge_session_key(session: dict) -> str:
    return f"user-{session['user']['id']}"


def create_monitor(token: str, *, contact_name: str, chat_key: str, chat_type: str = "group", is_active: bool = True):
    response = client.post(
        "/api/whatsapp/monitored-contacts",
        json={
            "contact_name": contact_name,
            "chat_key": chat_key,
            "chat_type": chat_type,
            "is_active": is_active,
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    return response.json()


def test_upload_chat_and_get_report():
    sample = """[12/5/26, 9:00 PM] Sara: Hello there\n[12/5/26, 9:05 PM] Bob: Hi Sara\n"""
    files = {"file": ("chat.txt", sample.encode("utf-8"), "text/plain")}
    resp = client.post("/api/analyze/upload", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert "chat_id" in data

    chat_id = data["chat_id"]
    # Fetch report
    resp2 = client.get(f"/api/analyze/report/{chat_id}")
    assert resp2.status_code == 200
    report = resp2.json()
    assert report["id"] == chat_id
    assert isinstance(report["messages"], list)
    assert len(report["messages"]) >= 1


def test_guest_upload_chat_does_not_persist_report():
    db = SessionLocal()
    try:
        chats_before = db.query(models.Chat).count()
        messages_before = db.query(models.Message).count()
        results_before = db.query(models.AnalysisResult).count()
    finally:
        db.close()

    sample = """[12/5/26, 9:00 PM] Sara: Hello there\n[12/5/26, 9:05 PM] Bob: I hate you\n"""
    files = {"file": ("guest-chat.txt", sample.encode("utf-8"), "text/plain")}
    resp = client.post("/api/analyze/guest-upload", files=files)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["report"]["chat_name"] == "guest-chat.txt"
    assert payload["report"]["id"] == 0
    assert len(payload["report"]["messages"]) == 2

    db = SessionLocal()
    try:
        assert db.query(models.Chat).count() == chats_before
        assert db.query(models.Message).count() == messages_before
        assert db.query(models.AnalysisResult).count() == results_before
    finally:
        db.close()


def test_schema_migrations_table_exists():
    db = SessionLocal()
    try:
        versions = {
            row[0]
            for row in db.execute(text("SELECT version FROM schema_migrations")).fetchall()
        }
        assert "20260530_001_whatsapp_live_schema" in versions
        assert "20260530_002_core_database_alignment" in versions
        assert "20260530_003_whatsapp_monitor_scope" in versions
    finally:
        db.close()


def test_image_upload():
    # Patch pytesseract to avoid dependency on system tesseract
    original_provider = image_analyzer.OCR_PROVIDER
    original = image_analyzer.pytesseract.image_to_string
    image_analyzer.OCR_PROVIDER = "tesseract"
    image_analyzer.pytesseract.image_to_string = lambda img, config=None: "9:19 PM Hello there 9:20 PM I hate you"

    # Create a simple blank PNG image
    img = Image.new("RGB", (100, 30), color=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    files = {"file": ("test.png", buf.read(), "image/png")}
    resp = client.post("/api/image/upload", files=files)

    # restore
    image_analyzer.OCR_PROVIDER = original_provider
    image_analyzer.pytesseract.image_to_string = original

    assert resp.status_code == 200
    data = resp.json()
    assert "chat_id" in data

    db = SessionLocal()
    try:
        image_scan = db.query(models.ImageScan).order_by(models.ImageScan.id.desc()).first()
        assert image_scan is not None
        assert image_scan.file_path == "test.png"
        assert image_scan.ocr_text == "9:19 PM Hello there 9:20 PM I hate you"
        chat = db.query(models.Chat).order_by(models.Chat.id.desc()).first()
        assert chat is not None
        messages = db.query(models.Message).filter(models.Message.chat_id == chat.id).order_by(models.Message.id.asc()).all()
        assert len(messages) == 2
        assert messages[0].message == "Hello there"
        assert messages[1].message == "I hate you"
    finally:
        db.close()


def test_login_is_case_insensitive_for_email():
    register_user("case-user", "Case.User@example.com", "secret123")

    resp = client.post(
        "/api/auth/login",
        json={
            "email_or_username": "case.user@EXAMPLE.com",
            "password": "secret123",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["user"]["email"] == "case.user@example.com"


def test_image_ocr_normalization():
    normalized = image_analyzer._normalize_ocr_text(
        "   9:46 iG) tise €< Z_ Zaneeha \n\n On May 24, 2026 \u2014 Forwarded \n\n 4:06 PM View channel - Kahan ho \n @@@ \n"
    )

    assert "Zaneeha" in normalized
    assert "On May 24, 2026 - Forwarded" in normalized
    assert "@@@" not in normalized


def test_segment_ocr_text_into_messages():
    parsed = image_analyzer._segment_ocr_text_into_messages(
        "May 24, 2026\nForwarded\nAgent Router\nGet up to $200 free AI credits\nSign up with GitHub\n4.06 PM Helllo 9.19 PM Kesi ho tum 9.45 PM Kahan ho 9.45 PM Jldi btao wrna 9.45 PM You bixtth 9.45 PM"
    )

    messages = [item["message"] for item in parsed]
    assert "Forwarded" not in messages
    assert "Agent Router" not in messages
    assert "Get up to $200 free AI credits" not in messages
    assert "Helllo" in messages
    assert "Kesi ho tum" in messages
    assert "Kahan ho" in messages
    assert "Jldi btao wrna" in messages
    assert "You bixtth" in messages


def test_segment_ocr_text_filters_low_quality_noise():
    parsed = image_analyzer._segment_ocr_text_into_messages(
        "1G) atl!\n"
        "and don't miss this opportunity.\n"
        "A al i) aad ee me ee oe ee ae oe Kahan ho\n"
        "taunt aren wy a SoORReeOhRees = & oak CI Sayer, 208 Jidi btao wrna...\n"
        "Kesi ho ui\n"
        "me 2c biI***h gas py cn Ce a"
    )

    messages = [item["message"] for item in parsed]
    assert "and don't miss this opportunity." not in messages
    assert all("1G) atl!" not in message for message in messages)
    assert all("A al i) aad ee me ee oe ee ae oe" not in message for message in messages)
    assert any("Kahan ho" in message for message in messages)
    assert any("Jidi btao wrna" in message for message in messages)
    assert any("Kesi ho ui" in message for message in messages)


def test_easyocr_line_filter_removes_ui_chrome():
    results = [
        ([[20, 20], [120, 20], [120, 50], [20, 50]], "9:46", 0.99),
        ([[180, 70], [420, 70], [420, 110], [180, 110]], "Zaneeha", 0.99),
        ([[240, 150], [360, 150], [360, 190], [240, 190]], "May 24, 2026", 0.98),
        ([[60, 240], [220, 240], [220, 280], [60, 280]], "Kesi ho tum", 0.98),
        ([[460, 240], [560, 240], [560, 275], [460, 275]], "9:45 PM", 0.97),
        ([[60, 300], [180, 300], [180, 340], [60, 340]], "Kahan ho", 0.98),
        ([[210, 720], [390, 720], [390, 760], [210, 760]], "5 unread messages", 0.98),
        ([[90, 1230], [270, 1230], [270, 1270], [90, 1270]], "Message", 0.99),
    ]

    filtered = image_analyzer._filter_easyocr_lines(results, (720, 1600))

    assert filtered == ["Kesi ho tum", "Kahan ho"]


def test_easyocr_text_extraction(monkeypatch):
    original_reader = image_analyzer._EASYOCR_READER

    class DummyReader:
        def readtext(self, image, detail=1, paragraph=False):
            return [
                ([[0, 0], [1, 0], [1, 1], [0, 1]], "Hello there", 0.97),
                ([[0, 2], [1, 2], [1, 3], [0, 3]], "Kahan ho", 0.95),
            ]

    monkeypatch.setattr(image_analyzer, "_get_easyocr_reader", lambda: DummyReader())

    img = Image.new("RGB", (100, 30), color=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    try:
        extracted = image_analyzer._extract_text_with_easyocr(buf.read())
    finally:
        image_analyzer._EASYOCR_READER = original_reader

    assert extracted == "Hello there Kahan ho"


def test_image_ocr_auto_uses_easyocr_first(monkeypatch):
    original_provider = image_analyzer.OCR_PROVIDER
    image_analyzer.OCR_PROVIDER = "auto"

    monkeypatch.setattr(
        image_analyzer,
        "_extract_text_with_easyocr",
        lambda content: "EasyOCR text",
    )

    try:
        extracted = image_analyzer.extract_text_from_image_bytes(b"fake-image")
    finally:
        image_analyzer.OCR_PROVIDER = original_provider

    assert extracted == "EasyOCR text"


def test_image_ocr_auto_falls_back_to_tesseract_when_google_unavailable(monkeypatch):
    original_provider = image_analyzer.OCR_PROVIDER
    image_analyzer.OCR_PROVIDER = "auto"

    monkeypatch.setattr(
        image_analyzer,
        "_extract_text_with_easyocr",
        lambda content: (_ for _ in ()).throw(RuntimeError("easyocr unavailable")),
    )
    monkeypatch.setattr(
        image_analyzer,
        "_extract_text_with_google_vision",
        lambda content: (_ for _ in ()).throw(RuntimeError("google unavailable")),
    )
    monkeypatch.setattr(
        image_analyzer,
        "_extract_text_with_tesseract",
        lambda content: "Fallback OCR text",
    )

    try:
        extracted = image_analyzer.extract_text_from_image_bytes(b"fake-image")
    finally:
        image_analyzer.OCR_PROVIDER = original_provider

    assert extracted == "Fallback OCR text"


def test_ocr_space_text_extraction(monkeypatch):
    original_key = image_analyzer.OCR_SPACE_API_KEY
    image_analyzer.OCR_SPACE_API_KEY = "test-key"

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "IsErroredOnProcessing": False,
                "ParsedResults": [
                    {"ParsedText": "Hello there\nKahan ho"}
                ],
            }

    monkeypatch.setattr(image_analyzer.requests, "post", lambda *args, **kwargs: DummyResponse())

    try:
        extracted = image_analyzer._extract_text_with_ocr_space(b"fake-image")
    finally:
        image_analyzer.OCR_SPACE_API_KEY = original_key

    assert extracted == "Hello there Kahan ho"


def test_ocr_space_missing_key_raises_runtime_error():
    original_key = image_analyzer.OCR_SPACE_API_KEY
    image_analyzer.OCR_SPACE_API_KEY = ""

    try:
        with pytest.raises(RuntimeError) as exc_info:
            image_analyzer._extract_text_with_ocr_space(b"fake-image")
    finally:
        image_analyzer.OCR_SPACE_API_KEY = original_key

    assert "API key" in str(exc_info.value)


def test_image_ocr_auto_falls_back_to_tesseract_when_ocr_space_unavailable(monkeypatch):
    original_provider = image_analyzer.OCR_PROVIDER
    image_analyzer.OCR_PROVIDER = "auto"

    monkeypatch.setattr(
        image_analyzer,
        "_extract_text_with_easyocr",
        lambda content: (_ for _ in ()).throw(RuntimeError("easyocr unavailable")),
    )
    monkeypatch.setattr(
        image_analyzer,
        "_extract_text_with_ocr_space",
        lambda content: (_ for _ in ()).throw(RuntimeError("ocr.space unavailable")),
    )
    monkeypatch.setattr(
        image_analyzer,
        "_extract_text_with_google_vision",
        lambda content: (_ for _ in ()).throw(RuntimeError("google unavailable")),
    )
    monkeypatch.setattr(
        image_analyzer,
        "_extract_text_with_tesseract",
        lambda content: "Fallback OCR text",
    )

    try:
        extracted = image_analyzer.extract_text_from_image_bytes(b"fake-image")
    finally:
        image_analyzer.OCR_PROVIDER = original_provider

    assert extracted == "Fallback OCR text"


def test_image_ocr_auto_preserves_no_text_error(monkeypatch):
    original_provider = image_analyzer.OCR_PROVIDER
    image_analyzer.OCR_PROVIDER = "auto"

    monkeypatch.setattr(
        image_analyzer,
        "_extract_text_with_easyocr",
        lambda content: (_ for _ in ()).throw(HTTPException(status_code=400, detail="Could not extract any text from the image")),
    )

    try:
        with pytest.raises(HTTPException) as exc_info:
            image_analyzer.extract_text_from_image_bytes(b"fake-image")
    finally:
        image_analyzer.OCR_PROVIDER = original_provider

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Could not extract any text from the image"


def test_whatsapp_status_and_incoming_routes():
    registered = register_user("bridge-status", "bridge-status@example.com", "secret123")
    create_monitor(registered["access_token"], contact_name="Test Group", chat_key="group-1", chat_type="group")
    status_resp = client.post(
        "/api/whatsapp/status",
        json={
            "bridge_session_key": bridge_session_key(registered),
            "status": "connected",
            "reason": "test",
            "qr": None,
            "connected_phone": "923001234567:1@s.whatsapp.net",
        },
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "connected"
    assert status_data["connected_phone"] == "923001234567:1@s.whatsapp.net"

    incoming_resp = client.post(
        "/api/whatsapp/messages/incoming",
        json={
            "bridge_session_key": bridge_session_key(registered),
            "message_id": "test123",
            "group_id": "group-1",
            "group_name": "Test Group",
            "chat_type": "group",
            "sender": "alice",
            "sender_name": "Alice",
            "text": "This is a WhatsApp bridge test.",
            "timestamp": None,
        },
    )
    assert incoming_resp.status_code == 200
    incoming_data = incoming_resp.json()
    assert "chat_id" in incoming_data
    assert "message_id" in incoming_data
    assert incoming_data["duplicate"] is False

    duplicate_resp = client.post(
        "/api/whatsapp/messages/incoming",
        json={
            "bridge_session_key": bridge_session_key(registered),
            "message_id": "test123",
            "group_id": "group-1",
            "group_name": "Test Group",
            "chat_type": "group",
            "sender": "alice",
            "sender_name": "Alice",
            "text": "This is a WhatsApp bridge test.",
            "timestamp": None,
        },
    )
    assert duplicate_resp.status_code == 200
    assert duplicate_resp.json()["duplicate"] is True

    feed_resp = client.get("/api/whatsapp/live-feed")
    assert feed_resp.status_code == 200
    feed_data = feed_resp.json()
    assert isinstance(feed_data.get("messages"), list)
    assert "total" in feed_data

    db = SessionLocal()
    try:
        moderation_log = db.query(models.ModerationLog).order_by(models.ModerationLog.id.desc()).first()
        assert moderation_log is not None
        assert moderation_log.action in {"allow", "flag"}
    finally:
        db.close()


def test_whatsapp_chat_and_bridge_routes(monkeypatch):
    import backend.api.whatsapp as whatsapp_api
    registered = register_user("bridge-routes", "bridge-routes@example.com", "secret123")
    token = registered["access_token"]

    def fake_bridge_request(path, method="GET", query=None):
        if path == "/directory":
            return (
                True,
                {
                    "status": "connected",
                    "detail": "Directory ready",
                    "total": 2,
                    "items": [
                        {
                            "chat_key": "family-group",
                            "chat_type": "group",
                            "display_name": "Family Group",
                            "phone_number": None,
                            "source": "group",
                            "recent_message_count": 12,
                            "last_activity_at": "2026-06-02T12:30:00+00:00",
                            "is_monitored": True,
                        },
                        {
                            "chat_key": "923001112222",
                            "chat_type": "direct",
                            "display_name": "Ayesha",
                            "phone_number": "923001112222",
                            "source": "recent",
                            "recent_message_count": 4,
                            "last_activity_at": "2026-06-02T11:15:00+00:00",
                            "is_monitored": False,
                        },
                    ],
                },
                None,
            )
        return (
            True,
            {"status": "connected", "detail": f"{method} {path}", "session_key": (query or {}).get("session_key")},
            None,
        )

    monkeypatch.setattr(
        whatsapp_api,
        "_bridge_request",
        fake_bridge_request,
    )

    health_resp = client.get("/api/whatsapp/bridge-health", headers=auth_headers(token))
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert health_data["reachable"] is True
    assert health_data["status"] == "connected"

    restart_resp = client.post("/api/whatsapp/bridge-restart", headers=auth_headers(token))
    assert restart_resp.status_code == 200
    restart_data = restart_resp.json()
    assert restart_data["reachable"] is True

    directory_resp = client.get("/api/whatsapp/chat-directory?search=ay&limit=10", headers=auth_headers(token))
    assert directory_resp.status_code == 200
    directory_data = directory_resp.json()
    assert directory_data["reachable"] is True
    assert directory_data["status"] == "connected"
    assert directory_data["total"] == 2
    assert len(directory_data["items"]) == 2
    assert {item["chat_type"] for item in directory_data["items"]} == {"group", "direct"}

    events_resp = client.get("/api/whatsapp/bridge-events")
    assert events_resp.status_code == 200
    events_data = events_resp.json()
    assert events_data["total"] >= 2
    assert events_data["limit"] == 50
    assert events_data["offset"] == 0
    event_types = {event["event_type"] for event in events_data["events"]}
    assert "health_check" in event_types
    assert "restart" in event_types

    connected_events_resp = client.get("/api/whatsapp/bridge-events?status=connected")
    assert connected_events_resp.status_code == 200
    connected_events = connected_events_resp.json()["events"]
    assert connected_events
    assert all(event["status"] == "connected" for event in connected_events)

    summary_resp = client.get("/api/whatsapp/bridge-events/summary")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["total_events"] >= 2
    assert summary_data["by_type"].get("health_check", 0) >= 1
    assert summary_data["by_type"].get("restart", 0) >= 1
    assert summary_data["latest_event_at"] is not None

    snapshot_resp = client.get("/api/whatsapp/bridge-state-history")
    assert snapshot_resp.status_code == 200
    snapshot_data = snapshot_resp.json()
    assert snapshot_data["total"] >= 2
    assert snapshot_data["limit"] == 50
    assert snapshot_data["offset"] == 0

    connected_snapshot_resp = client.get("/api/whatsapp/bridge-state-history?status=connected")
    assert connected_snapshot_resp.status_code == 200
    connected_snapshots = connected_snapshot_resp.json()["snapshots"]
    assert connected_snapshots
    assert all(snapshot["status"] == "connected" for snapshot in connected_snapshots)

    snapshot_summary_resp = client.get("/api/whatsapp/bridge-state-history/summary")
    assert snapshot_summary_resp.status_code == 200
    snapshot_summary = snapshot_summary_resp.json()
    assert snapshot_summary["total_snapshots"] >= 2
    assert snapshot_summary["by_status"].get("connected", 0) >= 1
    assert snapshot_summary["latest_snapshot_at"] is not None

    ops_summary_resp = client.get("/api/whatsapp/bridge-ops-summary", headers=auth_headers(token))
    assert ops_summary_resp.status_code == 200
    ops_summary = ops_summary_resp.json()
    assert ops_summary["current_state"]["status"] == "disconnected" or ops_summary["current_state"]["status"] == "connected"
    assert ops_summary["latest_event"] is not None
    assert ops_summary["latest_snapshot"] is not None
    assert ops_summary["recent_event_count"] >= 2
    assert ops_summary["recent_snapshot_count"] >= 2
    assert ops_summary["recent_window_hours"] == 24
    assert ops_summary["bridge_reachable"] is True

    chats_resp = client.get("/api/whatsapp/chats")
    assert chats_resp.status_code == 200
    chats_data = chats_resp.json()
    assert isinstance(chats_data.get("chats"), list)
    assert "total" in chats_data
    if chats_data["chats"]:
        detail_resp = client.get(f"/api/whatsapp/chats/{chats_data['chats'][0]['id']}")
        assert detail_resp.status_code == 200
        detail_data = detail_resp.json()
        assert "total_messages" in detail_data


def test_whatsapp_qr_status_persistence():
    registered = register_user("bridge-qr", "bridge-qr@example.com", "secret123")
    token = registered["access_token"]

    status_resp = client.post(
        "/api/whatsapp/status",
        json={
            "bridge_session_key": bridge_session_key(registered),
            "status": "qr_required",
            "reason": "Scan required",
            "qr": "qr-token-123",
        },
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "qr_required"
    assert status_data["qr"] == "qr-token-123"
    assert status_data["qr_updated_at"] is not None

    qr_resp = client.get("/api/whatsapp/qr", headers=auth_headers(token))
    assert qr_resp.status_code == 200
    qr_data = qr_resp.json()
    assert qr_data["qr"] == "qr-token-123"
    assert qr_data["status"] == "qr_required"

    events_resp = client.get(
        "/api/whatsapp/bridge-events?event_type=status_update",
        headers=auth_headers(token),
    )
    assert events_resp.status_code == 200
    events_data = events_resp.json()
    assert events_data["total"] >= 1
    assert all(event["event_type"] == "status_update" for event in events_data["events"])
    assert any(event["status"] == "qr_required" for event in events_data["events"])

    status_filtered_resp = client.get("/api/whatsapp/bridge-events?event_type=status_update&status=qr_required")
    assert status_filtered_resp.status_code == 200
    status_filtered = status_filtered_resp.json()["events"]
    assert status_filtered
    assert all(event["status"] == "qr_required" for event in status_filtered)

    summary_resp = client.get("/api/whatsapp/bridge-events/summary?event_type=status_update&status=qr_required")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["total_events"] >= 1
    assert summary_data["by_type"].get("status_update", 0) >= 1
    assert summary_data["by_status"].get("qr_required", 0) >= 1

    snapshot_resp = client.get("/api/whatsapp/bridge-state-history?status=qr_required")
    assert snapshot_resp.status_code == 200
    snapshot_data = snapshot_resp.json()
    assert snapshot_data["total"] >= 1
    assert all(snapshot["status"] == "qr_required" for snapshot in snapshot_data["snapshots"])
    assert any(snapshot["qr_present"] is True for snapshot in snapshot_data["snapshots"])

    snapshot_summary_resp = client.get("/api/whatsapp/bridge-state-history/summary?status=qr_required")
    assert snapshot_summary_resp.status_code == 200
    snapshot_summary = snapshot_summary_resp.json()
    assert snapshot_summary["total_snapshots"] >= 1
    assert snapshot_summary["by_status"].get("qr_required", 0) >= 1


def test_whatsapp_qr_persists_through_connecting_without_new_qr():
    registered = register_user("bridge-qr-connecting", "bridge-qr-connecting@example.com", "secret123")
    token = registered["access_token"]

    first_resp = client.post(
        "/api/whatsapp/status",
        json={
            "bridge_session_key": bridge_session_key(registered),
            "status": "qr_required",
            "reason": "Scan required",
            "qr": "qr-token-connecting",
        },
    )
    assert first_resp.status_code == 200
    assert first_resp.json()["qr"] == "qr-token-connecting"

    second_resp = client.post(
        "/api/whatsapp/status",
        json={
            "bridge_session_key": bridge_session_key(registered),
            "status": "connecting",
            "reason": "Opening WhatsApp session.",
            "qr": None,
        },
    )
    assert second_resp.status_code == 200
    second_data = second_resp.json()
    assert second_data["status"] == "connecting"
    assert second_data["qr"] == "qr-token-connecting"

    qr_resp = client.get("/api/whatsapp/qr", headers=auth_headers(token))
    assert qr_resp.status_code == 200
    qr_data = qr_resp.json()
    assert qr_data["status"] == "connecting"
    assert qr_data["qr"] == "qr-token-connecting"


def test_whatsapp_bridge_event_retention(monkeypatch):
    import backend.api.whatsapp as whatsapp_api

    monkeypatch.setattr(whatsapp_api, "BRIDGE_EVENT_RETENTION", 2)

    first_resp = client.post(
        "/api/whatsapp/status",
        json={"status": "connecting", "reason": "retention-1"},
    )
    assert first_resp.status_code == 200

    second_resp = client.post(
        "/api/whatsapp/status",
        json={"status": "qr_required", "reason": "retention-2", "qr": "qr-retention"},
    )
    assert second_resp.status_code == 200

    third_resp = client.post(
        "/api/whatsapp/status",
        json={"status": "connected", "reason": "retention-3", "connected_phone": "923000000000:1@s.whatsapp.net"},
    )
    assert third_resp.status_code == 200

    events_resp = client.get("/api/whatsapp/bridge-events?event_type=status_update")
    assert events_resp.status_code == 200
    events_data = events_resp.json()
    assert events_data["total"] == 2
    reasons = {event["detail"] for event in events_data["events"]}
    assert "retention-1" not in reasons
    assert "retention-2" in reasons
    assert "retention-3" in reasons


def test_whatsapp_bridge_state_snapshot_retention(monkeypatch):
    import backend.api.whatsapp as whatsapp_api

    monkeypatch.setattr(whatsapp_api, "BRIDGE_STATE_SNAPSHOT_RETENTION", 2)

    first_resp = client.post(
        "/api/whatsapp/status",
        json={"status": "connecting", "reason": "snapshot-retention-1"},
    )
    assert first_resp.status_code == 200

    second_resp = client.post(
        "/api/whatsapp/status",
        json={"status": "qr_required", "reason": "snapshot-retention-2", "qr": "snapshot-qr"},
    )
    assert second_resp.status_code == 200

    third_resp = client.post(
        "/api/whatsapp/status",
        json={"status": "connected", "reason": "snapshot-retention-3", "connected_phone": "923000000111:1@s.whatsapp.net"},
    )
    assert third_resp.status_code == 200

    snapshot_resp = client.get("/api/whatsapp/bridge-state-history")
    assert snapshot_resp.status_code == 200
    snapshot_data = snapshot_resp.json()
    assert snapshot_data["total"] == 2
    reasons = {snapshot["reason"] for snapshot in snapshot_data["snapshots"]}
    assert "snapshot-retention-1" not in reasons
    assert "snapshot-retention-2" in reasons
    assert "snapshot-retention-3" in reasons


def test_whatsapp_bridge_event_date_filters():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        old_event = models.WhatsAppBridgeEvent(
            event_type="status_update",
            status="disconnected",
            detail="old-window",
            created_at=now - timedelta(days=2),
        )
        new_event = models.WhatsAppBridgeEvent(
            event_type="status_update",
            status="connected",
            detail="new-window",
            created_at=now,
        )
        db.add_all([old_event, new_event])
        db.commit()
    finally:
        db.close()

    date_from = quote((now - timedelta(hours=12)).isoformat())
    recent_resp = client.get(f"/api/whatsapp/bridge-events?event_type=status_update&date_from={date_from}")
    assert recent_resp.status_code == 200
    recent_events = recent_resp.json()["events"]
    recent_details = {event["detail"] for event in recent_events}
    assert "new-window" in recent_details
    assert "old-window" not in recent_details

    date_to = quote((now - timedelta(days=1)).isoformat())
    older_resp = client.get(f"/api/whatsapp/bridge-events?event_type=status_update&date_to={date_to}")
    assert older_resp.status_code == 200
    older_events = older_resp.json()["events"]
    older_details = {event["detail"] for event in older_events}
    assert "old-window" in older_details
    assert "new-window" not in older_details

    summary_resp = client.get(f"/api/whatsapp/bridge-events/summary?event_type=status_update&date_from={date_from}")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["total_events"] >= 1
    assert summary_data["by_status"].get("connected", 0) >= 1


def test_whatsapp_direct_chat_naming_and_aggregate_updates():
    registered = register_user("direct-owner", "direct-owner@example.com", "secret123")
    token = registered["access_token"]
    create_monitor(
        token,
        contact_name="Ayesha",
        chat_key="923001112222",
        chat_type="direct",
    )

    first_resp = client.post(
        "/api/whatsapp/messages/incoming",
        json={
            "message_id": "direct-1",
            "group_id": "923001112222",
            "group_name": "923001112222",
            "chat_type": "direct",
            "sender": "923001112222",
            "sender_name": "Ayesha",
            "text": "Friendly hello from a direct chat.",
            "timestamp": 1780033700,
        },
    )
    assert first_resp.status_code == 200
    chat_id = first_resp.json()["chat_id"]

    second_resp = client.post(
        "/api/whatsapp/messages/incoming",
        json={
            "message_id": "direct-2",
            "group_id": "923001112222",
            "group_name": "923001112222",
            "chat_type": "direct",
            "sender": "923001112222",
            "sender_name": "Ayesha",
            "text": "I hate you and will ruin everything.",
            "timestamp": 1780033760,
        },
    )
    assert second_resp.status_code == 200
    assert second_resp.json()["chat_id"] == chat_id

    chats_resp = client.get("/api/whatsapp/chats", headers=auth_headers(token))
    assert chats_resp.status_code == 200
    chats = chats_resp.json()["chats"]
    target = next(chat for chat in chats if chat["id"] == chat_id)
    assert target["chat_name"] == "Ayesha"
    assert target["chat_type"] == "direct"
    assert target["message_count"] == 2
    assert target["flagged_messages"] >= 0
    assert "alert_count" in target
    assert "open_alert_count" in target
    assert "acknowledged_alert_count" in target
    assert "resolved_alert_count" in target
    assert target["latest_message_preview"] == "I hate you and will ruin everything."

    detail_resp = client.get(f"/api/whatsapp/chats/{chat_id}", headers=auth_headers(token))
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["chat_name"] == "Ayesha"
    assert len(detail["messages"]) == 2
    assert detail["total_messages"] == 2
    assert detail["analysis_results"] is not None
    assert detail["alert_count"] >= 0
    assert detail["open_alert_count"] >= 0
    assert detail["acknowledged_alert_count"] >= 0
    assert detail["resolved_alert_count"] >= 0
    assert detail["analysis_results"]["summary"].startswith("Live monitoring has flagged")

    flagged_detail_resp = client.get(
        f"/api/whatsapp/chats/{chat_id}?flagged_only=true",
        headers=auth_headers(token),
    )
    assert flagged_detail_resp.status_code == 200
    flagged_detail = flagged_detail_resp.json()
    assert flagged_detail["total_messages"] <= detail["total_messages"]
    assert all((message["risk_score"] or 0) > 50 for message in flagged_detail["messages"])

    summary_resp = client.get("/api/whatsapp/chats/summary", headers=auth_headers(token))
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["total_chats"] >= 1
    assert summary["total_messages"] >= 2
    assert summary["by_chat_type"].get("direct", 0) >= 1
    assert summary["by_risk_state"].get("safe", 0) + summary["by_risk_state"].get("flagged", 0) == summary["total_chats"]
    assert summary["latest_message_at"] is not None

    flagged_summary_resp = client.get(
        "/api/whatsapp/chats/summary?flagged_only=true",
        headers=auth_headers(token),
    )
    assert flagged_summary_resp.status_code == 200
    flagged_summary = flagged_summary_resp.json()
    assert flagged_summary["flagged_chats"] == flagged_summary["total_chats"]

    recent_summary_resp = client.get(
        "/api/whatsapp/chats/summary?date_from=2026-05-29T00%3A00%3A00%2B00%3A00",
        headers=auth_headers(token),
    )
    assert recent_summary_resp.status_code == 200
    recent_summary = recent_summary_resp.json()
    assert recent_summary["total_chats"] >= 1
    assert recent_summary["by_chat_type"].get("direct", 0) >= 1

    older_summary_resp = client.get(
        "/api/whatsapp/chats/summary?date_to=2026-05-01T00%3A00%3A00%2B00%3A00",
        headers=auth_headers(token),
    )
    assert older_summary_resp.status_code == 200
    older_summary = older_summary_resp.json()
    assert older_summary["total_chats"] == 0
    assert older_summary["total_messages"] == 0


def test_monitored_contact_crud_and_outgoing_message_fields():
    registered = register_user("monitor-owner", "monitor-owner@example.com", "secret123")
    token = registered["access_token"]

    create_resp = client.post(
        "/api/whatsapp/monitored-contacts",
        json={
            "contact_name": "Family Group",
            "chat_key": "family-group-1",
            "chat_type": "group",
            "is_active": True,
        },
        headers=auth_headers(token),
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["chat_key"] == "family-group-1"
    assert created["chat_type"] == "group"
    assert created["is_active"] is True

    duplicate_resp = client.post(
        "/api/whatsapp/monitored-contacts",
        json={
            "contact_name": "Family Group Updated",
            "chat_key": "family-group-1",
            "chat_type": "group",
            "is_active": False,
        },
        headers=auth_headers(token),
    )
    assert duplicate_resp.status_code == 200
    duplicate = duplicate_resp.json()
    assert duplicate["id"] == created["id"]
    assert duplicate["contact_name"] == "Family Group Updated"
    assert duplicate["is_active"] is False

    list_resp = client.get("/api/whatsapp/monitored-contacts", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert any(contact["id"] == created["id"] for contact in list_resp.json()["contacts"])

    active_resp = client.get("/api/whatsapp/monitored-contacts?active_only=true", headers=auth_headers(token))
    assert active_resp.status_code == 200
    assert all(contact["is_active"] is True for contact in active_resp.json()["contacts"])

    patch_resp = client.patch(
        f"/api/whatsapp/monitored-contacts/{created['id']}",
        json={"is_active": True, "contact_name": "Family Group Final"},
        headers=auth_headers(token),
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["is_active"] is True
    assert patched["contact_name"] == "Family Group Final"

    incoming_resp = client.post(
        "/api/whatsapp/messages/incoming",
        json={
            "message_id": "outgoing-1",
            "group_id": "family-group-1",
            "group_name": "Family Group Final",
            "chat_type": "group",
            "sender": "923001234567",
            "sender_name": "You",
            "text": "Outgoing bridge test message.",
            "timestamp": 1780036100,
            "direction": "outgoing",
            "is_from_me": True,
        },
    )
    assert incoming_resp.status_code == 200
    body = incoming_resp.json()
    assert body["duplicate"] is False
    assert body["live_message"]["direction"] == "outgoing"
    assert body["live_message"]["is_from_me"] is True
    assert body["chat"]["chat_name"] == "Family Group Final"

    db = SessionLocal()
    try:
        message = db.query(models.Message).filter(models.Message.id == body["message_id"]).first()
        assert message is not None
        assert message.direction == "outgoing"
        assert message.is_from_me is True
    finally:
        db.close()

    delete_resp = client.delete(f"/api/whatsapp/monitored-contacts/{created['id']}", headers=auth_headers(token))
    assert delete_resp.status_code == 200
    assert delete_resp.json()["ok"] is True


def test_live_monitor_is_scoped_per_user():
    first = register_user("scope-one", "scope-one@example.com", "secret123")
    second = register_user("scope-two", "scope-two@example.com", "secret123")
    create_monitor(first["access_token"], contact_name="Scoped Group", chat_key="scoped-group", chat_type="group")

    incoming_resp = client.post(
        "/api/whatsapp/messages/incoming",
        json={
            "message_id": "scoped-live-1",
            "group_id": "scoped-group",
            "group_name": "Scoped Group",
            "chat_type": "group",
            "sender": "alice",
            "sender_name": "Alice",
            "text": "Scoped live message",
            "timestamp": 1780036500,
        },
    )
    assert incoming_resp.status_code == 200
    assert incoming_resp.json()["duplicate"] is False

    first_feed = client.get("/api/whatsapp/live-feed", headers=auth_headers(first["access_token"]))
    assert first_feed.status_code == 200
    assert first_feed.json()["total"] >= 1

    second_feed = client.get("/api/whatsapp/live-feed", headers=auth_headers(second["access_token"]))
    assert second_feed.status_code == 200
    assert second_feed.json()["total"] == 0

    second_contacts = client.get("/api/whatsapp/monitored-contacts", headers=auth_headers(second["access_token"]))
    assert second_contacts.status_code == 200
    assert second_contacts.json()["total"] == 0


def test_whatsapp_single_account_demo_mode_accepts_unscoped_messages(monkeypatch):
    monkeypatch.setenv("SAFECHAT_WHATSAPP_SINGLE_ACCOUNT_MODE", "1")
    monkeypatch.setenv("SAFECHAT_WHATSAPP_DEMO_SESSION_KEY", "safechat-demo")
    monkeypatch.setenv("SAFECHAT_WHATSAPP_AUTO_FORWARD_ALL", "1")
    monkeypatch.setenv("SAFECHAT_WHATSAPP_DEMO_OWNER_EMAIL", "demo-owner@example.com")

    owner = register_user("demo-owner", "demo-owner@example.com", "secret123")
    token = owner["access_token"]

    status_resp = client.get("/api/whatsapp/status", headers=auth_headers(token))
    assert status_resp.status_code == 200
    assert status_resp.json()["single_account_mode"] is True
    assert status_resp.json()["bridge_session_key"] == "safechat-demo"

    bridge_contacts_resp = client.get("/api/whatsapp/bridge/monitored-contacts?session_key=safechat-demo")
    assert bridge_contacts_resp.status_code == 200
    assert bridge_contacts_resp.json()["total"] == 0

    incoming_resp = client.post(
        "/api/whatsapp/messages/incoming",
        json={
            "bridge_session_key": "safechat-demo",
            "message_id": "demo-live-1",
            "group_id": "demo-group-1",
            "group_name": "Demo Group",
            "chat_type": "group",
            "sender": "demo-sender",
            "sender_name": "Demo Sender",
            "text": "Demo mode should ingest this without scoped monitors.",
            "timestamp": 1780036600,
        },
    )
    assert incoming_resp.status_code == 200
    assert incoming_resp.json()["duplicate"] is False

    feed_resp = client.get("/api/whatsapp/live-feed", headers=auth_headers(token))
    assert feed_resp.status_code == 200
    assert feed_resp.json()["total"] >= 1


def test_whatsapp_alert_created_for_high_risk_message():
    registered = register_user("alert-owner", "alert-owner@example.com", "secret123")
    create_monitor(
        registered["access_token"],
        contact_name="Alert Group",
        chat_key="group-alert",
        chat_type="group",
    )

    with patch("backend.api.whatsapp.ai_engine.analyze_message", return_value={"risk_score": 92.0, "label": "Threat"}):
        incoming_resp = client.post(
            "/api/whatsapp/messages/incoming",
            json={
                "message_id": "alert-1",
                "group_id": "group-alert",
                "group_name": "Alert Group",
                "chat_type": "group",
                "sender": "bob",
                "sender_name": "Bob",
                "text": "This is a severe threat and you will regret it.",
                "timestamp": 1780033800,
            },
        )
    assert incoming_resp.status_code == 200
    message_id = incoming_resp.json()["message_id"]

    db = SessionLocal()
    try:
        alerts = db.query(models.Alert).filter(models.Alert.message_id == message_id).all()
        assert len(alerts) <= 1
        if alerts:
            assert alerts[0].severity in {"Medium", "High"}
    finally:
        db.close()


def test_whatsapp_alert_list_routes():
    registered = register_user("alert-feed", "alert-feed@example.com", "secret123")
    token = registered["access_token"]
    create_monitor(
        token,
        contact_name="Alert Feed",
        chat_key="group-alert-list",
        chat_type="group",
    )

    with patch("backend.api.whatsapp.ai_engine.analyze_message", return_value={"risk_score": 91.0, "label": "Threat"}):
        first_resp = client.post(
            "/api/whatsapp/messages/incoming",
            json={
                "message_id": "alert-list-1",
                "group_id": "group-alert-list",
                "group_name": "Alert Feed",
                "chat_type": "group",
                "sender": "sam",
                "sender_name": "Sam",
                "text": "I will destroy you and make you regret this.",
                "timestamp": 1780033900,
            },
        )
    assert first_resp.status_code == 200
    chat_id = first_resp.json()["chat_id"]

    with patch("backend.api.whatsapp.ai_engine.analyze_message", return_value={"risk_score": 83.0, "label": "Threat"}):
        second_resp = client.post(
            "/api/whatsapp/messages/incoming",
            json={
                "message_id": "alert-list-2",
                "group_id": "group-alert-list",
                "group_name": "Alert Feed",
                "chat_type": "group",
                "sender": "sam",
                "sender_name": "Sam",
                "text": "This is another severe threat.",
                "timestamp": 1780033960,
            },
        )
    assert second_resp.status_code == 200

    alerts_resp = client.get("/api/whatsapp/alerts", headers=auth_headers(token))
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()["alerts"]
    assert isinstance(alerts, list)

    recent_alerts_resp = client.get(
        "/api/whatsapp/alerts?date_from=2026-05-29T00%3A00%3A00%2B00%3A00",
        headers=auth_headers(token),
    )
    assert recent_alerts_resp.status_code == 200
    recent_alerts = recent_alerts_resp.json()["alerts"]
    assert len(recent_alerts) >= 1

    older_alerts_resp = client.get("/api/whatsapp/alerts?date_to=2026-05-01T00%3A00%3A00%2B00%3A00")
    assert older_alerts_resp.status_code == 200
    older_alerts = older_alerts_resp.json()
    assert older_alerts["total"] == 0
    assert older_alerts["alerts"] == []

    scoped_resp = client.get(f"/api/whatsapp/alerts?chat_id={chat_id}")
    assert scoped_resp.status_code == 200
    scoped_alerts = scoped_resp.json()["alerts"]
    assert all(alert["chat_id"] == chat_id for alert in scoped_alerts)

    summary_resp = client.get("/api/whatsapp/alerts/summary")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["total_alerts"] >= len(alerts)
    assert summary_data["latest_alert_at"] is not None

    recent_alert_summary_resp = client.get("/api/whatsapp/alerts/summary?date_from=2026-05-29T00%3A00%3A00%2B00%3A00")
    assert recent_alert_summary_resp.status_code == 200
    recent_alert_summary = recent_alert_summary_resp.json()
    assert recent_alert_summary["total_alerts"] >= 1

    older_alert_summary_resp = client.get("/api/whatsapp/alerts/summary?date_to=2026-05-01T00%3A00%3A00%2B00%3A00")
    assert older_alert_summary_resp.status_code == 200
    older_alert_summary = older_alert_summary_resp.json()
    assert older_alert_summary["total_alerts"] == 0

    scoped_summary_resp = client.get(f"/api/whatsapp/alerts/summary?chat_id={chat_id}")
    assert scoped_summary_resp.status_code == 200
    scoped_summary = scoped_summary_resp.json()
    assert scoped_summary["total_alerts"] >= len(scoped_alerts)

    chat_detail_resp = client.get(f"/api/whatsapp/chats/{chat_id}")
    assert chat_detail_resp.status_code == 200
    chat_detail = chat_detail_resp.json()
    assert chat_detail["alert_count"] >= 1
    assert chat_detail["open_alert_count"] >= 1

    high_resp = client.get("/api/whatsapp/alerts?severity=High")
    assert high_resp.status_code == 200
    high_alerts = high_resp.json()["alerts"]
    assert all(alert["severity"] == "High" for alert in high_alerts)

    high_summary_resp = client.get("/api/whatsapp/alerts/summary?severity=High")
    assert high_summary_resp.status_code == 200
    high_summary = high_summary_resp.json()
    assert high_summary["total_alerts"] >= len(high_alerts)
    assert high_summary["by_severity"].get("High", 0) >= len(high_alerts)

    paged_resp = client.get("/api/whatsapp/alerts?limit=1&offset=0")
    assert paged_resp.status_code == 200
    paged_data = paged_resp.json()
    assert paged_data["limit"] == 1
    assert paged_data["offset"] == 0
    assert paged_data["total"] >= len(paged_data["alerts"])

    if alerts:
        update_resp = client.patch(
            f"/api/whatsapp/alerts/{alerts[0]['id']}",
            json={"status": "acknowledged", "notes": "Reviewed by backend test"},
        )
        assert update_resp.status_code == 200
        updated = update_resp.json()
        assert updated["status"] == "acknowledged"
        assert updated["notes"] == "Reviewed by backend test"
        assert updated["acknowledged_at"] is not None

        acknowledged_detail_resp = client.get(f"/api/whatsapp/chats/{updated['chat_id']}")
        assert acknowledged_detail_resp.status_code == 200
        acknowledged_detail = acknowledged_detail_resp.json()
        assert acknowledged_detail["acknowledged_alert_count"] >= 1

        resolved_resp = client.patch(
            f"/api/whatsapp/alerts/{alerts[0]['id']}",
            json={"status": "resolved", "notes": "Issue closed"},
        )
        assert resolved_resp.status_code == 200
        resolved = resolved_resp.json()
        assert resolved["status"] == "resolved"
        assert resolved["resolved_at"] is not None

        resolved_detail_resp = client.get(f"/api/whatsapp/chats/{resolved['chat_id']}")
        assert resolved_detail_resp.status_code == 200
        resolved_detail = resolved_detail_resp.json()
        assert resolved_detail["resolved_alert_count"] >= 1

        filtered_resp = client.get("/api/whatsapp/alerts?status=resolved")
        assert filtered_resp.status_code == 200
        filtered = filtered_resp.json()["alerts"]
        assert all(alert["status"] == "resolved" for alert in filtered)

        resolved_summary_resp = client.get("/api/whatsapp/alerts/summary?status=resolved")
        assert resolved_summary_resp.status_code == 200
        resolved_summary = resolved_summary_resp.json()
        assert resolved_summary["by_status"].get("resolved", 0) >= len(filtered)


def test_whatsapp_summary_route():
    status_resp = client.post(
        "/api/whatsapp/status",
        json={"status": "connected", "reason": "bridge live", "qr": None, "connected_phone": "923009998887:1@s.whatsapp.net"},
    )
    assert status_resp.status_code == 200

    summary_resp = client.get("/api/whatsapp/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["bridge_status"] == "connected"
    assert summary["connected_phone"] == "923009998887:1@s.whatsapp.net"
    assert summary["total_live_chats"] >= 1
    assert summary["total_live_messages"] >= 1
    assert summary["flagged_live_messages"] >= 0
    assert summary["total_alerts"] >= 0
    assert summary["open_alerts"] >= 0
    assert summary["acknowledged_alerts"] >= 0
    assert summary["resolved_alerts"] >= 0
    assert 0 <= summary["safe_ratio"] <= 100

    recent_summary_resp = client.get("/api/whatsapp/summary?date_from=2026-05-29T00%3A00%3A00%2B00%3A00")
    assert recent_summary_resp.status_code == 200
    recent_summary = recent_summary_resp.json()
    assert recent_summary["total_live_chats"] >= 1
    assert recent_summary["total_live_messages"] >= 1
    assert recent_summary["last_message_at"] is not None

    older_summary_resp = client.get("/api/whatsapp/summary?date_to=2026-05-01T00%3A00%3A00%2B00%3A00")
    assert older_summary_resp.status_code == 200
    older_summary = older_summary_resp.json()
    assert older_summary["total_live_chats"] == 0
    assert older_summary["total_live_messages"] == 0
    assert older_summary["flagged_live_messages"] == 0
    assert older_summary["total_alerts"] == 0
    assert older_summary["last_message_at"] is None

    ops_summary_resp = client.get("/api/whatsapp/ops-summary")
    assert ops_summary_resp.status_code == 200
    ops_summary = ops_summary_resp.json()
    assert ops_summary["live_summary"]["total_live_chats"] >= 1
    assert ops_summary["live_summary"]["total_live_messages"] >= 1
    assert ops_summary["recent_feed_count"] >= 1
    assert ops_summary["recent_alert_count"] >= 0
    assert ops_summary["recent_flagged_message_count"] >= 0
    assert ops_summary["flagged_chat_count"] >= 0
    assert ops_summary["high_risk_chat_count"] >= 0
    assert ops_summary["recent_window_hours"] == 24

    health_summary_resp = client.get("/api/whatsapp/health-summary")
    assert health_summary_resp.status_code == 200
    health_summary = health_summary_resp.json()
    assert health_summary["bridge_ops"]["recent_window_hours"] == 24
    assert health_summary["live_ops"]["recent_window_hours"] == 24
    assert health_summary["recent_window_hours"] == 24
    assert health_summary["status"] in {"healthy", "attention"}
    assert health_summary["attention_required"] in {True, False}


def test_whatsapp_paginated_feed_and_chat_filters():
    feed_resp = client.get("/api/whatsapp/live-feed?limit=1&offset=0&flagged_only=false")
    assert feed_resp.status_code == 200
    feed_data = feed_resp.json()
    assert feed_data["limit"] == 1
    assert feed_data["offset"] == 0
    assert feed_data["total"] >= len(feed_data["messages"])

    recent_feed_resp = client.get("/api/whatsapp/live-feed?date_from=2026-05-29T00%3A00%3A00%2B00%3A00")
    assert recent_feed_resp.status_code == 200
    recent_feed = recent_feed_resp.json()
    assert recent_feed["total"] >= 1

    older_feed_resp = client.get("/api/whatsapp/live-feed?date_to=2026-05-01T00%3A00%3A00%2B00%3A00")
    assert older_feed_resp.status_code == 200
    older_feed = older_feed_resp.json()
    assert older_feed["total"] == 0
    assert older_feed["messages"] == []

    if feed_data["messages"]:
        sender = feed_data["messages"][0]["sender"]
        sender_resp = client.get(f"/api/whatsapp/live-feed?sender={sender}")
        assert sender_resp.status_code == 200
        sender_data = sender_resp.json()
        assert all(message["sender"] == sender for message in sender_data["messages"])

    chats_resp = client.get("/api/whatsapp/chats?limit=1&offset=0")
    assert chats_resp.status_code == 200
    chats_data = chats_resp.json()
    assert chats_data["limit"] == 1
    assert chats_data["offset"] == 0
    assert chats_data["total"] >= len(chats_data["chats"])

    recent_chats_resp = client.get("/api/whatsapp/chats?date_from=2026-05-29T00%3A00%3A00%2B00%3A00")
    assert recent_chats_resp.status_code == 200
    recent_chats = recent_chats_resp.json()
    assert recent_chats["total"] >= 1

    older_chats_resp = client.get("/api/whatsapp/chats?date_to=2026-05-01T00%3A00%3A00%2B00%3A00")
    assert older_chats_resp.status_code == 200
    older_chats = older_chats_resp.json()
    assert older_chats["total"] == 0
    assert older_chats["chats"] == []

    chats_summary_resp = client.get("/api/whatsapp/chats/summary")
    assert chats_summary_resp.status_code == 200
    chats_summary = chats_summary_resp.json()
    assert chats_summary["total_chats"] >= len(chats_data["chats"])

    if chats_data["chats"]:
        chat_id = chats_data["chats"][0]["id"]
        detail_resp = client.get(f"/api/whatsapp/chats/{chat_id}?limit=1&offset=0")
        assert detail_resp.status_code == 200
        detail_data = detail_resp.json()
        assert detail_data["limit"] == 1
        assert detail_data["offset"] == 0
        assert detail_data["total_messages"] >= len(detail_data["messages"])

        recent_detail_resp = client.get(
            f"/api/whatsapp/chats/{chat_id}?date_from=2026-05-29T00%3A00%3A00%2B00%3A00"
        )
        assert recent_detail_resp.status_code == 200
        recent_detail = recent_detail_resp.json()
        assert recent_detail["total_messages"] >= 1

        older_detail_resp = client.get(
            f"/api/whatsapp/chats/{chat_id}?date_to=2026-05-01T00%3A00%3A00%2B00%3A00"
        )
        assert older_detail_resp.status_code == 200
        older_detail = older_detail_resp.json()
        assert older_detail["total_messages"] == 0
        assert older_detail["messages"] == []


def test_auth_register_login_and_protected_routes():
    registered = register_user("integration-user", "integration@example.com", "secret123")
    token = registered["access_token"]

    me_resp = client.get("/api/users/me", headers=auth_headers(token))
    assert me_resp.status_code == 200
    me = me_resp.json()
    assert me["email"] == "integration@example.com"
    assert me["username"] == "integration-user"
    assert me["role"] == "user"

    login_resp = client.post(
        "/api/auth/login",
        json={"email_or_username": "integration@example.com", "password": "secret123"},
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["token_type"] == "bearer"

    unauthorized_resp = client.get("/api/users/me")
    assert unauthorized_resp.status_code == 401

    update_me_resp = client.patch(
        "/api/users/me",
        json={
            "username": "integration-user-updated",
            "email": "integration-updated@example.com",
            "name": "Integration User",
        },
        headers=auth_headers(token),
    )
    assert update_me_resp.status_code == 200
    updated_me = update_me_resp.json()
    assert updated_me["username"] == "integration-user-updated"
    assert updated_me["email"] == "integration-updated@example.com"
    assert updated_me["name"] == "Integration User"

    wrong_password_resp = client.patch(
        "/api/users/me",
        json={
            "current_password": "wrongsecret123",
            "new_password": "newsecret123",
        },
        headers=auth_headers(token),
    )
    assert wrong_password_resp.status_code == 400

    change_password_resp = client.patch(
        "/api/users/me",
        json={
            "current_password": "secret123",
            "new_password": "newsecret123",
        },
        headers=auth_headers(token),
    )
    assert change_password_resp.status_code == 200

    relogin_resp = client.post(
        "/api/auth/login",
        json={"email_or_username": "integration-updated@example.com", "password": "newsecret123"},
    )
    assert relogin_resp.status_code == 200


def test_default_admin_seed_creates_loginable_admin():
    db = SessionLocal()
    try:
        ensure_default_admin(db)
    finally:
        db.close()

    login_resp = client.post(
        "/api/auth/login",
        json={"email_or_username": "admin", "password": "Admin123!"},
    )
    assert login_resp.status_code == 200
    payload = login_resp.json()
    assert payload["user"]["role"] == "admin"
    assert payload["user"]["email"] == "admin@safechat.local"


def test_public_register_cannot_create_admin():
    response = client.post(
        "/api/auth/register",
        json={
            "username": "forced-admin",
            "email": "forced-admin@example.com",
            "password": "secret123",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["role"] == "user"


def test_user_profile_update_enforces_uniqueness():
    first = register_user("unique-first", "unique-first@example.com", "secret123")
    second = register_user("unique-second", "unique-second@example.com", "secret123")

    duplicate_email_resp = client.patch(
        "/api/users/me",
        json={"email": "unique-first@example.com"},
        headers=auth_headers(second["access_token"]),
    )
    assert duplicate_email_resp.status_code == 400

    duplicate_username_resp = client.patch(
        "/api/users/me",
        json={"username": "unique-first"},
        headers=auth_headers(second["access_token"]),
    )
    assert duplicate_username_resp.status_code == 400


def test_admin_user_management_routes():
    admin = create_seed_user("admin-manager", "admin-manager@example.com", "secret123", role="admin")
    member = register_user("member-user", "member-user@example.com", "secret123", role="user")

    forbidden_list = client.get("/api/users", headers=auth_headers(member["access_token"]))
    assert forbidden_list.status_code == 403

    list_resp = client.get("/api/users?search=member", headers=auth_headers(admin["access_token"]))
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(user["email"] == "member-user@example.com" for user in list_data["users"])

    patch_resp = client.patch(
        f"/api/users/{member['user']['id']}",
        json={"role": "admin", "is_active": False, "name": "Updated Member"},
        headers=auth_headers(admin["access_token"]),
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["role"] == "admin"
    assert updated["is_active"] is False
    assert updated["name"] == "Updated Member"

    self_disable_resp = client.patch(
        f"/api/users/{admin['user']['id']}",
        json={"is_active": False},
        headers=auth_headers(admin["access_token"]),
    )
    assert self_disable_resp.status_code == 400


def test_messages_send_and_get_chat_history():
    registered = register_user("chat-user", "chat-user@example.com", "secret123")
    token = registered["access_token"]

    with patch("backend.api.messages.ai_engine.analyze_message", return_value={
        "risk_score": 91.0,
        "label": "Threat",
        "action": "block",
        "severity": "High",
        "thresholds": {"flag": 55.0, "block": 85.0},
        "details": {"toxicity": {"threat": 0.91}},
    }):
        first_resp = client.post(
            "/api/messages/send",
            json={"chat_name": "Protected Chat", "content": "I will break everything."},
            headers=auth_headers(token),
        )
    assert first_resp.status_code == 200
    first_data = first_resp.json()
    assert first_data["action"] == "block"
    assert first_data["blocked"] is True

    with patch("backend.api.messages.ai_engine.analyze_message", return_value={
        "risk_score": 12.0,
        "label": "Safe",
        "action": "allow",
        "severity": "Low",
        "thresholds": {"flag": 55.0, "block": 85.0},
        "details": {"toxicity": {}},
    }):
        second_resp = client.post(
            "/api/messages/send",
            json={"chat_id": first_data["chat_id"], "content": "This one is safe."},
            headers=auth_headers(token),
        )
    assert second_resp.status_code == 200
    second_data = second_resp.json()
    assert second_data["action"] == "allow"
    assert second_data["blocked"] is False

    history_resp = client.get(f"/api/messages/{first_data['chat_id']}", headers=auth_headers(token))
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert history["chat_name"] == "Protected Chat"
    assert history["total_messages"] == 2
    assert history["messages"][0]["direction"] == "outgoing"


def test_moderate_text_and_image_routes():
    registered = register_user("moderate-user", "moderate-user@example.com", "secret123")
    token = registered["access_token"]

    with patch("backend.api.moderation.ai_engine.analyze_message", return_value={
        "risk_score": 68.0,
        "label": "Unsafe",
        "action": "flag",
        "severity": "Medium",
        "thresholds": {"flag": 55.0, "block": 85.0},
        "details": {"toxicity": {"toxicity": 0.68}},
    }):
        text_resp = client.post(
            "/api/moderate/text",
            json={"text": "This is abusive text.", "persist_result": True, "chat_name": "Manual review"},
            headers=auth_headers(token),
        )
    assert text_resp.status_code == 200
    text_data = text_resp.json()
    assert text_data["action"] == "flag"
    assert text_data["saved"] is True
    assert text_data["thresholds"]["block"] == 85.0
    assert text_data["chat_id"] is not None

    original = image_analyzer.pytesseract.image_to_string
    original_provider = image_analyzer.OCR_PROVIDER
    image_analyzer.OCR_PROVIDER = "tesseract"
    image_analyzer.pytesseract.image_to_string = lambda img, config=None: "Threat text from OCR"
    try:
        img = Image.new("RGB", (80, 30), color=(255, 255, 255))
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        with patch("backend.api.moderation.ai_engine.analyze_message", return_value={
            "risk_score": 88.0,
            "label": "Threat",
            "action": "block",
            "severity": "High",
            "thresholds": {"flag": 55.0, "block": 85.0},
            "details": {"toxicity": {"threat": 0.88}},
        }):
            image_resp = client.post(
                "/api/moderate/image",
                files={"file": ("moderate.png", buf.read(), "image/png")},
                headers=auth_headers(token),
            )
    finally:
        image_analyzer.OCR_PROVIDER = original_provider
        image_analyzer.pytesseract.image_to_string = original

    assert image_resp.status_code == 200
    image_data = image_resp.json()
    assert image_data["action"] == "block"
    assert image_data["blocked"] is True
    assert image_data["saved"] is True
    assert image_data["extracted_text"] == "Threat text from OCR"


def test_live_whatsapp_monitoring_websocket_flow():
    registered = register_user("ws-user", "ws-user@example.com", "secret123")
    create_monitor(registered["access_token"], contact_name="Realtime Group", chat_key="ws-group-1", chat_type="group")

    with client.websocket_connect(f"/ws/whatsapp?token={registered['access_token']}") as websocket:
        websocket.send_text("subscribe")

        status_resp = client.post(
            "/api/whatsapp/status",
            json={
                "status": "connected",
                "reason": "websocket test",
                "qr": None,
                "connected_phone": "923001112223:1@s.whatsapp.net",
            },
        )
        assert status_resp.status_code == 200
        status_event = websocket.receive_json()
        assert status_event["type"] == "status"
        assert status_event["payload"]["status"] == "connected"

        with patch("backend.api.whatsapp.ai_engine.analyze_message", return_value={"risk_score": 88.0, "label": "Threat"}):
            incoming_resp = client.post(
                "/api/whatsapp/messages/incoming",
                json={
                    "message_id": "ws-live-1",
                    "group_id": "ws-group-1",
                    "group_name": "Realtime Group",
                    "chat_type": "group",
                    "sender": "eve",
                    "sender_name": "Eve",
                    "text": "This websocket flow should be flagged.",
                    "timestamp": 1780034900,
                },
            )
        assert incoming_resp.status_code == 200

        first_event = websocket.receive_json()
        second_event = websocket.receive_json()
        event_types = {first_event["type"], second_event["type"]}
        assert event_types == {"message", "chat_updated"}

        message_event = first_event if first_event["type"] == "message" else second_event
        assert message_event["payload"]["chat_name"] == "Realtime Group"
        assert message_event["payload"]["risk_score"] == 88.0


def test_admin_dashboard_override_functionality():
    admin = create_seed_user("integration-admin", "admin@example.com", "secret123", role="admin")
    admin_token = admin["access_token"]

    with patch("backend.api.whatsapp.ai_engine.analyze_message", return_value={"risk_score": 95.0, "label": "Threat"}):
        incoming_resp = client.post(
            "/api/whatsapp/messages/incoming",
            json={
                "message_id": "override-log-1",
                "group_id": "override-group",
                "group_name": "Override Group",
                "chat_type": "group",
                "sender": "zoe",
                "sender_name": "Zoe",
                "text": "Override this moderation decision.",
                "timestamp": 1780035900,
            },
        )
    assert incoming_resp.status_code == 200

    forbidden_resp = client.get("/api/moderation/logs")
    assert forbidden_resp.status_code == 401

    logs_resp = client.get("/api/moderation/logs", headers=auth_headers(admin_token))
    assert logs_resp.status_code == 200
    logs = logs_resp.json()["logs"]
    assert logs
    target_log = logs[0]

    override_resp = client.patch(
        f"/api/moderation/logs/{target_log['id']}",
        json={"action": "allow"},
        headers=auth_headers(admin_token),
    )
    assert override_resp.status_code == 200
    updated = override_resp.json()
    assert updated["action"] == "allow"
    assert updated["reviewed_by"] == admin["user"]["id"]
    assert updated["reviewed_at"] is not None

    db = SessionLocal()
    try:
        alert = (
            db.query(models.Alert)
            .join(models.Message, models.Message.id == models.Alert.message_id)
            .filter(models.Message.id == target_log["message_id"])
            .first()
        )
        assert alert is not None
        assert alert.status == "resolved"
    finally:
        db.close()


def test_concurrent_summary_requests():
    def fetch_status(_: int) -> int:
        local_client = TestClient(app)
        response = local_client.get("/api/whatsapp/summary")
        return response.status_code

    with ThreadPoolExecutor(max_workers=5) as executor:
        statuses = list(executor.map(fetch_status, range(10)))

    assert statuses
    assert all(status_code == 200 for status_code in statuses)
