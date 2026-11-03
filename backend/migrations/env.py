"""Alembic environment, using the application's settings and models."""

from logging.config import fileConfig

from alembic import context

import app.models  # noqa: F401  (register every table on Base.metadata)
from app.core.config import get_settings
from app.core.database import Base, make_engine

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
OPTIONS = {"target_metadata": target_metadata, "compare_type": True}


def run_migrations_offline() -> None:
    """Emit SQL instead of running it (alembic upgrade head --sql)."""
    url = get_settings().sqlalchemy_url
    url = url.render_as_string(hide_password=False) if hasattr(url, "render_as_string") else url
    context.configure(url=url, literal_binds=True, **OPTIONS)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # the seed script and tests may pass an open connection
    """Run migrations on a passed-in connection or a new engine."""
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, **OPTIONS)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = make_engine()
    with engine.connect() as conn:
        context.configure(connection=conn, **OPTIONS)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
