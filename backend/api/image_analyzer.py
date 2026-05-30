import io
import os
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database.config import get_db
import backend.models.domain as models
import backend.schemas.domain as schemas
from backend.ai.engine import ai_engine
from backend.api.realtime import manager as realtime_manager
import asyncio
from PIL import Image
from PIL import ImageEnhance
import pytesseract

router = APIRouter()

DEFAULT_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

if os.path.exists(DEFAULT_TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = DEFAULT_TESSERACT_PATH


def extract_text_from_image_bytes(content: bytes) -> str:
    try:
        image = Image.open(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to process image: {str(exc)}") from exc

    processed = ImageEnhance.Contrast(image.convert("L")).enhance(1.5)
    if processed.width < 1200:
        scale = 1200 / max(processed.width, 1)
        processed = processed.resize((1200, max(int(processed.height * scale), 1)))

    try:
        extracted_text = pytesseract.image_to_string(processed)
    except pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail="Tesseract OCR is not installed or not in PATH. Please install Tesseract-OCR.",
        ) from exc

    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract any text from the image")
    return extracted_text.strip()


def persist_image_analysis(
    *,
    db: Session,
    filename: str,
    extracted_text: str,
    analysis: dict,
) -> tuple[models.Chat, models.Message]:
    score = analysis["risk_score"]
    action = analysis.get("action") or ai_engine.action_for_score(score)
    severity = analysis.get("severity") or ai_engine.severity_for_score(score)

    new_chat = models.Chat(platform="Image_OCR", chat_name=filename)
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)

    db_msg = models.Message(
        chat_id=new_chat.id,
        sender="Extracted_Text",
        message=extracted_text,
        content=extracted_text,
        timestamp=datetime.now(timezone.utc),
        risk_score=score,
        toxicity_score=score,
        is_flagged=action in {"flag", "block"},
        label=analysis["label"],
        source="image_upload",
    )
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)

    toxicity_details = analysis.get("details", {}).get("toxicity", {})
    db.add(
        models.ModerationLog(
            message_id=db_msg.id,
            toxic=toxicity_details.get("toxicity", 0.0),
            severe_toxic=toxicity_details.get("severe_toxic", 0.0),
            obscene=toxicity_details.get("obscene", 0.0),
            threat=toxicity_details.get("threat", 0.0),
            insult=toxicity_details.get("insult", 0.0),
            identity_hate=toxicity_details.get("identity_hate", 0.0),
            action=action,
        )
    )
    db.add(
        models.ImageScan(
            file_path=filename or "uploaded-image",
            ocr_text=extracted_text,
            is_flagged=action in {"flag", "block"},
            toxicity_score=score,
            scan_time=datetime.now(timezone.utc),
        )
    )
    if action in {"flag", "block"}:
        db.add(
            models.Alert(
                message_id=db_msg.id,
                alert_type=analysis["label"] or "Unsafe",
                severity=severity,
                status="open",
            )
        )
    db.commit()
    return new_chat, db_msg

@router.post("/upload", response_model=schemas.ChatUploadResponse)
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are supported")
        
    content = await file.read()
    extracted_text = extract_text_from_image_bytes(content)
        
    # Analyze extracted text
    analysis = ai_engine.analyze_message(extracted_text)
    action = analysis.get("action") or ai_engine.action_for_score(analysis["risk_score"])
    new_chat, db_msg = persist_image_analysis(
        db=db,
        filename=file.filename or "uploaded-image",
        extracted_text=extracted_text,
        analysis=analysis,
    )

    # Broadcast live message
    try:
        payload = {
            "type": "message",
            "payload": {
                "id": db_msg.id,
                "chat_id": new_chat.id,
                "chat_name": new_chat.chat_name,
                "sender": db_msg.sender,
                "message": db_msg.message,
                "timestamp": db_msg.timestamp.isoformat(),
                "risk_score": db_msg.risk_score,
                "label": db_msg.label,
            }
        }
        asyncio.create_task(realtime_manager.broadcast(payload))
    except Exception:
        pass
    # Save overall AnalysisResult
    result = models.AnalysisResult(
        chat_id=new_chat.id,
        overall_score=analysis["risk_score"],
        safe_percentage=100.0 if action == "allow" else 0.0,
        unsafe_percentage=0.0 if action == "allow" else 100.0,
        summary=f"Analyzed extracted text. Detected label: {analysis['label']}"
    )
    db.add(result)
    db.commit()
    
    return {"chat_id": new_chat.id, "message": f"Successfully extracted and analyzed text."}
