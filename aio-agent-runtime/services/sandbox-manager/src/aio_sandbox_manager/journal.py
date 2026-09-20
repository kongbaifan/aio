"""Local manager journal: atomic claims; PostgreSQL remains the platform Run authority."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import uuid


class Journal:
    def __init__(self, root: Path):
        root = Path(root)
        if not root.is_absolute():
            raise ValueError("Manager state root must be explicit and absolute")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink():
            raise ValueError("Manager state root cannot be a symlink")
        self.root = root.resolve()
        self._owner = open(self.root / "manager.lock", "a+b")
        self._owner.seek(0)
        self._owner.write(b"0")
        self._owner.flush()
        self._owner.seek(0)
        try:
            import os

            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._owner.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._owner.close()
            raise RuntimeError("Manager state directory is already owned by another service instance") from None
        self.path = self.root / "manager.sqlite3"
        with self.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS installation(id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS cells(
              binding_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, run_id TEXT NOT NULL,
              generation INTEGER NOT NULL, slot TEXT NOT NULL, profile TEXT NOT NULL,
              spec_digest TEXT NOT NULL, spec_json TEXT NOT NULL, state TEXT NOT NULL,
              container_id TEXT, deadline REAL NOT NULL, busy INTEGER NOT NULL DEFAULT 0,
              export_json TEXT, error_code TEXT,
              UNIQUE(org_id,run_id,generation,slot));
            CREATE TABLE IF NOT EXISTS commands(
              dispatch_id TEXT PRIMARY KEY, binding_id TEXT NOT NULL,
              request_digest TEXT NOT NULL, state TEXT NOT NULL, result_json TEXT,
              FOREIGN KEY(binding_id) REFERENCES cells(binding_id));
            """)
            columns = {row["name"] for row in c.execute("PRAGMA table_info(cells)")}
            if "export_operation" not in columns:
                c.execute("ALTER TABLE cells ADD COLUMN export_operation TEXT")
            if c.execute("SELECT id FROM installation").fetchone() is None:
                c.execute("INSERT INTO installation(id) VALUES (?)", (uuid.uuid4().hex,))
            self.installation_id = c.execute("SELECT id FROM installation").fetchone()["id"]

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def cell(self, binding_id):
        with self.connect() as c:
            row = c.execute("SELECT * FROM cells WHERE binding_id=?", (str(binding_id),)).fetchone()
            return dict(row) if row else None

    def cells(self):
        with self.connect() as c:
            return [dict(row) for row in c.execute("SELECT * FROM cells")]

    def close(self):
        if not self._owner.closed:
            self._owner.close()
