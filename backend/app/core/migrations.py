"""Alembic helpers shared by the seed script, the startup check and tests."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config(**attributes) -> Config:
    """Return an Alembic config usable from any working directory."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["configure_logger"] = False  # keep the application's logging configuration
    cfg.attributes.update(attributes)
    return cfg


def head_revision() -> str:
    """Return the latest migration revision."""
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(engine: Engine) -> str | None:
    """Return the revision the database is at, or None."""
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def upgrade(engine: Engine, revision: str = "head") -> None:
    """Apply migrations up to `revision`."""
    with engine.begin() as conn:
        command.upgrade(alembic_config(connection=conn), revision)


def stamp(engine: Engine, revision: str = "head") -> None:
    """Mark the database as being at `revision` without running migrations."""
    with engine.begin() as conn:
        command.stamp(alembic_config(connection=conn), revision)


def schema_problem(engine: Engine) -> str | None:
    """Return None if the database is current, otherwise how to fix it."""
    import app.models  # noqa: F401  (register tables)

    tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    current, head = current_revision(engine), head_revision()
    if current == head:
        return None
    if not tables:
        return "The database is empty. Create the tables and demo data:  uv run python -m app.seed"
    if current is None:
        return (
            "The database has tables but no migration history, so it wasn't built by BatchGate's "
            "migrations. Rebuild it:  uv run python -m app.seed --reset"
        )
    script = ScriptDirectory.from_config(alembic_config())
    known = {rev.revision for rev in script.walk_revisions()}
    if current not in known:
        return (
            f"The database is at migration {current}, which this code doesn't know. "
            "It was probably upgraded by a newer version of the code."
        )
    return (
        f"The database is behind the code (at {current}, latest is {head}). "
        "Apply the new migrations (keeps your data):  uv run alembic upgrade head"
    )
