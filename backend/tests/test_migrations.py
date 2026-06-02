import io
import runpy
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from sqlalchemy import create_engine, text

from backend.database.migrations import _ensure_migrations_table, run_migrations
from backend.scripts import migrate as migrate_script


class TestMigrations(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

    def tearDown(self):
        self.engine.dispose()

    def _create_legacy_tables(self):
        with self.engine.begin() as conn:
            conn.execute(text("CREATE TABLE chats (id INTEGER PRIMARY KEY, platform VARCHAR)"))
            conn.execute(text("CREATE TABLE messages (id INTEGER PRIMARY KEY, chat_id INTEGER, timestamp DATETIME)"))
            conn.execute(text("CREATE TABLE alerts (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE whatsapp_bridge_events (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE whatsapp_bridge_state_snapshots (id INTEGER PRIMARY KEY)"))

    def test_ensure_migrations_table(self):
        _ensure_migrations_table(self.engine)
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
            )
            self.assertIsNotNone(result.first())

    def test_run_migrations(self):
        self._create_legacy_tables()

        run_migrations(self.engine)

        with self.engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(chats)"))
            columns = [row[1] for row in result.fetchall()]
            self.assertIn("external_chat_id", columns)
            self.assertIn("is_live", columns)

            result = conn.execute(text("SELECT version FROM schema_migrations"))
            versions = [row[0] for row in result.fetchall()]
            self.assertIn("20260530_001_whatsapp_live_schema", versions)
            self.assertIn("20260530_002_core_database_alignment", versions)
            self.assertIn("20260530_003_whatsapp_monitor_scope", versions)
            self.assertIn("20260601_001_whatsapp_bridge_sessions", versions)

            result = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                    "('users', 'chat_participants', 'moderation_logs', 'image_scans', 'monitored_contacts')"
                )
            )
            created_tables = {row[0] for row in result.fetchall()}
            self.assertEqual(
                created_tables,
                {"users", "chat_participants", "moderation_logs", "image_scans", "monitored_contacts"},
            )

            result = conn.execute(text("PRAGMA table_info(messages)"))
            message_columns = {row[1] for row in result.fetchall()}
            self.assertIn("content", message_columns)
            self.assertIn("is_flagged", message_columns)
            self.assertIn("toxicity_score", message_columns)
            self.assertIn("direction", message_columns)
            self.assertIn("is_from_me", message_columns)

    def test_run_migrations_twice(self):
        self._create_legacy_tables()

        run_migrations(self.engine)
        run_migrations(self.engine)

        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM schema_migrations"))
            self.assertEqual(result.scalar(), 4)

    def test_migrate_main_runs_metadata_and_migrations(self):
        with patch.object(migrate_script.Base.metadata, "create_all") as create_all_mock, patch.object(
            migrate_script, "run_migrations"
        ) as run_migrations_mock, patch("sys.stdout", new_callable=io.StringIO) as stdout_mock:
            migrate_script.main()

        create_all_mock.assert_called_once_with(bind=migrate_script.engine)
        run_migrations_mock.assert_called_once_with(migrate_script.engine)
        self.assertIn("Migrations applied successfully.", stdout_mock.getvalue())

    def test_migrate_cli_entrypoint(self):
        cached_module = sys.modules.pop("backend.scripts.migrate", None)
        try:
            with patch("backend.database.config.Base.metadata.create_all") as create_all_mock, patch(
                "backend.database.migrations.run_migrations"
            ) as run_migrations_mock, io.StringIO() as buffer, redirect_stdout(buffer):
                runpy.run_module("backend.scripts.migrate", run_name="__main__")
                output = buffer.getvalue()
        finally:
            if cached_module is not None:
                sys.modules["backend.scripts.migrate"] = cached_module

        create_all_mock.assert_called_once()
        run_migrations_mock.assert_called_once()
        self.assertIn("Migrations applied successfully.", output)


if __name__ == "__main__":
    unittest.main()
