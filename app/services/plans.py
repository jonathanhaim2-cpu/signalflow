from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.alert_log import AlertLog
from app.models.user import User, UserTier
from app.models.webhook import WebhookEndpoint

FREE_ALERTS_PER_DAY = 3
FREE_CHANNEL_LIMIT = 1
SIGNALFLOW_FOOTER = "— SignalFlow"

MSG_CHANNEL_LIMIT = "בתוכנית החינמית אפשר לחבר קישור אחד בלבד. לשדרוג: $9 לחודש."
MSG_ALERT_LIMIT = "הגעתם למכסת 3 ההתראות היומית בתוכנית החינמית. נסו שוב מחר או שדרגו לפרו."


def parse_allow_pro_emails() -> set[str]:
    raw = get_settings().ALLOW_PRO_EMAILS or ""
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def is_pro(user: User | None) -> bool:
    if user is None:
        return False
    if (user.tier or "").lower() == UserTier.PRO.value:
        return True
    return user.email.lower() in parse_allow_pro_emails()


def effective_tier(user: User) -> str:
    return UserTier.PRO.value if is_pro(user) else UserTier.FREE.value


async def persist_allowlist_pro(db: AsyncSession, user: User) -> User:
    from app.services.admin import persist_privileges

    return await persist_privileges(db, user)


async def grant_pro(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.strip().lower()))
    user = result.scalar_one_or_none()
    if not user:
        return None
    user.tier = UserTier.PRO.value
    user.manual_pro = True
    user.upgrade_requested_at = None
    await db.commit()
    await db.refresh(user)
    return user


def utc_today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def count_channels(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(func.count(WebhookEndpoint.id)).where(WebhookEndpoint.user_id == user_id)
    )
    return int(result.scalar() or 0)


async def count_alerts_today(db: AsyncSession, user_id: int) -> int:
    today = utc_today_str()
    result = await db.execute(
        select(func.count(AlertLog.id))
        .join(WebhookEndpoint, AlertLog.endpoint_id == WebhookEndpoint.id)
        .where(
            WebhookEndpoint.user_id == user_id,
            func.date(AlertLog.created_at) == today,
        )
    )
    return int(result.scalar() or 0)


async def plan_snapshot(db: AsyncSession, user: User) -> dict:
    used_alerts = await count_alerts_today(db, user.id)
    used_channels = await count_channels(db, user.id)
    pro = is_pro(user)
    alerts_limit = None if pro else FREE_ALERTS_PER_DAY
    remaining = None if pro else max(0, FREE_ALERTS_PER_DAY - used_alerts)
    return {
        "tier": effective_tier(user),
        "alerts_used_today": used_alerts,
        "alerts_limit": alerts_limit,
        "alerts_remaining_today": remaining,
        "channels_used": used_channels,
        "channel_limit": None if pro else FREE_CHANNEL_LIMIT,
        "upgrade_requested_at": user.upgrade_requested_at,
    }


async def enforce_channel_limit(db: AsyncSession, user: User) -> None:
    if is_pro(user):
        return
    if await count_channels(db, user.id) >= FREE_CHANNEL_LIMIT:
        raise HTTPException(status_code=403, detail=MSG_CHANNEL_LIMIT)


async def enforce_alert_quota(db: AsyncSession, user: User) -> None:
    if is_pro(user):
        return
    if await count_alerts_today(db, user.id) >= FREE_ALERTS_PER_DAY:
        raise HTTPException(status_code=429, detail=MSG_ALERT_LIMIT)


def apply_footer(text: str, user: User | None, *, html: bool = False) -> str:
    if is_pro(user):
        return text
    if html:
        return f"{text}\n\n<i>{SIGNALFLOW_FOOTER}</i>"
    return f"{text}\n\n{SIGNALFLOW_FOOTER}"
