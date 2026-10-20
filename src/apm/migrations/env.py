from alembic import context
from sqlalchemy import create_engine, pool

from apm.db import Base

config = context.config
connection = config.attributes.get("connection")
if connection is not None:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(config.get_main_option("sqlalchemy.url"), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
