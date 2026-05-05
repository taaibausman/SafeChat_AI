from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import joblib

# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

# ============================================================
# MODEL PATH
# ============================================================

MODEL_PATH = str(BASE_DIR / "best_model")

# ============================================================
# LOAD TOKENIZER
# ============================================================

try:
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_PATH,
        use_fast=False,
        local_files_only=True
    )

except Exception as e:
    raise RuntimeError(
        f"❌ Tokenizer loading failed.\n"
        f"Check if 'best_model' folder contains tokenizer files.\n\n"
        f"Original Error:\n{e}"
    )

# ============================================================
# LOAD MODEL
# ============================================================

try:
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_PATH,
        local_files_only=True
    )

    model.eval()

except Exception as e:
    raise RuntimeError(
        f"❌ Model loading failed.\n"
        f"Check if model files exist inside 'best_model'.\n\n"
        f"Original Error:\n{e}"
    )

# ============================================================
# LOAD LABEL MAP
# ============================================================

try:
    id2label = joblib.load(BASE_DIR / "id2label.pkl")

except Exception as e:
    raise RuntimeError(
        f"❌ Could not load id2label.pkl\n\n{e}"
    )

# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="SafeChat AI API",
    version="1.0"
)

# ============================================================
# REQUEST FORMAT
# ============================================================

class MessageRequest(BaseModel):
    text: str

# ============================================================
# ROOT ENDPOINT
# ============================================================

@app.get("/")
def home():
    return {
        "message": "SafeChat AI API Running"
    }

# ============================================================
# HEALTH ENDPOINT
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "ok"
    }

# ============================================================
# PREDICT ENDPOINT
# ============================================================

@app.post("/predict")
def predict(data: MessageRequest):

    text = data.text.strip()

    # --------------------------------------------------------
    # EMPTY INPUT CHECK
    # --------------------------------------------------------

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Empty input"
        )

    # --------------------------------------------------------
    # TOKENIZE
    # --------------------------------------------------------

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=160
    )

    # --------------------------------------------------------
    # MODEL INFERENCE
    # --------------------------------------------------------

    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits

    # --------------------------------------------------------
    # PREDICTION
    # --------------------------------------------------------

    predicted_class_id = torch.argmax(
        logits,
        dim=1
    ).item()

    probabilities = torch.softmax(
        logits,
        dim=1
    )

    confidence = probabilities[
        0
    ][predicted_class_id].item()

    predicted_label = id2label[
        predicted_class_id
    ]

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return {
        "text": text,
        "label": predicted_label,
        "confidence": round(confidence * 100, 2)
    }
