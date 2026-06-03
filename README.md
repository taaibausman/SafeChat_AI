# SafeChat AI

SafeChat AI is a full-stack content moderation platform for analyzing chat conversations from three sources:

- exported chat logs
- OCR-extracted text from screenshots/images
- live WhatsApp messages through a local bridge

The project combines a React frontend, a FastAPI backend, a local moderation engine, OCR pipelines, and a Node.js WhatsApp relay. It is designed as a local prototype/demo environment for academic work, experimentation, moderation workflows, and safe-messaging analysis.

## What The Project Does

SafeChat AI supports these main workflows:

1. Upload a WhatsApp `.txt` export and generate a moderation report.
2. Upload a screenshot/image and extract chat text using OCR, then score the extracted messages.
3. Connect a live WhatsApp bridge and monitor incoming messages in near real time.
4. Review message-level risk labels, chat summaries, alerts, and operational system status.
5. Re-score older saved chats when moderation rules or model behavior changes.

## Core Features

### Chat Export Analysis

- parses WhatsApp-style `.txt` exports
- scores each message individually
- stores analysis results in the local database
- shows flagged messages, safe/unsafe ratios, and average risk score

### OCR Image Analysis

- accepts image uploads such as screenshots
- supports `tesseract`, `easyocr`, `ocr.space`, `google`, and `auto` OCR modes
- segments OCR output into likely message lines
- runs moderation on extracted messages

### Live WhatsApp Monitoring

- uses a local Node.js relay/bridge
- shows chat directory, monitored contacts, live feed, and alerts
- tracks bridge health, QR status, connection state, and operations summary

### Hybrid Moderation Engine

- uses a local classifier from `classifier/` or `best_model/`
- optionally uses Detoxify for toxicity signals
- applies rule-based heuristics for threats, scams, abuse, blackmail, self-harm, distress, and sexual harassment
- includes stronger Roman Urdu coverage and false-positive reduction for harmless short chat phrases
- supports context reduction for examples/testing/educational wording

### Roman Urdu Rule System

- moderation phrases are stored in a JSON config file
- rules are loaded and compiled once at startup
- easier to maintain than hardcoded phrase lists
- safer to expand over time with real chat examples

### Rescoring Existing Data

- saved chats/messages can be rescored with the latest moderation logic
- useful after updating heuristics or model behavior
- prevents old incorrect scores from remaining in reports

### Frontend Workspace

- dashboard for summaries and system state
- analyze pages for text export and OCR image uploads
- results/report views for saved analyses
- live monitor page for WhatsApp bridge monitoring
- admin/system-health pages
- compacted layout so more information fits on one screen

## Technology Stack

### Frontend

- React
- TypeScript
- Vite
- React Router
- Tailwind-based styling

### Backend

- Python 3.10+
- FastAPI
- SQLAlchemy
- SQLite for local development

### AI / Moderation

- local Hugging Face-style text classifier in `classifier/`
- optional Detoxify toxicity model
- JSON-driven Roman Urdu moderation rules

### OCR

- Tesseract OCR
- EasyOCR
- OCR.space
- Google Cloud Vision

### Live Bridge

- Node.js
- WhatsApp Web relay logic
- Socket / HTTP control integration with backend

## High-Level Architecture

### Frontend

The frontend provides user flows for:

- login/register
- upload-based moderation
- OCR moderation
- reports and results
- live monitoring
- settings and admin operations

### Backend

The backend exposes routes under modules such as:

- `backend/api/chat_analyzer.py`
- `backend/api/image_analyzer.py`
- `backend/api/moderation.py`
- `backend/api/messages.py`
- `backend/api/whatsapp.py`
- `backend/api/auth.py`
- `backend/api/users.py`
- `backend/api/realtime.py`

### Moderation Engine

The moderation engine lives in:

- `backend/ai/engine.py`
- `backend/ai/rule_loader.py`
- `backend/config/roman_urdu_moderation_rules.json`

It combines:

