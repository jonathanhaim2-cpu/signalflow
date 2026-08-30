from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import logger
from app.core.urls import public_base_url
from app.models.user import User, UserTier
from app.services.admin import is_admin_user
from app.services.plans import parse_allow_pro_emails

MSG_BILLING_UNCONFIGURED = "סליקה לא הוגדרה עדיין"
MSG_ALREADY_PRO = "כבר יש לכם פרו."
MSG_PADDLE_FAILED = "לא הצלחנו לפתוח דף תשלום. נסו שוב בעוד רגע."
MSG_BAD_SIGNATURE = "חתימה לא תקינה"

PROD_BASE = "https://api.paddle.com"
SANDBOX_BASE = "https://sandbox-api.paddle.com"
GRANT_EVENTS = {
    "transaction.completed",
    "subscription.created",
    "subscription.activated",
}
REVOKE_EVENTS = {
    "subscription.canceled",
    "subscription.cancelled",
    "subscription.past_due",
}


def paddle_configured() -> bool:
    settings = get_settings()
    return bool(
        (settings.PADDLE_API_KEY or "").strip()
        and (settings.PADDLE_PRICE_ID or "").strip()
    )


def paddle_base_url() -> str:
    settings = get_settings()
    return SANDBOX_BASE if settings.PADDLE_SANDBOX else PROD_BASE


def paddle_headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {settings.PADDLE_API_KEY.strip()}",
        "Content-Type": "application/json",
    }


