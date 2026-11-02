from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SchemaOutOfDate(RuntimeError):
    pass


def check_schema() -> None:
    """Fail at startup, with the fix spelled out, if the database predates the models.

    Until migrations are added, the demo database is rebuilt instead of migrated.
    """
    from sqlalchemy import inspect

    import app.models  # noqa: F401  (register tables)

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    if not existing:
        return  # empty database: the seed script creates everything
    problems = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            problems.append(f"table {table.name}")
            continue
        columns = {c["name"] for c in inspector.get_columns(table.name)}
        problems += [f"{table.name}.{c.name}" for c in table.columns if c.name not in columns]
    if problems:
        raise SchemaOutOfDate(
            "The database is older than the code (missing: "
            + ", ".join(problems[:5])
            + (", ..." if len(problems) > 5 else "")
            + "). Rebuild the demo data:  uv run python -m app.seed --reset"
        )
