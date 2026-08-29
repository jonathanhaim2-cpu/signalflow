import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.alert_log import AlertLog, AlertStatus
from app.models.webhook import TargetType, WebhookEndpoint
from app.services.dispatcher import send_discord, send_telegram
from app.services.formatter import format_discord_markdown, format_telegram_html, parse_alert_payload


async def relay_alert(
    db: AsyncSession,
    endpoint: WebhookEndpoint,
    raw_body: bytes,
    content_type: str | None,
) -> AlertLog:
    """Format and dispatch an incoming alert, then persist the delivery log. Never raises."""
    start = time.perf_counter()
    payload_text = raw_body.decode("utf-8", errors="replace")[:4000]

    try:
        alert = parse_alert_payload(raw_body, content_type)

        if endpoint.target_type == TargetType.TELEGRAM.value:
            text = format_telegram_html(alert)
            result = await send_telegram(
                chat_id=endpoint.target_config.get("chat_id", ""),
                text=text,
                bot_token=endpoint.target_config.get("bot_token") or None,
            )
        else:
            text = format_discord_markdown(alert)
            result = await send_discord(
                webhook_url=endpoint.target_config.get("discord_webhook_url", ""),
                text=text,
            )

        total_latency_ms = (time.perf_counter() - start) * 1000
        log = AlertLog(
            endpoint_id=endpoint.id,
            payload_raw=payload_text,
            status=AlertStatus.DELIVERED.value if result.success else AlertStatus.FAILED.value,
            latency_ms=round(total_latency_ms, 2),
            error_message=result.error_message,
        )
    except Exception as exc:  # noqa: BLE001 - relay must never crash the request path
        total_latency_ms = (time.perf_counter() - start) * 1000
        logger.exception("Unexpected error relaying alert for endpoint %s", endpoint.id)
        log = AlertLog(
            endpoint_id=endpoint.id,
            payload_raw=payload_text,
            status=AlertStatus.FAILED.value,
            latency_ms=round(total_latency_ms, 2),
            error_message=f"Internal error: {exc}"[:300],
        )

    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log
