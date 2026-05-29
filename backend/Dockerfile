FROM python:3.11-slim
WORKDIR /app

# Install system deps for Tesseract if required (optional, commented)
# RUN apt-get update && apt-get install -y tesseract-ocr libgl1 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
