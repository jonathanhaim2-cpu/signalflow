from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.alert_log import AlertLog
from app.models.user import User
from app.models.webhook import WebhookEndpoint
from app.schemas.webhook import AlertLogOut, EndpointCreate, EndpointOut

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


def _to_out(endpoint: WebhookEndpoint) -> EndpointOut:
    out = EndpointOut.model_validate(endpoint)
    out.webhook_url = f"{settings.BASE_URL}/api/v1/webhook/{endpoint.token}"
    return out


@router.get("", response_model=list[EndpointOut])
async def list_endpoints(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[EndpointOut]:
    result = await db.execute(
        select(WebhookEndpoint).where(WebhookEndpoint.user_id == user.id).order_by(WebhookEndpoint.id.desc())
    )
    return [_to_out(e) for e in result.scalars().all()]


@router.post("", response_model=EndpointOut, status_code=201)
async def create_endpoint(
    payload: EndpointCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EndpointOut:
    endpoint = WebhookEndpoint(
        user_id=user.id,
        name=payload.name,
        target_type=payload.target_type,
        target_config=payload.target_config,
    )
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    return _to_out(endpoint)


async def _get_owned_endpoint(endpoint_id: int, db: AsyncSession, user: User) -> WebhookEndpoint:
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id, WebhookEndpoint.user_id == user.id
        )
    )
    endpoint = result.scalar_one_or_none()
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")
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
    endpoint_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> EndpointOut:
    endpoint = await _get_owned_endpoint(endpoint_id, db, user)
    endpoint.is_active = not endpoint.is_active
    await db.commit()
    await db.refresh(endpoint)
    return _to_out(endpoint)


@router.get("/{endpoint_id}/logs", response_model=list[AlertLogOut])
async def get_endpoint_logs(
    endpoint_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[AlertLog]:
    await _get_owned_endpoint(endpoint_id, db, user)
    result = await db.execute(
        select(AlertLog).where(AlertLog.endpoint_id == endpoint_id).order_by(AlertLog.id.desc()).limit(100)
    )
    return list(result.scalars().all())
