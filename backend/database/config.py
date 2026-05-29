from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

# Use SQLite for local development MVP
SQLALCHEMY_DATABASE_URL = "sqlite:///./safechat.db"
# For PostgreSQL later, use: "postgresql://user:password@localhost/dbname"

# check_same_thread=False is needed only for SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_schema():
    inspector = inspect(engine)

    if "chats" in inspector.get_table_names():
        _ensure_columns(
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

    if "messages" in inspector.get_table_names():
        _ensure_columns(
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

    if "alerts" in inspector.get_table_names():
        _ensure_columns(
            "alerts",
            {
                "status": "VARCHAR DEFAULT 'open'",
                "notes": "TEXT",
                "acknowledged_at": "DATETIME",
                "resolved_at": "DATETIME",
            },
        )

    if "whatsapp_bridge_events" in inspector.get_table_names():
        _ensure_columns(
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

    if "whatsapp_bridge_state_snapshots" in inspector.get_table_names():
        _ensure_columns(
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

    _dedupe_live_message_ids()
    _ensure_indexes()


def _ensure_columns(table_name: str, columns: dict[str, str]):
    existing = {column["name"] for column in inspect(engine).get_columns(table_name)}
    with engine.begin() as connection:
        for name, definition in columns.items():
            if name in existing:
                continue
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"))


def _dedupe_live_message_ids():
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


def _ensure_indexes():
    statements = [
        "CREATE INDEX IF NOT EXISTS ix_chats_platform_external_chat_id ON chats (platform, external_chat_id)",
        "CREATE INDEX IF NOT EXISTS ix_chats_platform_last_message_at ON chats (platform, last_message_at)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_messages_chat_id_external_message_id ON messages (chat_id, external_message_id)",
        "CREATE INDEX IF NOT EXISTS ix_messages_chat_id_timestamp ON messages (chat_id, timestamp)",
        "CREATE INDEX IF NOT EXISTS ix_messages_source ON messages (source)",
        "CREATE INDEX IF NOT EXISTS ix_whatsapp_bridge_events_event_type_created_at ON whatsapp_bridge_events (event_type, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_whatsapp_bridge_state_snapshots_status_created_at ON whatsapp_bridge_state_snapshots (status, created_at)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
