System dependencies and limitations

- Tesseract-OCR: Required for image OCR (`pytesseract`). On Windows, install Tesseract and add to PATH or set `pytesseract.pytesseract.tesseract_cmd` to the executable path.
- Hugging Face models and `detoxify` may download large weights on first use. Set `HF_TOKEN` environment variable to speed up downloads for private/large models.
- Local custom model: place under `best_model/` at repository root. The system will skip cleanly if missing.

Limitations / Next improvements

- Model warm-up: models are downloaded lazily in background; initial analysis may be less accurate until models finish downloading.
- Authentication and multi-user isolation are minimal; database is SQLite for local dev.
- Testing: core endpoints are covered by basic integration tests. Expand tests for edge cases and parser formats.
- Real-time: current implementation uses WebSocket broadcast; consider authentication and scaling (Redis pub/sub) for production.
