from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from database.config import get_db
import models.domain as models
import schemas.domain as schemas
from utils.parser import parse_whatsapp_chat
from ai.engine import ai_engine

router = APIRouter()

@router.post("/upload", response_model=schemas.ChatUploadResponse)
async def upload_chat(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported for WhatsApp exports")
        
    content = await file.read()
    text_content = content.decode("utf-8")
    
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
            risk_score=score,
            label=label
        )
        db.add(db_msg)
        
    db.commit()
    
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
