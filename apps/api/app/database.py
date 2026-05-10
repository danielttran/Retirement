from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TEXT, TypeDecorator

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = REPO_ROOT / "retirement.db"
DATABASE_PATH = Path(os.environ.get("RETIREMENT_DATABASE_PATH", DEFAULT_DATABASE_PATH)).resolve()
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"


class Base(DeclarativeBase):
    pass


class Money(TypeDecorator[Decimal]):
    impl = TEXT
    cache_ok = True

    def process_bind_param(self, value: Decimal | int | str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return str(Decimal(value))

    def process_result_value(self, value: str | None, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value)


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.touch(exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
