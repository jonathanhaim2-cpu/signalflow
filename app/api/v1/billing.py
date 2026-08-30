from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.logging import logger
from app.models.user import User
from app.i18n import api_message
from app.services.billing import (
    apply_paddle_webhook,
    create_checkout_session,
    paddle_configured,
    parse_json_body,
    verify_paddle_signature,
)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout")
async def billing_checkout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return await create_checkout_session(user, request, db)


@router.post("/paddle")
async def paddle_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    raw = await request.body()
    settings = get_settings()
    secret = (settings.PADDLE_WEBHOOK_SECRET or "").strip()
    signature = request.headers.get("paddle-signature") or request.headers.get("Paddle-Signature") or ""

    if secret:
        if not verify_paddle_signature(signature, raw, secret):
            logger.warning("Paddle webhook signature mismatch")
            raise HTTPException(status_code=400, detail=api_message(request, "api.bad_signature"))
    elif not paddle_configured() and not raw:
        raise HTTPException(status_code=503, detail=api_message(request, "api.billing_unconfigured"))

    payload = parse_json_body(raw)
    result = await apply_paddle_webhook(db, payload)
    return JSONResponse(result)
