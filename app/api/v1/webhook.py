from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.models.webhook import WebhookEndpoint
from app.schemas.webhook import AlertLogOut, TradingViewAlert
from app.services.relay import relay_alert

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/{endpoint_token}", response_model=AlertLogOut)
@limiter.limit("60/minute")
async def receive_webhook(
    endpoint_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AlertLogOut:
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.token == endpoint_token))
    endpoint = result.scalar_one_or_none()

    if not endpoint:
        raise HTTPException(status_code=404, detail="Unknown webhook endpoint")
    if not endpoint.is_active:
        raise HTTPException(status_code=403, detail="Webhook endpoint is disabled")

    raw_body = await request.body()
    content_type = request.headers.get("content-type")

    log = await relay_alert(db, endpoint, raw_body, content_type)
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
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.token == endpoint_token))
    endpoint = result.scalar_one_or_none()

    if not endpoint or endpoint.user_id != user.id:
        raise HTTPException(status_code=404, detail="Endpoint not found")

    raw_body = alert.model_dump_json().encode("utf-8")
    log = await relay_alert(db, endpoint, raw_body, "application/json")
    return log
