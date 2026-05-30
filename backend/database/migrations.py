from collections.abc import Callable

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


MigrationFunc = Callable[[Engine], None]


def run_migrations(engine: Engine) -> None:
    _ensure_migrations_table(engine)
    for version, migration in MIGRATIONS:
        if _is_applied(engine, version):
            continue
        migration(engine)
        _mark_applied(engine, version)


def _ensure_migrations_table(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )


def _is_applied(engine: Engine, version: str) -> bool:
    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT version FROM schema_migrations WHERE version = :version"),
            {"version": version},
        ).first()
    return row is not None


def _mark_applied(engine: Engine, version: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO schema_migrations (version) VALUES (:version)"),
            {"version": version},
        )


def _has_table(engine: Engine, table_name: str) -> bool:
    return table_name in inspect(engine).get_table_names()


def _create_table_if_missing(engine: Engine, table_name: str, ddl: str) -> None:
    if _has_table(engine, table_name):
        return
    with engine.begin() as connection:
        connection.execute(text(ddl))


def _ensure_columns(engine: Engine, table_name: str, columns: dict[str, str]) -> None:
    existing = {column["name"] for column in inspect(engine).get_columns(table_name)}
    with engine.begin() as connection:
        for name, definition in columns.items():
            if name in existing:
                continue
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"))


