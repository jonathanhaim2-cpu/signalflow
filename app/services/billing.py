from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
MSG_PAYPLUS_FAILED = "לא הצלחנו לפתוח דף תשלום. נסו שוב בעוד רגע."

PRO_PRICE_ILS = 39
PROD_BASE = "https://restapi.payplus.co.il/api/v1.0/"
STAGING_BASE = "https://restapidev.payplus.co.il/api/v1.0/"
GENERATE_LINK_PATH = "PaymentPages/generateLink"

SUCCESS_CODES = {"000", "0", "00"}
REVOKE_TYPES = {
    "cancel",
    "cancelled",
    "canceled",
    "cancellation",
    "refund",
    "failure",
    "failed",
    "reject",
    "rejected",
    "unpaid",
}


def payplus_configured() -> bool:
    settings = get_settings()
    return bool(
        (settings.PAYPLUS_API_KEY or "").strip()
        and (settings.PAYPLUS_SECRET_KEY or "").strip()
        and (settings.PAYPLUS_PAYMENT_PAGE_UID or "").strip()
    )


def payplus_base_url() -> str:
    settings = get_settings()
    return STAGING_BASE if settings.PAYPLUS_USE_STAGING else PROD_BASE


def payplus_headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "api-key": settings.PAYPLUS_API_KEY.strip(),
        "secret-key": settings.PAYPLUS_SECRET_KEY.strip(),
        "Content-Type": "application/json",
    }


def payplus_hash(body: bytes, secret: str) -> str:
    return base64.b64encode(hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()).decode(
        "ascii"
    )


def verify_payplus_callback(request: Request, body: bytes) -> bool:
    """Validate PayPlus callback hash when a secret is configured."""
    settings = get_settings()
    secret = (settings.PAYPLUS_SECRET_KEY or "").strip()
    if not secret:
        return False
    header_hash = request.headers.get("hash") or request.headers.get("Hash") or ""
    if not header_hash or not body:
        return False
    expected = payplus_hash(body, secret)
    return hmac.compare_digest(expected, header_hash)