- binary classifier score
- optional toxicity score
- rule-based phrase matching
- token-based weak signals
- context softening
- severity/action mapping

### Database

Main domain models include:

- `User`
- `Chat`
- `Message`
- `AnalysisResult`
- `Alert`
- `ModerationLog`
- `ImageScan`
- `MonitoredContact`
- WhatsApp bridge state/event tables

### Live WhatsApp Bridge

The bridge is implemented in:

- `whatsapp/src/index.js`
- `whatsapp/src/config.js`
- `whatsapp/src/message-normalizer.js`

It handles:

- local auth/session state
- QR-based pairing
- incoming message normalization
- control API for backend status checks

## Project Structure

```text
SafeChat_AI/
|-- backend/
|   |-- ai/
|   |-- api/
|   |-- config/
|   |-- database/
|   |-- models/
|   |-- schemas/
|   |-- scripts/
|   `-- tests/
|-- frontend/
|   |-- src/
|   |   |-- lib/
|   |   `-- pages/
|-- whatsapp/
|   `-- src/
|-- classifier/
|-- run_all.ps1
|-- sample_test_chat_mixed_en_roman_urdu.txt
|-- sample_test_chat_safe_roman_urdu.txt
|-- sample_test_chat_abuse_threat_roman_urdu.txt
`-- sample_test_chat_scam_distress_roman_urdu.txt
```

## Setup

## Prerequisites

- Python 3.10+
- Node.js 18+
- Git
- Tesseract OCR for local image OCR

Optional:

- EasyOCR
- OCR.space API key
- Google Cloud Vision credentials
- Docker

## Backend Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
python backend\scripts\migrate.py
```

Run backend:

```powershell
.\backend\run_backend.ps1
```

Manual equivalent:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

## WhatsApp Bridge Setup

```powershell
cd whatsapp
copy .env.example .env
npm install
npm run dev
```

## Start Everything

After dependencies are installed:

```powershell
.\run_all.ps1
```

This starts:

- backend on `127.0.0.1:8000`
- frontend on Vite dev server
- WhatsApp bridge on its local control port

## Default Local Access

- Frontend: `http://127.0.0.1:5173`
- Backend docs: `http://127.0.0.1:8000/docs`

Default admin credentials depend on `backend/.env`. Common local default:

- username: `admin`
- password: `change-me`

## Environment Variables

Backend config examples are in `backend/.env.example`.

Important variables:

- `SAFECHAT_DISABLE_MODELS`
- `SAFECHAT_CUSTOM_MODEL_PATH`
- `SAFECHAT_FLAG_THRESHOLD`
- `SAFECHAT_BLOCK_THRESHOLD`
- `SAFECHAT_CREATE_DEFAULT_ADMIN`
- `SAFECHAT_DEFAULT_ADMIN_USERNAME`
- `SAFECHAT_DEFAULT_ADMIN_EMAIL`
- `SAFECHAT_DEFAULT_ADMIN_PASSWORD`
- `SAFECHAT_OCR_PROVIDER`
- `EASYOCR_LANG_LIST`
- `EASYOCR_USE_GPU`
- `OCR_SPACE_API_KEY`
- `OCR_SPACE_ENDPOINT`
- `OCR_SPACE_LANGUAGE`
- `OCR_SPACE_ENGINE`
- `OCR_SPACE_TIMEOUT_SECONDS`
- `WHATSAPP_BRIDGE_CONTROL_URL`
- `WHATSAPP_BRIDGE_EVENT_RETENTION`
- `WHATSAPP_BRIDGE_STATE_SNAPSHOT_RETENTION`

## Moderation Logic

The moderation engine now supports a broader Roman Urdu rule set and safer behavior for harmless conversation.

### Unsafe Categories Covered

- threats and violence
- abuse and insults
- harassment/stalking
- blackmail/extortion
- scams/fraud
- sexual harassment
- self-harm encouragement
- self-harm distress/escalation

### Safe/Context Handling

The engine reduces risk when messages are clearly:

