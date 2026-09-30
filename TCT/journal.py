"""Local immutable observations and transactional execution index (opt-in only)."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile


class Journal:
    def __init__(self, store):
        self.root = Path(store).expanduser().resolve()
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, format_version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS calls (
                    run_id TEXT NOT NULL, step_id TEXT NOT NULL,
                    call_id TEXT NOT NULL, parent_call_id TEXT,
                    operation TEXT NOT NULL, status TEXT NOT NULL,
                    input_hash TEXT NOT NULL, event_hash TEXT,
                    PRIMARY KEY(run_id, step_id));
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.root / "journal.sqlite3", timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def artifact(self, value):
        from .interfaces.serialization import to_jsonable

        payload = json.dumps(
            to_jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        digest = hashlib.sha256(payload).hexdigest()
        destination = self.artifacts / digest
        if destination.exists():
            if destination.read_bytes() != payload:
                raise ValueError("Stored artifact checksum conflict")
            return digest
        fd, temporary = tempfile.mkstemp(dir=self.artifacts, prefix=".pending-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            directory_fd = os.open(self.artifacts, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return digest

    def begin(self, record):
        input_hash = self.artifact(record["inputs"])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO runs VALUES (?, 1)", (record["run_id"],))
            for dependency in record["depends_on"]:
                found = db.execute(
                    "SELECT status FROM calls WHERE run_id=? AND step_id=?",
                    (record["run_id"], dependency),
                ).fetchone()
                if found != ("succeeded",):
                    raise ValueError(f"Dependency is not complete: {dependency}")
            existing = db.execute(
                "SELECT status FROM calls WHERE run_id=? AND step_id=?",
                (record["run_id"], record["step_id"]),
            ).fetchone()
            if existing:
                raise ValueError(
                    f"Step already recorded ({existing[0]}); use a new step_id or inspect the journal"
                )
            db.execute(
                "INSERT INTO calls VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    record["run_id"],
                    record["step_id"],
                    record["call_id"],
                    record["parent_call_id"],
                    record["operation"],
                    "running",
                    input_hash,
                ),
            )

    def finish(self, record):
        event_hash = self.artifact(record)
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE calls SET status=?, event_hash=? WHERE run_id=? AND step_id=? AND call_id=? AND status=?",
                (
                    record["status"],
                    event_hash,
                    record["run_id"],
                    record["step_id"],
                    record["call_id"],
                    "running",
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Execution record was not running")
