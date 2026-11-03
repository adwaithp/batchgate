"""Database engine, sessions and the startup schema check."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

# Named constraints let migrations drop or alter them by name.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base with named constraints."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_engine(schema: str | None = None):
    """Create an engine for the configured database, optionally on `schema`."""
    settings = get_settings()
    schema = schema or settings.db_schema
    connect_args = {"options": f"-csearch_path={schema}"} if schema else {}
    return create_engine(settings.sqlalchemy_url, pool_pre_ping=True, connect_args=connect_args)


@contextmanager
def scratch_schema(name: str) -> Iterator[Engine]:
    """Yield an engine on a fresh schema and drop the schema afterwards."""
    admin = make_engine("public")
    with admin.begin() as conn:
        conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{name}" CASCADE; CREATE SCHEMA "{name}"')
    engine = make_engine(name)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        admin.dispose()


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a session for one request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SchemaOutOfDateError(RuntimeError):
    """The database is not at the latest migration."""


def check_schema() -> None:
    """Raise SchemaOutOfDateError, with the fix, unless the database is current."""
    from app.core.migrations import schema_problem

    if not get_settings().check_schema_on_start:
        return
    if problem := schema_problem(engine):
        raise SchemaOutOfDateError(problem)
