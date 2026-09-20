"""Migration credentials are explicit and separate from runtime credentials."""

import os

from alembic import context
from sqlalchemy import create_engine, pool

from app.db.schema import metadata

config = context.config
url = config.attributes.get("database_url") or os.environ.get("PLATFORM_MIGRATION_DATABASE_URL")
if not url or not url.startswith("postgresql+psycopg://"):
    raise RuntimeError("PLATFORM_MIGRATION_DATABASE_URL must explicitly select a PostgreSQL database")

if context.is_offline_mode():
    context.configure(url=url, target_metadata=metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
