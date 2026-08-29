import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.alert_log import AlertLog, AlertStatus
from app.models.user import User
from app.models.webhook import TargetType, WebhookEndpoint
from app.services.dispatcher import send_discord, send_telegram, send_whatsapp
from app.services.formatter import (
    format_discord_markdown,
    format_telegram_html,
    format_whatsapp_text,
    parse_alert_payload,
)
from app.services.plans import apply_footer, is_pro


async def _dispatch_one(
    target_type: str,
    target_config: dict,
    alert,
    user: User | None,
    *,
    retry: bool,
):
    config = target_config or {}
    if target_type == TargetType.TELEGRAM.value:
        text = apply_footer(format_telegram_html(alert), user, html=True)
        return await send_telegram(
            chat_id=config.get("chat_id", ""),
            text=text,
            bot_token=config.get("bot_token") or None,
            retry=retry,
        )
    if target_type == TargetType.WHATSAPP.value:
        text = apply_footer(format_whatsapp_text(alert), user, html=False)
        return await send_whatsapp(config, text, retry=retry)

    text = apply_footer(format_discord_markdown(alert), user, html=False)
    return await send_discord(
        webhook_url=config.get("discord_webhook_url", ""),
        text=text,
        retry=retry,
    )


async def relay_alert(
    db: AsyncSession,
    endpoint: WebhookEndpoint,
    raw_body: bytes,
    content_type: str | None,
    user: User | None = None,
) -> AlertLog:
    """Format and dispatch an incoming alert, then persist the delivery log. Never raises."""
    start = time.perf_counter()
    payload_text = raw_body.decode("utf-8", errors="replace")[:4000]
    retry = is_pro(user)

    try:
        alert = parse_alert_payload(raw_body, content_type)
        result = await _dispatch_one(
            endpoint.target_type, endpoint.target_config or {}, alert, user, retry=retry
        )
        error_parts = []
        success = result.success
        if not result.success and result.error_message:
            error_parts.append(result.error_message)

        if endpoint.extra_target_type and endpoint.extra_target_config:
            extra = await _dispatch_one(
                endpoint.extra_target_type,
                endpoint.extra_target_config,
                alert,
                user,
                retry=retry,
            )
            success = success and extra.success
            if not extra.success and extra.error_message:
                error_parts.append(f"יעד נוסף: {extra.error_message}")

        total_latency_ms = (time.perf_counter() - start) * 1000
        log = AlertLog(
            endpoint_id=endpoint.id,
            payload_raw=payload_text,
            status=AlertStatus.DELIVERED.value if success else AlertStatus.FAILED.value,
            latency_ms=round(total_latency_ms, 2),
            error_message="; ".join(error_parts) or None,
        )
    except Exception as exc:  # noqa: BLE001 - relay must never crash the request path
        total_latency_ms = (time.perf_counter() - start) * 1000
        logger.exception("Unexpected error relaying alert for endpoint %s", endpoint.id)
        log = AlertLog(
            endpoint_id=endpoint.id,
            payload_raw=payload_text,
            status=AlertStatus.FAILED.value,
            latency_ms=round(total_latency_ms, 2),
            error_message=f"שגיאה פנימית: {exc}"[:300],
        )

    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log
