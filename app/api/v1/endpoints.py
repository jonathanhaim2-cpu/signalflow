from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.secrets import mask_config
from app.core.urls import webhook_url_for
from app.i18n import api_message
from app.models.alert_log import AlertLog
from app.models.user import User
from app.models.webhook import WebhookEndpoint
from app.schemas.webhook import AlertLogOut, DestinationOut, EndpointCreate, EndpointOut
from app.services.destinations import apply_destinations, destinations_of, normalize_destinations
from app.services.dispatcher import normalize_callmebot_phone, normalize_discord_webhook
from app.services.plans import enforce_channel_limit

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


def _normalize_config(target_type: str, config: dict) -> dict:
    cleaned = dict(config or {})
    if target_type == "discord" and cleaned.get("discord_webhook_url"):
        cleaned["discord_webhook_url"] = normalize_discord_webhook(cleaned["discord_webhook_url"])
    if target_type == "whatsapp":
        provider = (cleaned.get("provider") or "callmebot").strip().lower().replace("-", "_")
        if provider in {"callmebot", "call_me_bot"}:
            cleaned["provider"] = "callmebot"
            raw_phone = cleaned.get("phone") or cleaned.get("chat_id") or cleaned.get("to") or ""
            cleaned["phone"] = normalize_callmebot_phone(str(raw_phone))
            if not cleaned.get("apikey") and cleaned.get("api_token"):
                cleaned["apikey"] = cleaned["api_token"]
    return cleaned


def _to_out(endpoint: WebhookEndpoint, request: Request) -> EndpointOut:
    dests = destinations_of(endpoint)
    extra_config = endpoint.extra_target_config
    return EndpointOut(
        id=endpoint.id,
        name=endpoint.name,
        token=endpoint.token,
        target_type=endpoint.target_type,
        target_config=mask_config(endpoint.target_config),
        extra_target_type=endpoint.extra_target_type,
        extra_target_config=mask_config(extra_config) if extra_config else None,
        destinations=[
            DestinationOut(type=d["type"], config=mask_config(d.get("config") or {})) for d in dests
        ],
        is_active=endpoint.is_active,
        created_at=endpoint.created_at,
        webhook_url=webhook_url_for(endpoint.token, request),
    )


@router.get("", response_model=list[EndpointOut])
async def list_endpoints(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EndpointOut]:
    result = await db.execute(
        select(WebhookEndpoint).where(WebhookEndpoint.user_id == user.id).order_by(WebhookEndpoint.id.desc())
    )
    return [_to_out(e, request) for e in result.scalars().all()]


@router.post("", response_model=EndpointOut, status_code=201)
async def create_endpoint(
    payload: EndpointCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EndpointOut:
    await enforce_channel_limit(db, user, request)
    dests = normalize_destinations(
        destinations=[d.model_dump() for d in payload.destinations] if payload.destinations else None,
        target_type=payload.target_type,
        target_config=payload.target_config,
        extra_target_type=payload.extra_target_type,
        extra_target_config=payload.extra_target_config,
    )
    dests = [
        {"type": d["type"], "config": _normalize_config(d["type"], d["config"])}
        for d in dests
    ]

    endpoint = WebhookEndpoint(user_id=user.id, name=payload.name)
    apply_destinations(endpoint, dests)
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    return _to_out(endpoint, request)


async def _get_owned_endpoint(
    endpoint_id: int, db: AsyncSession, user: User, request: Request | None = None
) -> WebhookEndpoint:
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id, WebhookEndpoint.user_id == user.id
        )
    )
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise HTTPException(status_code=404, detail=api_message(request, "api.connection_missing"))
    return endpoint


@router.delete("/{endpoint_id}", status_code=204)
async def delete_endpoint(
    endpoint_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    endpoint = await _get_owned_endpoint(endpoint_id, db, user)
    await db.delete(endpoint)
    await db.commit()


@router.patch("/{endpoint_id}/toggle", response_model=EndpointOut)
async def toggle_endpoint(
    endpoint_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EndpointOut:
    endpoint = await _get_owned_endpoint(endpoint_id, db, user)
    endpoint.is_active = not endpoint.is_active
    await db.commit()
    await db.refresh(endpoint)
    return _to_out(endpoint, request)


@router.get("/{endpoint_id}/logs", response_model=list[AlertLogOut])
async def get_endpoint_logs(
    endpoint_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[AlertLog]:
    await _get_owned_endpoint(endpoint_id, db, user)
    result = await db.execute(
        select(AlertLog).where(AlertLog.endpoint_id == endpoint_id).order_by(AlertLog.id.desc()).limit(100)
    )
    return list(result.scalars().all())
