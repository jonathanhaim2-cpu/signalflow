from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.models.webhook import WebhookEndpoint
from app.schemas.webhook import AlertLogOut, TradingViewAlert
from app.services.plans import enforce_alert_quota
from app.services.relay import relay_alert

router = APIRouter(prefix="/webhook", tags=["webhook"])


async def _load_endpoint(db: AsyncSession, endpoint_token: str) -> WebhookEndpoint:
    result = await db.execute(
        select(WebhookEndpoint)
        .options(selectinload(WebhookEndpoint.user))
        .where(WebhookEndpoint.token == endpoint_token)
    )
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise HTTPException(status_code=404, detail="חיבור לא מוכר")
    if not endpoint.is_active:
        raise HTTPException(status_code=403, detail="החיבור כבוי")
    if endpoint.user and endpoint.user.is_disabled:
        raise HTTPException(status_code=403, detail="החשבון מושבת")
    return endpoint


@router.post("/{endpoint_token}", response_model=AlertLogOut)
@limiter.limit("60/minute")
async def receive_webhook(
    endpoint_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AlertLogOut:
    endpoint = await _load_endpoint(db, endpoint_token)
    await enforce_alert_quota(db, endpoint.user)

    raw_body = await request.body()
    content_type = request.headers.get("content-type")

    log = await relay_alert(db, endpoint, raw_body, content_type, user=endpoint.user)
    logger.info(
        "Alert relayed endpoint=%s status=%s latency_ms=%.1f", endpoint.token, log.status, log.latency_ms
    )
    return log


@router.post("/{endpoint_token}/test", response_model=AlertLogOut)
async def test_webhook(
    endpoint_token: str,
    alert: TradingViewAlert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AlertLogOut:
    """Send a simulated alert through an owned endpoint — used by the dashboard's payload tester."""
    endpoint = await _load_endpoint(db, endpoint_token)
    if endpoint.user_id != user.id:
        raise HTTPException(status_code=404, detail="החיבור לא נמצא")

    await enforce_alert_quota(db, user)

    raw_body = alert.model_dump_json().encode("utf-8")
    log = await relay_alert(db, endpoint, raw_body, "application/json", user=user)
    return log
