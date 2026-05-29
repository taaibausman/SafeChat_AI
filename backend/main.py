import os
import sys
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is on sys.path so backend package imports work
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.api.chat_analyzer import router as chat_router
from backend.api.image_analyzer import router as image_router
from backend.api.realtime import router as realtime_router
from backend.api.whatsapp import router as whatsapp_router
from backend.ai.engine import ai_engine
from backend.database.config import engine, Base

app = FastAPI(
    title="SafeChat AI API",
    description="API for SafeChat AI chat analysis and OCR image analysis.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api/analyze", tags=["analyze"])
app.include_router(image_router, prefix="/api/image", tags=["image"])
app.include_router(whatsapp_router, prefix="/api/whatsapp", tags=["whatsapp"])
app.include_router(realtime_router, tags=["realtime"])


@app.on_event("startup")
async def on_startup():
    Base.metadata.create_all(bind=engine)
    # Schedule model loading in background so startup isn't blocked
    try:
        asyncio.create_task(asyncio.to_thread(ai_engine._load_models))
    except Exception:
        # Fallback: fire-and-forget using loop
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, ai_engine._load_models)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
