# SafeChat WhatsApp Bridge

Minimal Baileys-based WhatsApp bridge for SafeChat AI.

## Setup

```powershell
cd whatsapp
npm install
copy .env.example .env
npm run dev
```

For a term-project demo, keep the bridge in shared single-account mode:

```env
SAFECHAT_WHATSAPP_SINGLE_ACCOUNT_MODE=1
SAFECHAT_WHATSAPP_DEMO_SESSION_KEY=safechat-demo
SAFECHAT_WHATSAPP_AUTO_FORWARD_ALL=1
```

## What it does

- Opens a WhatsApp Web session with QR authentication.
- Persists auth files locally under `auth/`.
- Posts connection state and QR updates to FastAPI.
- Forwards incoming WhatsApp messages to SafeChat for AI analysis.
- Exposes a tiny local control server for bridge health and restart actions.
- In single-account demo mode, reuses one shared WhatsApp session and can
  forward messages even before monitor scope is configured.

## Endpoints expected in FastAPI

- `POST /api/whatsapp/status`
- `POST /api/whatsapp/messages/incoming`

## Local control server

The bridge also exposes a local HTTP control port on `127.0.0.1:3011` by default.

- `GET /health`
- `POST /restart`
