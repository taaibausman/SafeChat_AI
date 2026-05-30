# SafeChat AI Deployment Checklist

Use this for a fresh local machine or a new server-style environment.

## 1. Install prerequisites

- Python 3.10+ is available on `PATH`
- Node.js 18+ and `npm` are available on `PATH`
- Optional: Tesseract OCR if image text extraction is needed
- Optional: Docker Desktop / Docker Engine if running the backend in a container

## 2. Prepare the repository

- Clone the repo
- Confirm the working directory is the repo root
- Review `README.md` and `backend/.env.example`

## 3. Backend setup

- Create a virtual environment:
  `python -m venv .venv`
- Activate it:
  `.\.venv\Scripts\Activate.ps1`
- Install dependencies:
  `pip install -r backend\requirements.txt`
- Copy env file if needed:
  `Copy-Item backend\.env.example backend\.env`
- Apply migrations:
  `python backend\scripts\migrate.py`

## 4. Frontend setup

- Install frontend dependencies:
  `cd frontend`
  `npm install`
- Verify production build:
  `npm.cmd run build`

## 5. WhatsApp bridge setup

- Install bridge dependencies:
  `cd whatsapp`
  `npm install`
- If bridge env management is used, configure the bridge port and auth path before start
- Start the bridge:
  `npm.cmd run dev`

## 6. Local startup

- Start backend:
  `.\backend\run_backend.ps1`
- Start frontend:
  `cd frontend`
  `npm.cmd run dev -- --host 127.0.0.1`
- Or start all windows after dependencies are installed:
  `.\run_all.ps1`

## 7. Verify backend and migrations

- Open backend health:
  `http://127.0.0.1:8000/health`
- Check operational endpoints:
  `GET /api/whatsapp/health-summary`
  `GET /api/whatsapp/bridge-ops-summary`
  `GET /api/whatsapp/ops-summary`
- Confirm the `schema_migrations` table contains the current migration version

## 8. Verify frontend

- Open the frontend dev URL shown by Vite
- Confirm dashboard loads
- Confirm live monitor loads without client errors
- Confirm admin ops page loads and refresh works

## 9. Verify bridge integration

- Confirm backend can reach the bridge control URL
- Confirm QR pairing appears when the bridge is waiting for auth
- Send a test message through a monitored chat
- Confirm live feed, alerts, and bridge history update in the UI

## 10. Optional Docker backend verification

- Build:
  `docker build -t safechat-backend ./backend`
- Run:
  `docker run --rm -p 8000:8000 --env-file backend/.env safechat-backend`
- Re-run the backend health and ops endpoint checks after container startup

## 11. Production hardening follow-ups

- Replace SQLite before multi-user or long-running production use
- Add auth/access control to admin and live-monitor endpoints
- Add structured logging and retention policy decisions
- Define bridge retry/reconnect expectations and monitoring
