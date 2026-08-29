import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserTier(str, Enum):
    FREE = "free"
    PRO = "pro"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    api_token: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid.uuid4())
    )
    tier: Mapped[str] = mapped_column(String(20), default=UserTier.FREE.value)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    upgrade_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    manual_pro: Mapped[bool] = mapped_column(Boolean, default=False)
    payplus_customer_uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payplus_recurring_uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payplus_page_request_uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    endpoints: Mapped[list["WebhookEndpoint"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
