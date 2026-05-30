# SafeChat AI PostgreSQL Schema

This schema is the production-oriented PostgreSQL design that matches the current SQLAlchemy domain model and moderation flows.

## Core Tables

### `users`
- `id BIGSERIAL PRIMARY KEY`
- `username VARCHAR(150) UNIQUE`
- `email VARCHAR(255) NOT NULL UNIQUE`
- `password_hash TEXT`
- `role VARCHAR(32) NOT NULL DEFAULT 'user'`
- `is_active BOOLEAN NOT NULL DEFAULT TRUE`
- `firebase_uid VARCHAR(255) UNIQUE`
- `name VARCHAR(255)`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

### `chats`
- `id BIGSERIAL PRIMARY KEY`
- `user_id BIGINT REFERENCES users(id) ON DELETE SET NULL`
- `platform VARCHAR(64) NOT NULL`
- `chat_name VARCHAR(255) NOT NULL`
- `external_chat_id VARCHAR(255)`
- `chat_type VARCHAR(32)`
- `is_live BOOLEAN NOT NULL DEFAULT FALSE`
- `is_active BOOLEAN NOT NULL DEFAULT TRUE`
- `message_count INTEGER NOT NULL DEFAULT 0`
- `flagged_message_count INTEGER NOT NULL DEFAULT 0`
- `last_message_at TIMESTAMPTZ`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Indexes:
- `(platform, external_chat_id)`
- `(platform, last_message_at DESC)`

### `chat_participants`
- `user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE`
- `chat_id BIGINT NOT NULL REFERENCES chats(id) ON DELETE CASCADE`
- `joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- Primary key `(user_id, chat_id)`

### `messages`
- `id BIGSERIAL PRIMARY KEY`
- `chat_id BIGINT NOT NULL REFERENCES chats(id) ON DELETE CASCADE`
- `sender VARCHAR(255) NOT NULL`
- `sender_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL`
- `sender_id VARCHAR(255)`
- `sender_name VARCHAR(255)`
- `message TEXT NOT NULL`
- `content TEXT`
- `external_message_id VARCHAR(255)`
- `source VARCHAR(64)`
- `direction VARCHAR(32)`
- `is_from_me BOOLEAN NOT NULL DEFAULT FALSE`
- `raw_payload JSONB`
- `timestamp TIMESTAMPTZ`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `risk_score DOUBLE PRECISION`
- `toxicity_score DOUBLE PRECISION`
- `is_flagged BOOLEAN NOT NULL DEFAULT FALSE`
- `label VARCHAR(64)`

Indexes:
- Unique `(chat_id, external_message_id)` where `external_message_id IS NOT NULL`
- `(chat_id, timestamp DESC)`
- `(sender_user_id)`
- `(source)`

### `moderation_logs`
- `id BIGSERIAL PRIMARY KEY`
- `message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE`
- `toxic DOUBLE PRECISION NOT NULL DEFAULT 0`
- `severe_toxic DOUBLE PRECISION NOT NULL DEFAULT 0`
- `obscene DOUBLE PRECISION NOT NULL DEFAULT 0`
- `threat DOUBLE PRECISION NOT NULL DEFAULT 0`
- `insult DOUBLE PRECISION NOT NULL DEFAULT 0`
- `identity_hate DOUBLE PRECISION NOT NULL DEFAULT 0`
- `action VARCHAR(32) NOT NULL DEFAULT 'allow'`
- `reviewed_by BIGINT REFERENCES users(id) ON DELETE SET NULL`
- `reviewed_at TIMESTAMPTZ`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Indexes:
- `(message_id)`
- `(reviewed_by)`

### `alerts`
- `id BIGSERIAL PRIMARY KEY`
- `message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE`
- `alert_type VARCHAR(64) NOT NULL`
- `severity VARCHAR(32) NOT NULL`
- `status VARCHAR(32) NOT NULL DEFAULT 'open'`
- `notes TEXT`
- `acknowledged_at TIMESTAMPTZ`
- `resolved_at TIMESTAMPTZ`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

### `image_scans`
- `id BIGSERIAL PRIMARY KEY`
- `user_id BIGINT REFERENCES users(id) ON DELETE SET NULL`
- `file_path VARCHAR(255) NOT NULL`
- `ocr_text TEXT`
- `is_flagged BOOLEAN NOT NULL DEFAULT FALSE`
- `toxicity_score DOUBLE PRECISION`
- `scan_time TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Indexes:
- `(user_id)`
- `(scan_time DESC)`

### `monitored_contacts`
- `id BIGSERIAL PRIMARY KEY`
- `user_id BIGINT REFERENCES users(id) ON DELETE SET NULL`
- `contact_name VARCHAR(255) NOT NULL`
- `phone_number VARCHAR(255)`
- `chat_key VARCHAR(255)`
- `chat_type VARCHAR(32) DEFAULT 'direct'`
- `is_active BOOLEAN NOT NULL DEFAULT TRUE`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Indexes:
- `(user_id, is_active)`
- `(chat_key)`

### `analysis_results`
- `id BIGSERIAL PRIMARY KEY`
- `chat_id BIGINT NOT NULL UNIQUE REFERENCES chats(id) ON DELETE CASCADE`
- `overall_score DOUBLE PRECISION NOT NULL`
- `safe_percentage DOUBLE PRECISION NOT NULL`
- `unsafe_percentage DOUBLE PRECISION NOT NULL`
- `summary TEXT NOT NULL`

## Operational Tables

### `whatsapp_bridge_state`
- single-row state table for latest bridge status, QR, reachability, and timestamps

### `whatsapp_bridge_events`
- append-only bridge event history

### `whatsapp_bridge_state_snapshots`
- append-only state snapshots for diagnostics and ops history

## Threshold Policy

Recommended moderation thresholds:
- `allow`: `< 55`
- `flag`: `>= 55` and `< 85`
- `block`: `>= 85`

These are configurable in runtime with:
- `SAFECHAT_FLAG_THRESHOLD`
- `SAFECHAT_BLOCK_THRESHOLD`
