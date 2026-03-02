import asyncio
import os
import sys

from logging.config import fileConfig
from sqlalchemy import pool, create_engine

from alembic import context

# add project root (parent of app) to path so imports work
# this ensures `import app` resolves to the package, not the
# app.py module inside the same folder.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# add your model's MetaData object here
# for "autogenerate" support
from app.models import Base  # noqa: E402

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline():
    """Run migrations in "offline" mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """

    url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in "online" mode using an async engine.

    We create an AsyncEngine and use its connection to run the migrations
    in a synchronous context by calling ``connection.run_sync``.
    """

    # determine database URL
    url = os.getenv("DATABASE_URL")
    if not url:
        section = config.get_section("sqlalchemy") or {}
        url = section.get("url")
    if not url:
        raise RuntimeError("No database URL configured for Alembic")

    # use async engine directly; alembic supports running on a sync
    # connection created by ``run_sync``
    from sqlalchemy.ext.asyncio import create_async_engine

    async_engine = create_async_engine(url, poolclass=pool.NullPool)

    # this function is synchronous because connection.run_sync
    # will run it in the context of the sync Engine
    def do_run_migrations(connection):
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    async def run_async():
        async with async_engine.connect() as connection:
            # run_sync takes a callable and returns its result (sync)
            await connection.run_sync(do_run_migrations)

    # run the async routine
    asyncio.run(run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