def parse_paddle_signature(header: str) -> tuple[str, list[str]]:
    ts = ""
    signatures: list[str] = []
    for part in (header or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key, value = key.strip(), value.strip()
        if key == "ts":
            ts = value
        elif key == "h1":
            signatures.append(value)
    return ts, signatures


def paddle_signature(ts: str, body: bytes, secret: str) -> str:
    signed = f"{ts}:{body.decode('utf-8')}"
    return hmac.new(secret.encode("utf-8"), signed.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_paddle_signature(header: str, body: bytes, secret: str, *, max_age: int = 300) -> bool:
    ts, signatures = parse_paddle_signature(header)
    if not ts or not signatures or not body or not secret:
        return False
    try:
        age = abs(int(time.time()) - int(ts))
    except ValueError:
        return False
    if max_age and age > max_age:
        return False
    expected = paddle_signature(ts, body, secret)
    return any(hmac.compare_digest(expected, sig) for sig in signatures)


async def paddle_request(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to Paddle Billing. Isolated so tests can mock HTTP."""
    import httpx

    url = paddle_base_url().rstrip("/") + "/" + path.lstrip("/")
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        resp = await client.post(url, json=payload, headers=paddle_headers())
    try:
        data = resp.json()
    except Exception:
        data = {"raw": (resp.text or "")[:400]}
    if resp.status_code >= 400:
        logger.warning("Paddle HTTP %s: %s", resp.status_code, data)
        raise HTTPException(status_code=502, detail=MSG_PADDLE_FAILED)
    return data if isinstance(data, dict) else {"data": data}


def _checkout_payload(user: User, request: Request) -> dict[str, Any]:
    settings = get_settings()
    base = public_base_url(request)
    return {
        "collection_mode": "automatic",
        "currency_code": "USD",
        "items": [{"price_id": settings.PADDLE_PRICE_ID.strip(), "quantity": 1}],
        "custom_data": {"user_id": str(user.id)},
        "checkout": {"url": f"{base}/dashboard"},
    }


def _checkout_url(data: dict[str, Any]) -> str | None:
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    checkout = inner.get("checkout") if isinstance(inner.get("checkout"), dict) else {}
    return checkout.get("url") or data.get("url")


async def create_checkout_session(user: User, request: Request, db: AsyncSession) -> dict[str, str]:
    if not paddle_configured():
        raise HTTPException(status_code=503, detail=MSG_BILLING_UNCONFIGURED)
    if (user.tier or "").lower() == UserTier.PRO.value:
        raise HTTPException(status_code=400, detail=MSG_ALREADY_PRO)

    payload = _checkout_payload(user, request)
    data = await paddle_request("transactions", payload)
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    url = _checkout_url(data)
    txn_id = str(inner.get("id") or "")
    if not url:
        logger.warning("Paddle create transaction missing checkout.url: %s", data)
        raise HTTPException(status_code=502, detail=MSG_PADDLE_FAILED)
    if txn_id:
        user.paddle_transaction_id = txn_id
        await db.commit()
        await db.refresh(user)
    return {"url": url, "transaction_id": txn_id}


def _custom_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    custom = data.get("custom_data") if isinstance(data.get("custom_data"), dict) else {}
    return custom


def _ids_from_payload(payload: dict[str, Any]) -> dict[str, str]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    custom = _custom_data(payload)
    event_type = str(payload.get("event_type") or payload.get("eventType") or "").strip()
    entity_id = str(data.get("id") or "").strip()
    subscription_id = str(data.get("subscription_id") or "").strip()
    if event_type.startswith("subscription.") and entity_id.startswith("sub_"):
        subscription_id = entity_id
    transaction_id = entity_id if entity_id.startswith("txn_") else str(data.get("transaction_id") or "").strip()
    return {
        "user_id": str(custom.get("user_id") or custom.get("userId") or "").strip(),
        "email": str(
            custom.get("email")
            or data.get("email")
            or (data.get("customer") or {}).get("email")
            or ""
        ).strip().lower(),
        "customer_id": str(data.get("customer_id") or "").strip(),
        "subscription_id": subscription_id,
        "transaction_id": transaction_id,
    }


async def _find_user(db: AsyncSession, ids: dict[str, str]) -> User | None:
    clauses = []
    if ids["user_id"].isdigit():
        clauses.append(User.id == int(ids["user_id"]))
    if ids["email"]:
        clauses.append(User.email == ids["email"])
    if ids["subscription_id"]:
        clauses.append(User.paddle_subscription_id == ids["subscription_id"])
    if ids["customer_id"]:
        clauses.append(User.paddle_customer_id == ids["customer_id"])
    if ids["transaction_id"]:
        clauses.append(User.paddle_transaction_id == ids["transaction_id"])
    if not clauses:
        return None
    result = await db.execute(select(User).where(or_(*clauses)))
    return result.scalars().first()


def should_keep_manual_pro(user: User) -> bool:
    if user.manual_pro:
        return True
    if user.email.lower() in parse_allow_pro_emails():
        return True
    if is_admin_user(user):
        return True
    return False


async def grant_pro_from_paddle(db: AsyncSession, user: User, ids: dict[str, str]) -> User:
    user.tier = UserTier.PRO.value
    user.upgrade_requested_at = None
    if ids.get("customer_id"):
        user.paddle_customer_id = ids["customer_id"]
    if ids.get("subscription_id"):
        user.paddle_subscription_id = ids["subscription_id"]
    if ids.get("transaction_id"):
        user.paddle_transaction_id = ids["transaction_id"]
    await db.commit()
    await db.refresh(user)
    return user


async def revoke_pro_from_paddle(db: AsyncSession, user: User) -> User:
    if should_keep_manual_pro(user):
        logger.info("Paddle revoke skipped for manual/admin Pro user=%s", user.email)
        return user
    user.tier = UserTier.FREE.value
    await db.commit()
    await db.refresh(user)
    return user


def event_type_of(payload: dict[str, Any]) -> str:
    return str(payload.get("event_type") or payload.get("eventType") or "").strip().lower()


async def apply_paddle_webhook(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    event = event_type_of(payload)
    ids = _ids_from_payload(payload)
    user = await _find_user(db, ids)
    if user is None:
        logger.warning("Paddle webhook user not found: event=%s ids=%s", event, ids)
        return {"ok": False, "detail": "user-not-found"}

    if event in GRANT_EVENTS:
        await grant_pro_from_paddle(db, user, ids)
        return {"ok": True, "action": "grant", "user_id": user.id, "event": event}
    if event in REVOKE_EVENTS:
        await revoke_pro_from_paddle(db, user)
        return {"ok": True, "action": "revoke", "user_id": user.id, "event": event}
    logger.info("Paddle webhook ignored event=%s user=%s", event, user.email)
    return {"ok": True, "action": "ignored", "user_id": user.id, "event": event}


def parse_json_body(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw.decode("utf-8", errors="replace")[:2000]}
    return data if isinstance(data, dict) else {"data": data}
