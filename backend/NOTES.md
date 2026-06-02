System dependencies and limitations

- EasyOCR: Recommended local OCR provider for screenshot-heavy workflows. Configure `SAFECHAT_OCR_PROVIDER=easyocr` or use `auto` to prefer it before external providers.
- Tesseract-OCR: Primary local OCR provider (`pytesseract`). On Windows, install Tesseract and add to PATH or set `pytesseract.pytesseract.tesseract_cmd` to the executable path.
- OCR.space: Optional free-tier external OCR provider for screenshots. Configure `OCR_SPACE_API_KEY` and set `SAFECHAT_OCR_PROVIDER=ocrspace` or `auto`.
- Google Cloud Vision OCR: Optional external OCR provider. The backend supports Application Default Credentials (ADC) via `GOOGLE_APPLICATION_CREDENTIALS` and can be selected with `SAFECHAT_OCR_PROVIDER=google` or used automatically with `SAFECHAT_OCR_PROVIDER=auto`.
- Hugging Face models and `detoxify` may download large weights on first use. Set `HF_TOKEN` environment variable to speed up downloads for private/large models.
- Local custom model: place under `best_model/` at repository root. The system will skip cleanly if missing.

Limitations / Next improvements

- Model warm-up: models are downloaded lazily in background; initial analysis may be less accurate until models finish downloading.
- Authentication and multi-user isolation are minimal; database is SQLite for local dev.
- Testing: core endpoints are covered by basic integration tests. Expand tests for edge cases and parser formats.
- Real-time: current implementation uses WebSocket broadcast; consider authentication and scaling (Redis pub/sub) for production.
