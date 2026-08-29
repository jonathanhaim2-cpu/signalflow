from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.logging import logger
from app.models.user import User
from app.services.billing import (
    MSG_BILLING_UNCONFIGURED,
    apply_payplus_callback,
    create_checkout_session,
    parse_callback_payload,
    payplus_configured,
    verify_payplus_callback,
)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout")
async def billing_checkout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return await create_checkout_session(user, request, db)


@router.api_route("/payplus", methods=["GET", "POST"])
async def payplus_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    raw = await request.body()
    settings = get_settings()
    secret_set = bool((settings.PAYPLUS_SECRET_KEY or "").strip())
    if secret_set and raw and request.headers.get("hash"):
        if not verify_payplus_callback(request, raw):
            logger.warning("PayPlus callback hash mismatch")
            raise HTTPException(status_code=400, detail="חתימה לא תקינה")
    elif secret_set and raw and (request.headers.get("user-agent") or "") == "PayPlus":
        if not verify_payplus_callback(request, raw):
            logger.warning("PayPlus callback missing/invalid hash from PayPlus UA")
            raise HTTPException(status_code=400, detail="חתימה לא תקינה")

    if not payplus_configured() and not raw and not request.query_params:
        raise HTTPException(status_code=503, detail=MSG_BILLING_UNCONFIGURED)

    # parse_callback_payload may re-read body; FastAPI caches request.body()
    payload = await parse_callback_payload(request)
    result = await apply_payplus_callback(db, payload)
    return JSONResponse(result)
