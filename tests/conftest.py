"""Shared test isolation.

Every test module points `DATABASE_URL` at the same in-memory SQLite DB, and
`models.py` pins it to a `StaticPool` so worker threads all see one schema.
That makes the DB genuinely shared for the whole pytest session, so rows left
by one module collide with another module's primary keys. Reset per test here,
once, rather than trusting every module to remember.

Module-level fixtures still run after this one, so per-file setup that seeds a
device keeps working.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from server.db import models as m  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    m.init_db()
    with m.SessionLocal() as db:
        for table in (m.HistoryRecord, m.Patch, m.Event, m.Device):
            db.query(table).delete()
        db.commit()
    yield