def _dedupe_live_message_ids(engine: Engine) -> None:
    if not _has_table(engine, "messages"):
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                DELETE FROM messages
                WHERE id IN (
                    SELECT duplicate.id
                    FROM messages AS duplicate
                    JOIN messages AS keeper
                      ON keeper.chat_id = duplicate.chat_id
                     AND keeper.external_message_id = duplicate.external_message_id
                     AND keeper.id < duplicate.id
                    WHERE duplicate.external_message_id IS NOT NULL
                )
                """
            )
        )


def _backfill_message_columns(engine: Engine) -> None:
    if not _has_table(engine, "messages"):
        return
    existing = {column["name"] for column in inspect(engine).get_columns("messages")}
    content_source = "message" if "message" in existing else "content"
    score_source = "risk_score" if "risk_score" in existing else "toxicity_score"
    with engine.begin() as connection:
        connection.execute(
            text(
                f"""
                UPDATE messages
                SET content = COALESCE(content, {content_source}),
                    toxicity_score = COALESCE(toxicity_score, {score_source}),
                    is_flagged = CASE
                        WHEN is_flagged IS NULL AND COALESCE({score_source}, 0) > 50 THEN 1
                        WHEN is_flagged IS NULL THEN 0
                        ELSE is_flagged
                    END
                """
            )
        )


def _ensure_indexes(engine: Engine, statements: list[str]) -> None:
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _migration_20260530_001_whatsapp_live_schema(engine: Engine) -> None:
    if _has_table(engine, "chats"):
        _ensure_columns(
            engine,
            "chats",
            {
                "external_chat_id": "VARCHAR",
                "chat_type": "VARCHAR",
                "is_live": "BOOLEAN DEFAULT 0",
                "message_count": "INTEGER DEFAULT 0",
                "flagged_message_count": "INTEGER DEFAULT 0",
                "last_message_at": "DATETIME",
            },
        )

    if _has_table(engine, "messages"):
        _ensure_columns(
            engine,
            "messages",
            {
                "sender_id": "VARCHAR",
                "sender_name": "VARCHAR",
                "external_message_id": "VARCHAR",
                "source": "VARCHAR",
                "raw_payload": "TEXT",
                "created_at": "DATETIME",
            },
        )

    if _has_table(engine, "alerts"):
        _ensure_columns(
            engine,
            "alerts",
            {
                "status": "VARCHAR DEFAULT 'open'",
                "notes": "TEXT",
                "acknowledged_at": "DATETIME",
                "resolved_at": "DATETIME",
            },
        )

    if _has_table(engine, "whatsapp_bridge_events"):
        _ensure_columns(
            engine,
            "whatsapp_bridge_events",
            {
                "event_type": "VARCHAR",
                "status": "VARCHAR",
                "detail": "VARCHAR",
                "connected_phone": "VARCHAR",
                "bridge_reachable": "BOOLEAN",
                "payload": "TEXT",
                "created_at": "DATETIME",
            },
        )

    if _has_table(engine, "whatsapp_bridge_state_snapshots"):
        _ensure_columns(
            engine,
            "whatsapp_bridge_state_snapshots",
            {
                "status": "VARCHAR",
                "reason": "VARCHAR",
                "connected_phone": "VARCHAR",
                "bridge_status": "VARCHAR",
                "bridge_detail": "VARCHAR",
                "bridge_reachable": "BOOLEAN",
                "qr_present": "BOOLEAN DEFAULT 0",
                "created_at": "DATETIME",
            },
        )

    _dedupe_live_message_ids(engine)
    _ensure_indexes(
        engine,
        [
            "CREATE INDEX IF NOT EXISTS ix_chats_platform_external_chat_id ON chats (platform, external_chat_id)",
            "CREATE INDEX IF NOT EXISTS ix_chats_platform_last_message_at ON chats (platform, last_message_at)",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_messages_chat_id_external_message_id ON messages (chat_id, external_message_id)",
            "CREATE INDEX IF NOT EXISTS ix_messages_chat_id_timestamp ON messages (chat_id, timestamp)",
            "CREATE INDEX IF NOT EXISTS ix_messages_source ON messages (source)",
            "CREATE INDEX IF NOT EXISTS ix_whatsapp_bridge_events_event_type_created_at ON whatsapp_bridge_events (event_type, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_whatsapp_bridge_state_snapshots_status_created_at ON whatsapp_bridge_state_snapshots (status, created_at)",
        ],
    )


def _migration_20260530_002_core_database_alignment(engine: Engine) -> None:
    _create_table_if_missing(
        engine,
        "users",
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username VARCHAR UNIQUE,
            email VARCHAR NOT NULL UNIQUE,
            password_hash VARCHAR,
            role VARCHAR DEFAULT 'user',
            is_active BOOLEAN DEFAULT 1,
            firebase_uid VARCHAR UNIQUE,
            name VARCHAR,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    _ensure_columns(
        engine,
        "users",
        {
            "username": "VARCHAR",
            "password_hash": "VARCHAR",
            "role": "VARCHAR DEFAULT 'user'",
            "is_active": "BOOLEAN DEFAULT 1",
            "firebase_uid": "VARCHAR",
            "name": "VARCHAR",
            "created_at": "DATETIME",
        },
    )

    _create_table_if_missing(
        engine,
        "chat_participants",
        """
        CREATE TABLE chat_participants (
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, chat_id),
            FOREIGN KEY(user_id) REFERENCES users (id),
            FOREIGN KEY(chat_id) REFERENCES chats (id)
        )
        """,
    )

    if _has_table(engine, "chats"):
        _ensure_columns(
            engine,
            "chats",
            {
                "user_id": "INTEGER",
                "is_active": "BOOLEAN DEFAULT 1",
                "created_at": "DATETIME",
            },
        )

    if _has_table(engine, "messages"):
        _ensure_columns(
            engine,
            "messages",
            {
                "sender_user_id": "INTEGER",
                "content": "TEXT",
                "is_flagged": "BOOLEAN DEFAULT 0",
                "toxicity_score": "FLOAT",
            },
        )
        _backfill_message_columns(engine)

    _create_table_if_missing(
        engine,
        "moderation_logs",
        """
        CREATE TABLE moderation_logs (
            id INTEGER PRIMARY KEY,
            message_id INTEGER NOT NULL,
            toxic FLOAT DEFAULT 0,
            severe_toxic FLOAT DEFAULT 0,
            obscene FLOAT DEFAULT 0,
            threat FLOAT DEFAULT 0,
            insult FLOAT DEFAULT 0,
            identity_hate FLOAT DEFAULT 0,
            action VARCHAR DEFAULT 'allow',
            reviewed_by INTEGER,
            reviewed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(message_id) REFERENCES messages (id),
            FOREIGN KEY(reviewed_by) REFERENCES users (id)
        )
        """,
    )

    _create_table_if_missing(
        engine,
        "image_scans",
        """
        CREATE TABLE image_scans (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            file_path VARCHAR NOT NULL,
            ocr_text TEXT,
            is_flagged BOOLEAN DEFAULT 0,
            toxicity_score FLOAT,
            scan_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users (id)
        )
        """,
    )

    _ensure_indexes(
        engine,
        [
            "CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)",
            "CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)",
            "CREATE INDEX IF NOT EXISTS ix_messages_sender_user_id ON messages (sender_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_moderation_logs_message_id ON moderation_logs (message_id)",
            "CREATE INDEX IF NOT EXISTS ix_moderation_logs_reviewed_by ON moderation_logs (reviewed_by)",
            "CREATE INDEX IF NOT EXISTS ix_image_scans_user_id ON image_scans (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_image_scans_scan_time ON image_scans (scan_time)",
        ],
    )


def _migration_20260530_003_whatsapp_monitor_scope(engine: Engine) -> None:
    if _has_table(engine, "messages"):
        _ensure_columns(
            engine,
            "messages",
            {
                "direction": "VARCHAR",
                "is_from_me": "BOOLEAN DEFAULT 0",
            },
        )

    _create_table_if_missing(
        engine,
        "monitored_contacts",
        """
        CREATE TABLE monitored_contacts (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            contact_name VARCHAR NOT NULL,
            phone_number VARCHAR,
            chat_key VARCHAR,
            chat_type VARCHAR DEFAULT 'direct',
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users (id)
        )
        """,
    )
    _ensure_columns(
        engine,
        "monitored_contacts",
        {
            "phone_number": "VARCHAR",
            "chat_key": "VARCHAR",
            "chat_type": "VARCHAR DEFAULT 'direct'",
            "is_active": "BOOLEAN DEFAULT 1",
            "created_at": "DATETIME",
        },
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE monitored_contacts
                SET chat_key = COALESCE(chat_key, phone_number),
                    phone_number = COALESCE(phone_number, chat_key),
                    chat_type = COALESCE(chat_type, 'direct'),
                    created_at = COALESCE(created_at, CURRENT_TIMESTAMP)
                """
            )
        )

    _ensure_indexes(
        engine,
        [
            "CREATE INDEX IF NOT EXISTS ix_monitored_contacts_user_id_is_active ON monitored_contacts (user_id, is_active)",
            "CREATE INDEX IF NOT EXISTS ix_monitored_contacts_chat_key ON monitored_contacts (chat_key)",
        ],
    )


MIGRATIONS: list[tuple[str, MigrationFunc]] = [
    ("20260530_001_whatsapp_live_schema", _migration_20260530_001_whatsapp_live_schema),
    ("20260530_002_core_database_alignment", _migration_20260530_002_core_database_alignment),
    ("20260530_003_whatsapp_monitor_scope", _migration_20260530_003_whatsapp_monitor_scope),
]
