from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.secrets import mask_config
from app.core.urls import webhook_url_for
from app.models.alert_log import AlertLog
from app.models.user import User
from app.models.webhook import WebhookEndpoint
from app.schemas.webhook import AlertLogOut, EndpointCreate, EndpointOut
from app.services.dispatcher import normalize_discord_webhook
from app.services.plans import enforce_channel_limit, enforce_extra_destination

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


def _normalize_config(target_type: str, config: dict) -> dict:
    cleaned = dict(config or {})
    if target_type == "discord" and cleaned.get("discord_webhook_url"):
        cleaned["discord_webhook_url"] = normalize_discord_webhook(cleaned["discord_webhook_url"])
    return cleaned


def _to_out(endpoint: WebhookEndpoint, request: Request) -> EndpointOut:
    extra_config = endpoint.extra_target_config
    return EndpointOut(
        id=endpoint.id,
        name=endpoint.name,
        token=endpoint.token,
        target_type=endpoint.target_type,
        target_config=mask_config(endpoint.target_config),
        extra_target_type=endpoint.extra_target_type,
        extra_target_config=mask_config(extra_config) if extra_config else None,
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
    await enforce_channel_limit(db, user)
    await enforce_extra_destination(user, payload.extra_target_type)

    endpoint = WebhookEndpoint(
        user_id=user.id,
        name=payload.name,
        target_type=payload.target_type,
        target_config=_normalize_config(payload.target_type, payload.target_config),
        extra_target_type=payload.extra_target_type,
        extra_target_config=(
            _normalize_config(payload.extra_target_type, payload.extra_target_config)
            if payload.extra_target_type and payload.extra_target_config
            else None
        ),
    )
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    return _to_out(endpoint, request)


async def _get_owned_endpoint(endpoint_id: int, db: AsyncSession, user: User) -> WebhookEndpoint:
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id, WebhookEndpoint.user_id == user.id
        )
    )
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise HTTPException(status_code=404, detail="החיבור לא נמצא")
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
