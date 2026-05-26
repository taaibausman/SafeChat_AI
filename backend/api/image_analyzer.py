import os
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from database.config import get_db
import models.domain as models
import schemas.domain as schemas
from ai.engine import ai_engine
from PIL import Image
import pytesseract
import io

router = APIRouter()

# Note: pytesseract requires Tesseract-OCR to be installed on the system.
# For Windows, you usually need to set the path if it's not in PATH:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

@router.post("/upload", response_model=schemas.ChatUploadResponse)
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are supported")
        
    content = await file.read()
    try:
        image = Image.open(io.BytesIO(content))
        # Optional: set tesseract path if it fails here
        try:
            extracted_text = pytesseract.image_to_string(image)
        except pytesseract.TesseractNotFoundError:
            raise HTTPException(
                status_code=500, 
                detail="Tesseract OCR is not installed or not in PATH. Please install Tesseract-OCR."
            )
            
        if not extracted_text.strip():
            raise HTTPException(status_code=400, detail="Could not extract any text from the image")
            
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=f"Failed to process image: {str(e)}")
        
    # Analyze extracted text
    analysis = ai_engine.analyze_message(extracted_text)
    score = analysis["risk_score"]
    label = analysis["label"]
    
    # Save chat to DB
    new_chat = models.Chat(platform="Image_OCR", chat_name=file.filename)
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)
    
    # Save the extracted text as a single message
    db_msg = models.Message(
        chat_id=new_chat.id,
        sender="Extracted_Text",
        message=extracted_text,
        risk_score=score,
        label=label
    )
    db.add(db_msg)
    
    # Save overall AnalysisResult
    result = models.AnalysisResult(
        chat_id=new_chat.id,
        overall_score=score,
        safe_percentage=100.0 if score < 50 else 0.0,
        unsafe_percentage=100.0 if score >= 50 else 0.0,
        summary=f"Analyzed extracted text. Detected label: {label}"
    )
    db.add(result)
    db.commit()
    
    return {"chat_id": new_chat.id, "message": f"Successfully extracted and analyzed text."}
