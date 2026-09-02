import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from truss_api.core.settings import Settings, get_settings
from truss_api.core.storage import ensure_storage_layout


def connect(settings: Settings | None = None) -> sqlite3.Connection:
    resolved = settings or get_settings()
    ensure_storage_layout(resolved)
    connection = sqlite3.connect(resolved.database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


@contextmanager
def transaction(settings: Settings | None = None) -> Iterator[sqlite3.Connection]:
    connection = connect(settings)

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
