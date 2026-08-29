from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.invite import InviteCode
from app.models.user import User, UserTier

DEFAULT_OWNER_EMAIL = "jonathanhaim2@gmail.com"
DEFAULT_INVITE_DAYS = 7


def parse_admin_emails() -> set[str]:
    raw = get_settings().ADMIN_EMAILS or ""
    emails = {part.strip().lower() for part in raw.split(",") if part.strip()}
    emails.add(DEFAULT_OWNER_EMAIL)
    return emails


def is_admin_user(user: User | None) -> bool:
    if user is None:
        return False
    if user.is_admin:
        return True
    return user.email.lower() in parse_admin_emails()


def is_env_protected_owner(email: str) -> bool:
    return email.strip().lower() in parse_admin_emails()


async def persist_privileges(db: AsyncSession, user: User) -> User:
    """On signup/login: ADMIN_EMAILS / owner → admin+pro; ALLOW_PRO_EMAILS → pro."""
    from app.services.plans import parse_allow_pro_emails

    changed = False
    email = user.email.lower()
    if email in parse_allow_pro_emails() and user.tier != UserTier.PRO.value:
        user.tier = UserTier.PRO.value
        changed = True
    if email in parse_admin_emails():
        if not user.is_admin:
            user.is_admin = True
            changed = True
        if user.tier != UserTier.PRO.value:
            user.tier = UserTier.PRO.value
            changed = True
    if changed:
        await db.commit()
        await db.refresh(user)
    return user


async def set_user_tier(db: AsyncSession, user: User, tier: str) -> User:
    user.tier = tier
    if tier == UserTier.PRO.value:
        user.upgrade_requested_at = None
    await db.commit()
    await db.refresh(user)
    return user


async def set_user_disabled(db: AsyncSession, user: User, disabled: bool) -> User:
    user.is_disabled = disabled
    await db.commit()
    await db.refresh(user)
    return user


def generate_invite_code() -> str:
    raw = secrets.token_hex(4).upper()
    return f"SF-{raw[:4]}-{raw[4:]}"


async def create_invite(
    db: AsyncSession,
    *,
    created_by: User | None,
    days: int = DEFAULT_INVITE_DAYS,
) -> InviteCode:
    days = max(1, min(days, 365))
    for _ in range(8):
        code = generate_invite_code()
        exists = await db.execute(select(InviteCode).where(InviteCode.code == code))
        if exists.scalar_one_or_none():
            continue
        invite = InviteCode(
            code=code,
            expires_at=datetime.now(timezone.utc) + timedelta(days=days),
            created_by_user_id=created_by.id if created_by else None,
        )
        db.add(invite)
        await db.commit()
        await db.refresh(invite)
        return invite
    raise RuntimeError("לא הצלחנו ליצור קוד ייחודי")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def invite_status(invite: InviteCode) -> str:
    now = datetime.now(timezone.utc)
    if invite.revoked_at:
        return "revoked"
    if invite.redeemed_at:
        return "used"
    expires = _aware(invite.expires_at)
    if expires and expires < now:
        return "expired"
    return "unused"


async def redeem_invite(db: AsyncSession, code: str, user: User) -> tuple[bool, str]:
    normalized = (code or "").strip().upper()
    result = await db.execute(select(InviteCode).where(InviteCode.code == normalized))
    invite = result.scalar_one_or_none()
    if not invite:
        return False, "הקוד לא נמצא. בדקו שהעתקתם אותו נכון."
    status = invite_status(invite)
    if status == "revoked":
        return False, "הקוד בוטל ולא ניתן לממש אותו."
    if status == "used":
        return False, "הקוד כבר מומש. כל קוד עובד פעם אחת."
    if status == "expired":
        return False, "פג תוקף הקוד. בקשו מהבעלים קוד חדש."
    user.tier = UserTier.PRO.value
    user.upgrade_requested_at = None
    invite.redeemed_at = datetime.now(timezone.utc)
    invite.redeemed_by_user_id = user.id
    await db.commit()
    await db.refresh(user)
    return True, "החשבון שודרג לפרו. בלי הגבלת ערוצים והתראות."


async def revoke_invite(db: AsyncSession, invite: InviteCode) -> InviteCode:
    if invite.redeemed_at is None and invite.revoked_at is None:
        invite.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(invite)
    return invite


async def unused_invites(db: AsyncSession) -> list[InviteCode]:
    result = await db.execute(select(InviteCode).order_by(InviteCode.id.desc()))
    return [inv for inv in result.scalars().all() if invite_status(inv) == "unused"]


async def all_invites(db: AsyncSession) -> list[InviteCode]:
    result = await db.execute(select(InviteCode).order_by(InviteCode.id.desc()))
    return list(result.scalars().all())
