# SafeChat AI

SafeChat AI is a local prototype for:
- analyzing exported chat logs
- analyzing OCR text from images
- monitoring live WhatsApp messages through a bridge

## Stack
- Backend: FastAPI + SQLAlchemy + SQLite
- Frontend: React + Vite
- Live bridge: Node.js WhatsApp relay

## Prerequisites
- Python 3.10+
- Node.js 18+
- Tesseract OCR for screenshot/image OCR
- EasyOCR as a local screenshot OCR option
- Optional: Google Cloud Vision as an external OCR provider
- Optional: OCR.space as a free-tier external OCR provider
- Optional: Docker for containerized backend runs

## Backend setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
python backend\scripts\migrate.py
```

Run the backend:

```powershell
.\backend\run_backend.ps1
```

Manual equivalent:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

## Frontend setup

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

## WhatsApp bridge setup

```powershell
cd whatsapp
copy .env.example .env
npm install
npm run dev
```

## Run all services

After dependencies are already installed:

```powershell
.\run_all.ps1
```

This starts backend, WhatsApp bridge, and frontend in separate PowerShell windows.

## Fresh environment checklist

See [DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md) for a root-level run/deploy checklist that covers:
- dependency install order
- migration and backend startup
- frontend build verification
- WhatsApp bridge verification
- optional Docker backend verification

## Manual QA and submission

- Manual QA checklist: [MANUAL_QA_CHECKLIST.md](./MANUAL_QA_CHECKLIST.md)
- Final submission prep: [SUBMISSION_PREP.md](./SUBMISSION_PREP.md)

## Backend operational endpoints

- `GET /api/whatsapp/health-summary`
- `GET /api/whatsapp/bridge-ops-summary`
- `GET /api/whatsapp/ops-summary`
- `GET /api/whatsapp/summary`

## Backend environment variables

Backend env examples live in `backend/.env.example`.

Current backend-facing settings:

- `WHATSAPP_BRIDGE_CONTROL_URL`
  Points the backend at the WhatsApp bridge control API. Default: `http://127.0.0.1:3011`
- `WHATSAPP_BRIDGE_EVENT_RETENTION`
  Maximum number of bridge event rows retained after pruning. Default: `1000`
- `WHATSAPP_BRIDGE_STATE_SNAPSHOT_RETENTION`
  Maximum number of bridge snapshot rows retained after pruning. Default: `1000`
- `SAFECHAT_DISABLE_MODELS`
  Optional lightweight mode for development or tests that should avoid loading live model inference
- `SAFECHAT_CUSTOM_MODEL_PATH`
  Optional override for the local Hugging Face classifier directory. By default the backend now checks `classifier/` first, then `best_model/`
- `SAFECHAT_CREATE_DEFAULT_ADMIN`
  When enabled, backend startup ensures a local admin account exists
- `SAFECHAT_DEFAULT_ADMIN_USERNAME`, `SAFECHAT_DEFAULT_ADMIN_EMAIL`, `SAFECHAT_DEFAULT_ADMIN_PASSWORD`
  Credentials for the seeded local admin account
- `SAFECHAT_OCR_PROVIDER`
  OCR provider selection for image uploads. Supported values are `easyocr`, `tesseract`, `google`, `ocrspace`, and `auto`. `auto` now tries EasyOCR first, then OCR.space, then Google Vision, then Tesseract
- `EASYOCR_LANG_LIST`, `EASYOCR_USE_GPU`
  EasyOCR runtime configuration. Use comma-separated language codes such as `en` or `en,ur`
- `OCR_SPACE_API_KEY`, `OCR_SPACE_ENDPOINT`, `OCR_SPACE_LANGUAGE`, `OCR_SPACE_ENGINE`, `OCR_SPACE_TIMEOUT_SECONDS`
  OCR.space API configuration. OCR.space uses `3-letter` language codes such as `eng`, and the default endpoint is `https://api.ocr.space/parse/image`

## Database migrations

SafeChat now uses a simple in-repo migration runner.

Apply migrations manually:

```powershell
python backend\scripts\migrate.py
```

Current migration history is stored in the `schema_migrations` table.

## Backend Docker

Build:

```powershell
docker build -t safechat-backend ./backend
```

Run:

```powershell
docker run --rm -p 8000:8000 safechat-backend
```

If you need backend env overrides when using Docker:

```powershell
docker run --rm -p 8000:8000 --env-file backend/.env safechat-backend
```

## Notes

- First startup may download large model weights.
- The hybrid moderation engine can now use the checked-in `classifier/` folder as its local custom model without renaming it.
- SQLite is used for local development only.
- EasyOCR is now the recommended local OCR path for screenshot-heavy demos.
- Tesseract is now the primary OCR path for local screenshot/image uploads.
- OCR.space is available as a practical free-tier OCR option for screenshot-heavy demos.
- Google Cloud Vision remains available as an optional external OCR provider.
- Live WhatsApp monitoring depends on the separate bridge process being available.
- Default local admin credentials are `admin` / `Admin123!` unless overridden in `backend/.env`.