async def payplus_request(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to PayPlus. Isolated so tests can mock HTTP without Stripe leftovers."""
    import httpx

    url = payplus_base_url().rstrip("/") + "/" + path.lstrip("/")
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        resp = await client.post(url, json=payload, headers=payplus_headers())
    try:
        data = resp.json()
    except Exception:
        data = {"raw": (resp.text or "")[:400]}
    if resp.status_code >= 400:
        logger.warning("PayPlus HTTP %s: %s", resp.status_code, data)
        raise HTTPException(status_code=502, detail=MSG_PAYPLUS_FAILED)
    return data if isinstance(data, dict) else {"data": data}


def _generate_link_payload(user: User, request: Request) -> dict[str, Any]:
    settings = get_settings()
    base = public_base_url(request)
    payload: dict[str, Any] = {
        "payment_page_uid": settings.PAYPLUS_PAYMENT_PAGE_UID.strip(),
        "charge_method": 3,
        "currency_code": "ILS",
        "amount": PRO_PRICE_ILS,
        "language_code": "he",
        "sendEmailApproval": True,
        "sendEmailFailure": True,
        "send_failure_callback": True,
        "refURL_success": f"{base}/dashboard?checkout=success",
        "refURL_failure": f"{base}/dashboard?checkout=failure",
        "refURL_cancel": f"{base}/dashboard?checkout=cancel",
        "refURL_callback": f"{base}/api/v1/billing/payplus",
        "more_info": str(user.id),
        "more_info_1": user.email,
        "customer": {
            "customer_name": user.email.split("@")[0],
            "email": user.email,
            "customer_external_number": str(user.id),
        },
        "items": [
            {
                "name": "SignalFlow Pro",
                "quantity": 1,
                "price": PRO_PRICE_ILS,
                "vat_type": 0,
            }
        ],
        "allowed_charge_methods": ["credit-card", "bit"],
        "recurring_settings": {
            "instant_first_payment": True,
            "recurring_type": 2,
            "recurring_range": 1,
            "number_of_charges": 0,
            "start_date_on_payment_date": True,
            "start_date": 1,
            "jump_payments": 0,
            "successful_invoice": False,
            "customer_failure_email": True,
            "send_customer_success_email": True,
        },
    }
    terminal = (settings.PAYPLUS_TERMINAL_UID or "").strip()
    if terminal:
        payload["terminal_uid"] = terminal
    return payload


async def create_checkout_session(user: User, request: Request, db: AsyncSession) -> dict[str, str]:
    if not payplus_configured():
        raise HTTPException(status_code=503, detail=MSG_BILLING_UNCONFIGURED)
    if (user.tier or "").lower() == UserTier.PRO.value:
        raise HTTPException(status_code=400, detail=MSG_ALREADY_PRO)

    payload = _generate_link_payload(user, request)
    data = await payplus_request(GENERATE_LINK_PATH, payload)
    results = data.get("results") or {}
    if str(results.get("status") or "").lower() not in {"success", "ok", ""} and results.get("code") not in (
        0,
        "0",
        None,
    ):
        logger.warning("PayPlus generateLink failed: %s", data)
        raise HTTPException(status_code=502, detail=MSG_PAYPLUS_FAILED)

    inner = data.get("data") or {}
    link = inner.get("payment_page_link") or data.get("payment_page_link")
    page_uid = inner.get("page_request_uid") or data.get("page_request_uid")
    if not link:
        logger.warning("PayPlus generateLink missing link: %s", data)
        raise HTTPException(status_code=502, detail=MSG_PAYPLUS_FAILED)

    if page_uid:
        user.payplus_page_request_uid = str(page_uid)
        await db.commit()
        await db.refresh(user)
    return {"url": link, "page_request_uid": str(page_uid or "")}


def _nested(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _status_code(payload: dict[str, Any]) -> str:
    raw = (
        _nested(payload, "transaction", "status_code")
        or payload.get("status_code")
        or payload.get("statusCode")
        or ""
    )
    return str(raw).strip()


def _transaction_type(payload: dict[str, Any]) -> str:
    raw = (
        payload.get("transaction_type")
        or payload.get("type")
        or _nested(payload, "transaction", "type")
        or ""
    )
    return str(raw).strip().lower()


def _status_word(payload: dict[str, Any]) -> str:
    raw = payload.get("status") or _nested(payload, "transaction", "status") or ""
    return str(raw).strip().lower()


def is_success_callback(payload: dict[str, Any]) -> bool:
    code = _status_code(payload)
    if code and code in SUCCESS_CODES:
        return True
    status = _status_word(payload)
    if status in {"success", "approved", "ok", "charge"}:
        return True
    ttype = _transaction_type(payload)
    if ttype in {"charge", "charged"} and (not code or code in SUCCESS_CODES):
        if status in REVOKE_TYPES:
            return False
        return True
    return False


def is_revoke_callback(payload: dict[str, Any]) -> bool:
    ttype = _transaction_type(payload)
    status = _status_word(payload)
    code = _status_code(payload)
    if ttype in REVOKE_TYPES or status in REVOKE_TYPES:
        return True
    if code and code not in SUCCESS_CODES:
        return True
    return False


def _ids_from_payload(payload: dict[str, Any]) -> dict[str, str]:
    tx = payload.get("transaction") if isinstance(payload.get("transaction"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    recurring = tx.get("recurring_charge_information") if isinstance(tx.get("recurring_charge_information"), dict) else {}
    more_info = str(tx.get("more_info") or payload.get("more_info") or "").strip()
    more_info_1 = str(tx.get("more_info_1") or payload.get("more_info_1") or "").strip()
    return {
        "user_id": more_info,
        "email": more_info_1
        or str(_nested(payload, "customer", "email") or data.get("email") or payload.get("email") or "").strip(),
        "customer_uid": str(data.get("customer_uid") or payload.get("customer_uid") or "").strip(),
        "recurring_uid": str(
            recurring.get("recurring_uid") or payload.get("recurring_uid") or ""
        ).strip(),
        "page_request_uid": str(
            tx.get("payment_request_uid")
            or payload.get("payment_request_uid")
            or payload.get("page_request_uid")
            or ""
        ).strip(),
    }


async def _find_user(db: AsyncSession, ids: dict[str, str]) -> User | None:
    clauses = []
    if ids["user_id"].isdigit():
        clauses.append(User.id == int(ids["user_id"]))
    if ids["email"]:
        clauses.append(User.email == ids["email"].lower())
    if ids["page_request_uid"]:
        clauses.append(User.payplus_page_request_uid == ids["page_request_uid"])
    if ids["recurring_uid"]:
        clauses.append(User.payplus_recurring_uid == ids["recurring_uid"])
    if ids["customer_uid"]:
        clauses.append(User.payplus_customer_uid == ids["customer_uid"])
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


async def grant_pro_from_payplus(db: AsyncSession, user: User, ids: dict[str, str]) -> User:
    user.tier = UserTier.PRO.value
    user.upgrade_requested_at = None
    if ids.get("customer_uid"):
        user.payplus_customer_uid = ids["customer_uid"]
    if ids.get("recurring_uid"):
        user.payplus_recurring_uid = ids["recurring_uid"]
    if ids.get("page_request_uid"):
        user.payplus_page_request_uid = ids["page_request_uid"]
    await db.commit()
    await db.refresh(user)
    return user


async def revoke_pro_from_payplus(db: AsyncSession, user: User) -> User:
    if should_keep_manual_pro(user):
        logger.info("PayPlus revoke skipped for manual/admin Pro user=%s", user.email)
        return user
    user.tier = UserTier.FREE.value
    await db.commit()
    await db.refresh(user)
    return user


async def apply_payplus_callback(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    ids = _ids_from_payload(payload)
    user = await _find_user(db, ids)
    if user is None:
        logger.warning("PayPlus callback user not found: %s", ids)
        return {"ok": False, "detail": "user-not-found"}

    if is_success_callback(payload) and not is_revoke_callback(payload):
        await grant_pro_from_payplus(db, user, ids)
        return {"ok": True, "action": "grant", "user_id": user.id}
    if is_revoke_callback(payload):
        await revoke_pro_from_payplus(db, user)
        return {"ok": True, "action": "revoke", "user_id": user.id}
    logger.info("PayPlus callback ignored for user=%s payload_keys=%s", user.email, list(payload)[:8])
    return {"ok": True, "action": "ignored", "user_id": user.id}


async def parse_callback_payload(request: Request) -> dict[str, Any]:
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        body = await request.body()
        if not body:
            return dict(request.query_params)
        try:
            data = json.loads(body)
            return data if isinstance(data, dict) else {"data": data}
        except json.JSONDecodeError:
            return {"raw": body.decode("utf-8", errors="replace")[:2000]}
    form = None
    try:
        form = await request.form()
    except Exception:
        form = None
    if form:
        return {str(k): str(v) for k, v in form.items()}
    if request.query_params:
        return dict(request.query_params)
    body = await request.body()
    if body:
        try:
            data = json.loads(body)
            return data if isinstance(data, dict) else {"data": data}
        except json.JSONDecodeError:
            return {"raw": body.decode("utf-8", errors="replace")[:2000]}
    return {}
