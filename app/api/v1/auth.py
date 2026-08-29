from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import MeOut, Token, UserCreate, UserLogin, UserOut
from app.services.plans import persist_allowlist_pro, plan_snapshot

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_MAX_AGE = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def _set_session_cookie(response: Response, email: str) -> str:
    token = create_access_token(subject=email)
    response.set_cookie(
        "access_token", token, httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax"
    )
    return token


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(payload: UserCreate, response: Response, db: AsyncSession = Depends(get_db)) -> User:
    email = str(payload.email).strip().lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="האימייל הזה כבר רשום אצלנו")

    user = User(email=email, hashed_password=hash_password(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    user = await persist_allowlist_pro(db, user)

    _set_session_cookie(response, user.email)
    return user


@router.post("/login", response_model=Token)
async def login(payload: UserLogin, response: Response, db: AsyncSession = Depends(get_db)) -> Token:
    email = str(payload.email).strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="אימייל או סיסמה שגויים")
    if user.is_disabled:
        raise HTTPException(status_code=401, detail="החשבון מושבת. פנו לבעלים.")

    user = await persist_allowlist_pro(db, user)
    token = _set_session_cookie(response, user.email)
    return Token(access_token=token)


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie("access_token")
    return {"ok": True}


@router.get("/me", response_model=MeOut)
async def me(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> MeOut:
    snap = await plan_snapshot(db, user)
    return MeOut(
        id=user.id,
        email=user.email,
        api_token=user.api_token,
        tier=snap["tier"],
        is_admin=user.is_admin,
        upgrade_requested_at=snap["upgrade_requested_at"],
        alerts_used_today=snap["alerts_used_today"],
        alerts_limit=snap["alerts_limit"],
        alerts_remaining_today=snap["alerts_remaining_today"],
        channels_used=snap["channels_used"],
        channel_limit=snap["channel_limit"],
    )


@router.post("/request-pro")
async def request_pro(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Record a Pro waitlist request. Does not charge and does not change the tier."""
    if user.upgrade_requested_at is None:
        user.upgrade_requested_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(user)
    return {
        "ok": True,
        "charged": False,
        "upgrade_requested_at": user.upgrade_requested_at.isoformat() if user.upgrade_requested_at else None,
    }
