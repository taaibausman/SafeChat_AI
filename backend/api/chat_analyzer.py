from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.database.config import get_db
import backend.models.domain as models
import backend.schemas.domain as schemas
from backend.utils.parser import parse_whatsapp_chat
from backend.ai.engine import ai_engine
from backend.api.realtime import manager as realtime_manager
import asyncio

router = APIRouter()

@router.post("/upload", response_model=schemas.ChatUploadResponse)
async def upload_chat(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported for WhatsApp exports")
        
    content = await file.read()
    text_content = content.decode("utf-8", errors="ignore")
    
    parsed_messages = parse_whatsapp_chat(text_content)
    if not parsed_messages:
        raise HTTPException(status_code=400, detail="Could not parse any messages from the file")
        
    # Save chat to DB
    new_chat = models.Chat(platform="WhatsApp", chat_name=file.filename)
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)
    
    # Analyze messages and save to DB
    total_messages = len(parsed_messages)
    unsafe_count = 0
    total_score = 0
    
    for msg in parsed_messages:
        analysis = ai_engine.analyze_message(msg["message"])
        score = analysis["risk_score"]
        label = analysis["label"]
        
        if score > 50:
            unsafe_count += 1
        total_score += score
            
        db_msg = models.Message(
            chat_id=new_chat.id,
            sender=msg["sender"],
            message=msg["message"],
            timestamp=msg["timestamp"],
            risk_score=score,
            label=label
        )
        db.add(db_msg)
        db.commit()
        db.refresh(db_msg)

        # Broadcast a live message event (fire-and-forget)
        try:
            payload = {
                "type": "message",
                "payload": {
                    "id": db_msg.id,
                    "chat_id": new_chat.id,
                    "chat_name": new_chat.chat_name,
                    "sender": db_msg.sender,
                    "message": db_msg.message,
                    "timestamp": db_msg.timestamp.isoformat() if db_msg.timestamp else None,
                    "risk_score": db_msg.risk_score,
                    "label": db_msg.label,
                }
            }
            asyncio.create_task(realtime_manager.broadcast(payload))
        except Exception:
            pass
    
    
    # Save overall AnalysisResult
    safe_count = total_messages - unsafe_count
    safe_perc = (safe_count / total_messages * 100) if total_messages > 0 else 100
    unsafe_perc = (unsafe_count / total_messages * 100) if total_messages > 0 else 0
    overall = (total_score / total_messages) if total_messages > 0 else 0
    
    result = models.AnalysisResult(
        chat_id=new_chat.id,
        overall_score=overall,
        safe_percentage=safe_perc,
        unsafe_percentage=unsafe_perc,
        summary=f"Found {unsafe_count} unsafe messages out of {total_messages}."
    )
    db.add(result)
    db.commit()
    
    return {"chat_id": new_chat.id, "message": f"Successfully analyzed {total_messages} messages."}

@router.get("/report/{chat_id}", response_model=schemas.ChatDetailResponse)
def get_report(chat_id: int, db: Session = Depends(get_db)):
    chat = db.query(models.Chat).filter(models.Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    return chat

@router.get("/dashboard-summary", response_model=schemas.DashboardSummaryResponse)
def get_dashboard_summary(db: Session = Depends(get_db)):
    total_chats = db.query(func.count(models.Chat.id)).scalar() or 0
    total_messages = db.query(func.count(models.Message.id)).scalar() or 0
    flagged_messages = (
        db.query(func.count(models.Message.id))
        .filter(models.Message.risk_score > 50)
        .scalar()
        or 0
    )
    safe_ratio = ((total_messages - flagged_messages) / total_messages * 100) if total_messages else 100.0

    recent_rows = (
        db.query(models.Chat, models.AnalysisResult)
        .outerjoin(models.AnalysisResult, models.AnalysisResult.chat_id == models.Chat.id)
        .order_by(models.Chat.created_at.desc())
        .limit(5)
        .all()
    )

    recent_chats = []
    for chat, analysis in recent_rows:
        chat_flagged = (
            db.query(func.count(models.Message.id))
            .filter(models.Message.chat_id == chat.id, models.Message.risk_score > 50)
            .scalar()
            or 0
        )
        recent_chats.append(
            schemas.DashboardRecentChat(
                id=chat.id,
                chat_name=chat.chat_name,
                platform=chat.platform,
                created_at=chat.created_at,
                unsafe_percentage=analysis.unsafe_percentage if analysis else None,
                flagged_messages=chat_flagged,
            )
        )

    return schemas.DashboardSummaryResponse(
        total_chats=total_chats,
        total_messages=total_messages,
        flagged_messages=flagged_messages,
        safe_ratio=round(safe_ratio, 1),
        recent_chats=recent_chats,
    )
