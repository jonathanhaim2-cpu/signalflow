from collections.abc import AsyncGenerator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_async_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


def _existing_columns(sync_conn, table: str) -> set[str]:
    inspector = inspect(sync_conn)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def _add_missing_columns(sync_conn) -> None:
    dialect = sync_conn.dialect.name
    datetime_type = "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME"
    json_type = "JSON" if dialect == "postgresql" else "TEXT"

    user_cols = _existing_columns(sync_conn, "users")
    if user_cols and "upgrade_requested_at" not in user_cols:
        sync_conn.execute(text(f"ALTER TABLE users ADD COLUMN upgrade_requested_at {datetime_type}"))
    if user_cols and "tier" not in user_cols:
        sync_conn.execute(text("ALTER TABLE users ADD COLUMN tier VARCHAR(20) DEFAULT 'free'"))
    bool_type = "BOOLEAN DEFAULT FALSE" if dialect == "postgresql" else "BOOLEAN DEFAULT 0"
    if user_cols and "is_admin" not in user_cols:
        sync_conn.execute(text(f"ALTER TABLE users ADD COLUMN is_admin {bool_type}"))
    if user_cols and "is_disabled" not in user_cols:
        sync_conn.execute(text(f"ALTER TABLE users ADD COLUMN is_disabled {bool_type}"))

    endpoint_cols = _existing_columns(sync_conn, "webhook_endpoints")
    if endpoint_cols and "extra_target_type" not in endpoint_cols:
        sync_conn.execute(text("ALTER TABLE webhook_endpoints ADD COLUMN extra_target_type VARCHAR(20)"))
    if endpoint_cols and "extra_target_config" not in endpoint_cols:
        sync_conn.execute(text(f"ALTER TABLE webhook_endpoints ADD COLUMN extra_target_config {json_type}"))


async def init_db() -> None:
    # Ensure models are registered on Base.metadata before create_all.
    from app.models import AlertLog, InviteCode, User, WebhookEndpoint  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
