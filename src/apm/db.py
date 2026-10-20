import time
import uuid
from contextlib import contextmanager

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from apm.config import Settings


def uid() -> str:
    return str(uuid.uuid4())


def now() -> int:
    return int(time.time())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[str] = mapped_column(String(16), default="observer")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    language: Mapped[str] = mapped_column(String(2), default="ru")
    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_pending: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_totp_step: Mapped[int] = mapped_column(Integer, default=0)
    recovery_hashes: Mapped[list] = mapped_column(JSON, default=list)
    oidc_subject: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    authenticated: Mapped[bool] = mapped_column(Boolean, default=True)


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    source_key: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    updated_at: Mapped[int] = mapped_column(Integer, default=now)


class Revision(Base):
    __tablename__ = "revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    snapshot: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=time.time_ns, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[int] = mapped_column(Integer, default=now)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    updated_at: Mapped[int] = mapped_column(Integer, default=now)


class State(Base):
    __tablename__ = "state"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(254))
    action: Mapped[str] = mapped_column(String(64))
    object_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[int] = mapped_column(Integer, default=now, index=True)


class Database:
    def __init__(self, config: Settings):
        config.prepare()
        self.config = config
        self.engine = create_engine(config.db_url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=30000")

        self.factory = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self):
        with self.factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def initialize(self):
        import fcntl
        from pathlib import Path

        from alembic import command
        from alembic.config import Config

        with (self.config.data_dir / "run/migrate.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            migration = Config()
            migration.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
            with self.engine.begin() as connection:
                from alembic.migration import MigrationContext
                from alembic.script import ScriptDirectory

                current = MigrationContext.configure(connection).get_current_revision()
                target = ScriptDirectory.from_config(migration).get_current_head()
                if current and current != target:
                    from apm.transfers import backup

                    backup(self, self.config, uid())
                migration.attributes["connection"] = connection
                command.upgrade(migration, "head")
        (self.config.data_dir / "apm.sqlite3").chmod(0o600)


def state_get(session: Session, key: str, default=None):
    row = session.get(State, key)
    return row.value if row else default


def state_set(session: Session, key: str, value: dict):
    row = session.get(State, key)
    if row:
        row.value = value
    else:
        session.add(State(key=key, value=value))
