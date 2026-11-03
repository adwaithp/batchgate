"""Migrations match the models, and schema problems get clear advice.

If the models and migrations differ, run:

  uv run alembic revision --autogenerate -m "what changed"
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
import app.seed as seed_module
from app.core import migrations
from app.core.database import Base, scratch_schema


@pytest.fixture
def engine():
    """Yield an engine on an empty schema."""
    with scratch_schema("batchgate_migrations_test") as eng:
        yield eng


def _assert_matches_models(engine):
    """Fail if the migrated schema differs from the models."""
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], (
        "The models and migrations differ. Run: "
        'uv run alembic revision --autogenerate -m "what changed"\n' + "\n".join(map(str, diff))
    )
    assert migrations.current_revision(engine) == migrations.head_revision()
    assert migrations.schema_problem(engine) is None


def test_migrations_match_the_models(engine):
    migrations.upgrade(engine)
    _assert_matches_models(engine)


def test_the_test_schema_was_built_by_the_migrations(test_engine):
    _assert_matches_models(test_engine)


def test_downgrade_to_nothing_and_back(engine):
    migrations.upgrade(engine)
    migrations.upgrade(engine)  # already at head: nothing to do
    with engine.begin() as conn:
        command.downgrade(migrations.alembic_config(connection=conn), "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    migrations.upgrade(engine)
    assert "batches" in inspect(engine).get_table_names()


def test_empty_database_says_to_seed(engine):
    assert "app.seed" in migrations.schema_problem(engine)


def test_tables_without_migration_history_need_a_rebuild(engine):
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE batches (id integer primary key)"))
    assert "seed --reset" in migrations.schema_problem(engine)


def test_unknown_revision_is_reported(engine):
    migrations.upgrade(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'ffff'"))
    assert "doesn't know" in migrations.schema_problem(engine)


def test_behind_says_to_upgrade(engine):
    migrations.upgrade(engine, "0001")
    problem = migrations.schema_problem(engine)
    assert "alembic upgrade head" in problem and "keeps your data" in problem


def _run_seed(monkeypatch, engine, *args):
    """Run the seed script's main() against `engine`."""
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(
        seed_module, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False)
    )
    monkeypatch.setattr("sys.argv", ["seed", *args])
    seed_module.main()


def _qty(engine, batch_number):
    """Return a batch's quantity straight from the database."""
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT quantity FROM batches WHERE batch_number = :b"), {"b": batch_number}
        ).scalar()


def test_seed_builds_through_migrations_and_is_repeatable(monkeypatch, engine):
    _run_seed(monkeypatch, engine)
    assert migrations.schema_problem(engine) is None
    with engine.connect() as conn:
        batches = conn.execute(text("SELECT count(*) FROM batches")).scalar()
    assert batches > 0
    _run_seed(monkeypatch, engine)  # nothing duplicated
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM batches")).scalar() == batches


def test_seed_keeps_data_and_reset_starts_fresh(monkeypatch, engine):
    _run_seed(monkeypatch, engine)
    seeded = _qty(engine, "FC-2611-12")
    with engine.begin() as conn:
        conn.execute(text("UPDATE batches SET quantity = 7 WHERE batch_number = 'FC-2611-12'"))
    _run_seed(monkeypatch, engine)
    assert _qty(engine, "FC-2611-12") == 7
    _run_seed(monkeypatch, engine, "--reset")
    assert migrations.schema_problem(engine) is None
    assert _qty(engine, "FC-2611-12") == seeded != 7
