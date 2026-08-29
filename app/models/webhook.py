import secrets
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TargetType(str, Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, default=lambda: secrets.token_hex(8)
    )
    target_type: Mapped[str] = mapped_column(String(20), default=TargetType.TELEGRAM.value)
    target_config: Mapped[dict] = mapped_column(JSON, default=dict)
    extra_target_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    extra_target_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="endpoints")
    logs: Mapped[list["AlertLog"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )
