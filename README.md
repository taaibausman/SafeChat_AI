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
- Optional: Tesseract OCR for image extraction
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
- SQLite is used for local development only.
- Tesseract is required for OCR-heavy image workflows.
- Live WhatsApp monitoring depends on the separate bridge process being available.
