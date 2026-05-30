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


MIGRATIONS: list[tuple[str, MigrationFunc]] = [
    ("20260530_001_whatsapp_live_schema", _migration_20260530_001_whatsapp_live_schema),
]
