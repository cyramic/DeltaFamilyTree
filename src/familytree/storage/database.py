from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

# Ensure models are imported so SQLModel.metadata knows about every table
from familytree.domain import models as _models  # noqa: F401

DEFAULT_DB_PATH = Path("data/family.db")


def _configure_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """Enforce foreign keys and enable WAL mode on every new SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.close()


def build_engine(database_url: str | None = None) -> Engine:
    """Create a configured SQLAlchemy/SQLModel engine."""
    if database_url is None:
        DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{DEFAULT_DB_PATH}"

    # check_same_thread=False is required because NiceGUI runs UI callbacks
    # across FastAPI's event loop and background worker threads.
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}

    engine = create_engine(database_url, connect_args=connect_args)

    if database_url.startswith("sqlite"):
        event.listen(engine, "connect", _configure_sqlite_pragmas)

    return engine


# Default singleton engine for the application
engine: Engine = build_engine()


def init_db(target_engine: Engine | None = None) -> None:
    """Create all database tables if they do not already exist."""
    SQLModel.metadata.create_all(target_engine or engine)


@contextmanager
def get_session(target_engine: Engine | None = None) -> Generator[Session, None, None]:
    """Context manager yielding a transactional SQLModel session."""
    with Session(target_engine or engine, expire_on_commit=False) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise