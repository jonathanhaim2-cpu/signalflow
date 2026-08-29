from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user_optional
from app.core.security import hash_password
from app.core.urls import public_base_url
from app.models.invite import InviteCode
from app.models.user import User, UserTier
from app.services.admin import (
    all_invites,
    create_invite,
    invite_status,
    is_admin_user,
    is_env_protected_owner,
    redeem_invite,
    revoke_invite,
    set_user_disabled,
    set_user_tier,
)
from app.services.plans import count_alerts_today
from app.services.qr import qr_png_bytes

router = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


def _login_redirect(next_path: str = "/admin") -> RedirectResponse:
    return RedirectResponse(url=f"/login?next={next_path}", status_code=303)


def _require_admin(user: User | None, next_path: str = "/admin"):
    if not user:
        return _login_redirect(next_path)
    if not is_admin_user(user):
        raise HTTPException(status_code=404, detail="העמוד לא נמצא")
    return None


def _temp_password() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


def redeem_url_for(code: str, request: Request) -> str:
    return f"{public_base_url(request)}/redeem/{code}"


async def _user_rows(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(User).order_by(User.id.desc()))
    rows = []
    for user in result.scalars().all():
        rows.append(
            {
                "user": user,
                "tier_label": "פרו" if user.tier == UserTier.PRO.value else "חינם",
                "alerts_today": await count_alerts_today(db, user.id),
                "upgrade_requested": bool(user.upgrade_requested_at),
                "protected": is_env_protected_owner(user.email),
            }
        )
    return rows


async def _admin_context(
    request: Request,
    db: AsyncSession,
    admin: User,
    **extra,
) -> dict:
    invites = await all_invites(db)
    unused = [inv for inv in invites if invite_status(inv) == "unused"]
    ctx = {
        "admin": admin,
        "user": admin,
        "nav_mode": "app",
        "users": await _user_rows(db),
        "unused_invites": unused,
        "invites": invites,
        "invite_status": {inv.id: invite_status(inv) for inv in invites},
        "redeem_urls": {inv.id: redeem_url_for(inv.code, request) for inv in unused},
        "flash": None,
        "generated_password": None,
        "created_email": None,
        "error": None,
    }
    ctx.update(extra)
    return ctx


@router.get("/admin")
async def admin_home(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    blocked = _require_admin(user)
    if blocked:
        return blocked
    return templates.TemplateResponse(
        request, "admin.html", await _admin_context(request, db, user)
    )


@router.post("/admin/users/{user_id}/pro")
async def admin_make_pro(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    blocked = _require_admin(user)
    if blocked:
        return blocked
    target = await db.get(User, user_id)
    if target:
        await set_user_tier(db, target, UserTier.PRO.value)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/free")
async def admin_make_free(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    blocked = _require_admin(user)
    if blocked:
        return blocked
    target = await db.get(User, user_id)
    if target and not is_env_protected_owner(target.email):
        await set_user_tier(db, target, UserTier.FREE.value)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/disable")
async def admin_disable(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    blocked = _require_admin(user)
    if blocked:
        return blocked
    target = await db.get(User, user_id)
    if target and target.id != user.id and not is_env_protected_owner(target.email):
        await set_user_disabled(db, target, True)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/enable")
async def admin_enable(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    blocked = _require_admin(user)
    if blocked:
        return blocked
    target = await db.get(User, user_id)
    if target:
        await set_user_disabled(db, target, False)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/create")
async def admin_create_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    blocked = _require_admin(user)
    if blocked:
        return blocked
    email = email.strip().lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        ctx = await _admin_context(request, db, user, error="האימייל הזה כבר רשום.")
        return templates.TemplateResponse(request, "admin.html", ctx, status_code=400)
    raw_password = password.strip()
    if not raw_password:
        raw_password = _temp_password()
    if len(raw_password) < 8:
        ctx = await _admin_context(request, db, user, error="הסיסמה חייבת להכיל לפחות 8 תווים.")
        return templates.TemplateResponse(request, "admin.html", ctx, status_code=400)
    new_user = User(email=email, hashed_password=hash_password(raw_password))
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    from app.services.admin import persist_privileges

    await persist_privileges(db, new_user)
    ctx = await _admin_context(
        request,
        db,
        user,
        flash="המשתמש נוצר. הראו לו את הסיסמה עכשיו — היא לא תופיע שוב.",
        generated_password=raw_password,
        created_email=email,
    )
    return templates.TemplateResponse(request, "admin.html", ctx)


@router.post("/admin/invites")
async def admin_create_invite(
    days: int = Form(7),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    blocked = _require_admin(user)
    if blocked:
        return blocked
    invite = await create_invite(db, created_by=user, days=days)
    return RedirectResponse(url=f"/admin/invites/{invite.id}/print", status_code=303)


@router.post("/admin/invites/{invite_id}/revoke")
async def admin_revoke_invite(
    invite_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    blocked = _require_admin(user)
    if blocked:
        return blocked
    invite = await db.get(InviteCode, invite_id)
    if invite:
        await revoke_invite(db, invite)
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/admin/invites/{invite_id}/print")
async def admin_print_invite(
    invite_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    blocked = _require_admin(user, next_path=f"/admin/invites/{invite_id}/print")
    if blocked:
        return blocked
    invite = await db.get(InviteCode, invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="העמוד לא נמצא")
    return templates.TemplateResponse(
        request,
        "admin_print.html",
        {
            "invite": invite,
            "status": invite_status(invite),
            "redeem_url": redeem_url_for(invite.code, request),
        },
    )


@router.get("/admin/invites/{invite_id}/qr.png")
async def admin_invite_qr(
    invite_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    blocked = _require_admin(user)
    if blocked:
        return blocked
    invite = await db.get(InviteCode, invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="העמוד לא נמצא")
    png = qr_png_bytes(redeem_url_for(invite.code, request))
    return Response(content=png, media_type="image/png")


@router.get("/redeem/{code}")
async def redeem_page(
    code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    if user:
        ok, message = await redeem_invite(db, code, user)
        return templates.TemplateResponse(
            request,
            "redeem.html",
            {"ok": ok, "message": message, "code": code.upper(), "logged_in": True},
        )
    return templates.TemplateResponse(
        request,
        "redeem.html",
        {
            "ok": None,
            "message": "כדי לממש את הקוד צריך להירשם או להיכנס. אחר כך הקוד יופעל אוטומטית.",
            "code": code.upper(),
            "logged_in": False,
            "next": f"/redeem/{code}",
        },
    )
