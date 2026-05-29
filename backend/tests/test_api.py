from fastapi.testclient import TestClient
from backend.main import app
from backend.database.config import engine, Base
import backend.api.image_analyzer as image_analyzer
from io import BytesIO
from PIL import Image

client = TestClient(app)


def setup_module(module):
    # reset the database for tests
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


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


def test_image_upload():
    # Patch pytesseract to avoid dependency on system tesseract
    original = image_analyzer.pytesseract.image_to_string
    image_analyzer.pytesseract.image_to_string = lambda img: "Extracted test text"

    # Create a simple blank PNG image
    img = Image.new("RGB", (100, 30), color=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    files = {"file": ("test.png", buf.read(), "image/png")}
    resp = client.post("/api/image/upload", files=files)

    # restore
    image_analyzer.pytesseract.image_to_string = original

    assert resp.status_code == 200
    data = resp.json()
    assert "chat_id" in data


def test_whatsapp_status_and_incoming_routes():
    status_resp = client.post(
        "/api/whatsapp/status",
        json={"status": "connected", "reason": "test", "qr": None},
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "connected"

    incoming_resp = client.post(
        "/api/whatsapp/messages/incoming",
        json={
            "message_id": "test123",
            "group_id": "group-1",
            "group_name": "Test Group",
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

    feed_resp = client.get("/api/whatsapp/live-feed")
    assert feed_resp.status_code == 200
    feed_data = feed_resp.json()
    assert isinstance(feed_data.get("messages"), list)


def test_whatsapp_chat_and_bridge_routes(monkeypatch):
    import backend.api.whatsapp as whatsapp_api

    monkeypatch.setattr(
        whatsapp_api,
        "_bridge_request",
        lambda path, method="GET": (True, {"status": "connected", "detail": f"{method} {path}"}, None),
    )

    health_resp = client.get("/api/whatsapp/bridge-health")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert health_data["reachable"] is True
    assert health_data["status"] == "connected"

    restart_resp = client.post("/api/whatsapp/bridge-restart")
    assert restart_resp.status_code == 200
    restart_data = restart_resp.json()
    assert restart_data["reachable"] is True

    chats_resp = client.get("/api/whatsapp/chats")
    assert chats_resp.status_code == 200
    chats_data = chats_resp.json()
    assert isinstance(chats_data.get("chats"), list)
