"""SQLite-backed telemetry for actual IT support requests."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from uuid import uuid4


class TelemetryStore:
    """Store request outcomes without retaining prompts or response content."""

    MAX_FEEDBACK_TEXT_LENGTH = 500
    VALID_CATEGORIES = frozenset({"network", "vpn", "account", "general"})

    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS support_request_events (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL CHECK(latency_ms >= 0),
                    outcome TEXT NOT NULL CHECK(outcome IN ('agent_success', 'fallback')),
                    error_stage TEXT,
                    error_type TEXT,
                    category TEXT CHECK(
                        category IS NULL OR category IN ('network', 'vpn', 'account', 'general')
                    )
                )
                """
            )
            request_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(support_request_events)").fetchall()
            }
            if "category" not in request_columns:
                connection.execute(
                    """
                    ALTER TABLE support_request_events ADD COLUMN category TEXT CHECK(
                        category IS NULL OR category IN ('network', 'vpn', 'account', 'general')
                    )
                    """
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_support_request_events_requested_at "
                "ON support_request_events(requested_at)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS support_feedback (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE REFERENCES support_request_events(id),
                    resolution_status TEXT NOT NULL
                        CHECK(resolution_status IN ('resolved', 'not_resolved')),
                    feedback_text TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            feedback_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(support_feedback)").fetchall()
            }
            if "feedback_text" not in feedback_columns:
                connection.execute("ALTER TABLE support_feedback ADD COLUMN feedback_text TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_support_feedback_created_at "
                "ON support_feedback(created_at)"
            )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()

    def record_request(
        self,
        conversation_id: str,
        requested_at: str,
        latency_ms: int,
        outcome: str,
        error_stage: str | None = None,
        error_type: str | None = None,
        category: str | None = None,
    ) -> str:
        if outcome not in {"agent_success", "fallback"}:
            raise ValueError("outcome must be 'agent_success' or 'fallback'")
        if not isinstance(latency_ms, int) or isinstance(latency_ms, bool):
            raise TypeError("latency_ms must be an integer")
        if latency_ms < 0:
            raise ValueError("latency_ms cannot be negative")
        if category is not None and category not in self.VALID_CATEGORIES:
            raise ValueError("category must be a supported fallback category or None")
        if outcome != "fallback" and category is not None:
            raise ValueError("only fallback requests can have a category")

        event_id = str(uuid4())
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO support_request_events (
                    id, conversation_id, requested_at, completed_at, latency_ms,
                    outcome, error_stage, error_type, category
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, conversation_id, requested_at, self._timestamp(), latency_ms,
                 outcome, error_stage, error_type, category),
            )
        return event_id

    def latest_request_id(self, conversation_id: str) -> str | None:
        """Return the newest request event for a loaded conversation."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id FROM support_request_events
                WHERE conversation_id = ?
                ORDER BY requested_at DESC, completed_at DESC
                LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
        return None if row is None else row["id"]

    @classmethod
    def _normalize_feedback_text(cls, feedback_text: str | None) -> str | None:
        if feedback_text is None:
            return None
        if not isinstance(feedback_text, str):
            raise TypeError("feedback_text must be a string or None")
        normalized = feedback_text.strip()
        if not normalized:
            return None
        if len(normalized) > cls.MAX_FEEDBACK_TEXT_LENGTH:
            raise ValueError(f"feedback_text cannot exceed {cls.MAX_FEEDBACK_TEXT_LENGTH} characters")
        return normalized

    def record_feedback(
        self,
        request_id: str,
        resolution_status: str,
        feedback_text: str | None = None,
    ) -> str:
        """Persist one explicit user resolution response for a request event."""
        if resolution_status not in {"resolved", "not_resolved"}:
            raise ValueError("resolution_status must be 'resolved' or 'not_resolved'")
        feedback_text = self._normalize_feedback_text(feedback_text)

        feedback_id = str(uuid4())
        with self._connection() as connection:
            request_exists = connection.execute(
                "SELECT 1 FROM support_request_events WHERE id = ?", (request_id,)
            ).fetchone()
            if request_exists is None:
                raise ValueError("request_id does not identify a support request")
            existing_feedback = connection.execute(
                "SELECT 1 FROM support_feedback WHERE request_id = ?", (request_id,)
            ).fetchone()
            if existing_feedback is not None:
                raise ValueError("feedback has already been recorded for this request")
            try:
                connection.execute(
                    """
                    INSERT INTO support_feedback (
                        id, request_id, resolution_status, feedback_text, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (feedback_id, request_id, resolution_status, feedback_text, self._timestamp()),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("feedback has already been recorded for this request") from error
        return feedback_id

    def feedback_for_request(self, request_id: str) -> dict[str, str] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, request_id, resolution_status, feedback_text, created_at
                FROM support_feedback WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
        return None if row is None else dict(row)

    @staticmethod
    def _filter_clause(start_at: str | None) -> tuple[str, tuple[str, ...]]:
        if start_at is None:
            return "", ()
        return " WHERE requested_at >= ?", (start_at,)

    def summary(self, start_at: str | None = None) -> dict[str, int | float | None]:
        where_clause, parameters = self._filter_clause(start_at)
        with self._connection() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS total_requests,
                    COALESCE(SUM(outcome = 'agent_success'), 0) AS successful_requests,
                    COALESCE(SUM(outcome = 'fallback'), 0) AS failed_requests,
                    AVG(latency_ms) AS average_latency_ms
                FROM support_request_events{where_clause}
                """,
                parameters,
            ).fetchone()
        summary = dict(row)
        total = summary["total_requests"]
        summary["agent_success_rate"] = (
            None if not total else summary["successful_requests"] / total * 100
        )
        summary["p95_latency_ms"] = self.p95_latency_ms(start_at)
        return summary

    def p95_latency_ms(self, start_at: str | None = None) -> int | None:
        """Return nearest-rank P95 latency without requiring an analytics dependency."""
        where_clause, parameters = self._filter_clause(start_at)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT latency_ms FROM support_request_events{where_clause} ORDER BY latency_ms ASC",
                parameters,
            ).fetchall()
        if not rows:
            return None
        return rows[ceil(len(rows) * 0.95) - 1]["latency_ms"]

    def volume_by_day(self, start_at: str | None = None) -> list[dict[str, int | str]]:
        where_clause, parameters = self._filter_clause(start_at)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT substr(requested_at, 1, 10) AS day, COUNT(*) AS requests
                FROM support_request_events{where_clause} GROUP BY day ORDER BY day ASC
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def failure_breakdown(self, start_at: str | None = None) -> list[dict[str, int | float | str | None]]:
        where_clause, parameters = self._filter_clause(start_at)
        failure_clause = " WHERE outcome = 'fallback'"
        if where_clause:
            failure_clause += " AND requested_at >= ?"
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT error_stage, error_type, COUNT(*) AS errors,
                    AVG(latency_ms) AS average_response_latency_ms
                FROM support_request_events{failure_clause}
                GROUP BY error_stage, error_type ORDER BY errors DESC, error_type ASC
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def fallback_category_distribution(self, start_at: str | None = None) -> list[dict[str, int | str]]:
        """Return categories selected by local fallback troubleshooting only."""
        if start_at is None:
            where_clause, parameters = " WHERE outcome = 'fallback' AND category IS NOT NULL", ()
        else:
            where_clause = " WHERE outcome = 'fallback' AND category IS NOT NULL AND requested_at >= ?"
            parameters = (start_at,)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT category, COUNT(*) AS requests
                FROM support_request_events{where_clause}
                GROUP BY category ORDER BY requests DESC, category ASC
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def feedback_summary(self, start_at: str | None = None) -> dict[str, int | float | None]:
        """Summarize explicit feedback submitted during the selected period."""
        if start_at is None:
            where_clause, parameters = "", ()
        else:
            where_clause, parameters = " WHERE created_at >= ?", (start_at,)
        with self._connection() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS feedback_responses,
                    COALESCE(SUM(resolution_status = 'resolved'), 0) AS resolved_requests,
                    COALESCE(SUM(resolution_status = 'not_resolved'), 0) AS not_resolved_requests
                FROM support_feedback{where_clause}
                """,
                parameters,
            ).fetchone()
        summary = dict(row)
        total = summary["feedback_responses"]
        summary["user_confirmed_resolution_rate"] = (
            None if not total else summary["resolved_requests"] / total * 100
        )
        return summary