- examples
- assignments
- moderation tests
- educational explanations
- short harmless chat phrases

Examples that should remain safe:

- `kahan ho`
- `kesi ho`
- `how are you`
- `what are you doing`
- `how are yoy`

## OCR Pipeline Notes

OCR extraction lives mainly in `backend/api/image_analyzer.py`.

Highlights:

- image preprocessing before OCR
- OCR line filtering to remove UI noise
- message segmentation from OCR text
- fallback chain in `auto` mode
- moderation applied after OCR extraction

Supported providers:

- `tesseract`
- `easyocr`
- `ocrspace`
- `google`
- `auto`

## Live WhatsApp Monitoring Notes

The live bridge integration supports:

- QR pairing
- bridge state snapshots
- bridge event history
- monitored contacts
- live chat summaries
- live alerts
- real-time websocket updates

Useful backend operational endpoints:

- `GET /api/whatsapp/health-summary`
- `GET /api/whatsapp/bridge-ops-summary`
- `GET /api/whatsapp/ops-summary`
- `GET /api/whatsapp/summary`

## Testing

Backend tests include:

- AI-engine moderation logic
- OCR behavior
- moderation endpoints
- WhatsApp live-monitoring flows
- database/migration checks

Run targeted backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_ai_engine.py -q
```

Run broader tests:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Frontend build check:

```powershell
cd frontend
npm.cmd run build
```

## Sample Test Files

Use these for quick moderation checks:

- `sample_test_chat_mixed_en_roman_urdu.txt`
- `sample_test_chat_safe_roman_urdu.txt`
- `sample_test_chat_abuse_threat_roman_urdu.txt`
- `sample_test_chat_scam_distress_roman_urdu.txt`

These files help verify:

- harmless Roman Urdu conversation
- abuse/threat detection
- scam detection
- distress/self-harm escalation behavior

## Rescoring Existing Chats

If saved messages were scored before moderation fixes, rescore them:

Specific chat by name:

```powershell
.\.venv\Scripts\python.exe backend\scripts\rescore_messages.py --chat-name "120363409506309279"
```

Specific chat by id:

```powershell
.\.venv\Scripts\python.exe backend\scripts\rescore_messages.py --chat-id 12
```

All chats:

```powershell
.\.venv\Scripts\python.exe backend\scripts\rescore_messages.py
```

This updates:

- message risk scores
- labels
- flagged state
- moderation logs
- alerts
- chat summaries
- analysis results

## Operational Notes

- first startup may download model weights
- the checked-in `classifier/` directory is used automatically when available
- SQLite is intended for local development/demo use
- WhatsApp live monitoring depends on the separate bridge process
- OCR quality depends heavily on image quality and provider choice

## Troubleshooting

### Backend starts but classifications look outdated

Restart the backend so new moderation rules are loaded.

### UI still shows old incorrect labels

Rescore saved chats using:

```powershell
.\.venv\Scripts\python.exe backend\scripts\rescore_messages.py
```

### OCR extracts poor text

Try:

- better quality screenshots
- different OCR provider
- `SAFECHAT_OCR_PROVIDER=auto`

### Tesseract not found

Install Tesseract OCR and ensure it is on PATH, or place it at the expected Windows path.

### Frontend build command fails in PowerShell

Use:

```powershell
npm.cmd run build
```

instead of `npm run build` if execution policy blocks PowerShell script wrappers.

## Supporting Documents

- [DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md)
- [MANUAL_QA_CHECKLIST.md](./MANUAL_QA_CHECKLIST.md)
- [SUBMISSION_PREP.md](./SUBMISSION_PREP.md)

## Current State Summary

At the current stage, SafeChat AI includes:

- export analysis
- OCR moderation
- live WhatsApp monitoring
- Roman Urdu rule-based moderation
- JSON-driven rule configuration
- rescoring support for saved data
- improved frontend density and usability
- focused backend regression tests

This makes the project more accurate, more maintainable, and more suitable for demonstration/report submission than the earlier prototype state.
