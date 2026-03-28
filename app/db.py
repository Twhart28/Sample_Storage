from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./freezer.db"
DATABASE_URL = os.getenv("SAMPLE_STORAGE_DATABASE_URL", DEFAULT_DATABASE_URL)
engine = None
SessionLocal = None


def configure(database_url: str | None = None) -> None:
    global DATABASE_URL, engine, SessionLocal

    DATABASE_URL = database_url or os.getenv(
        "SAMPLE_STORAGE_DATABASE_URL", DEFAULT_DATABASE_URL
    )
    connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


configure()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
