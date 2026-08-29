import time
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logging import logger

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


@dataclass
class DispatchResult:
    success: bool
    latency_ms: float
    error_message: str | None = None


async def send_telegram(chat_id: str, text: str, bot_token: str | None = None) -> DispatchResult:
    token = bot_token or settings.TELEGRAM_DEFAULT_BOT_TOKEN
    if not token:
        return DispatchResult(success=False, latency_ms=0.0, error_message="No Telegram bot token configured")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}

    start = time.perf_counter()
    try:
        client = get_http_client()
        resp = await client.post(url, json=payload)
        latency_ms = (time.perf_counter() - start) * 1000
        if resp.status_code == 200:
            return DispatchResult(success=True, latency_ms=latency_ms)
        return DispatchResult(
            success=False, latency_ms=latency_ms, error_message=f"Telegram API {resp.status_code}: {resp.text[:300]}"
        )
    except httpx.HTTPError as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.warning("Telegram dispatch failed: %s", exc)
        return DispatchResult(success=False, latency_ms=latency_ms, error_message=str(exc)[:300])


def _normalize_discord_webhook(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    url = url.replace("http://", "https://")
    url = url.replace("ptb.discord.com", "discord.com")
    url = url.replace("canary.discord.com", "discord.com")
    url = url.replace("discordapp.com", "discord.com")
    return url.rstrip("/")


async def send_discord(webhook_url: str, text: str) -> DispatchResult:
    url = _normalize_discord_webhook(webhook_url)
    start = time.perf_counter()
    if not url:
        return DispatchResult(
            success=False,
            latency_ms=0.0,
            error_message="חסר קישור דיסקורד. צריך קישור Webhook מהערוץ, לא קישור רגיל לערוץ.",
        )
    if "/api/webhooks/" not in url:
        return DispatchResult(
            success=False,
            latency_ms=0.0,
            error_message="זה לא קישור Webhook. בדיסקורד: הגדרות ערוץ → Integrations → Webhooks → Copy Webhook URL.",
        )
    try:
        client = get_http_client()
        resp = await client.post(url, json={"content": text})
        if resp.status_code in (301, 302, 307, 308):
            location = resp.headers.get("location")
            if location:
                if location.startswith("/"):
                    location = str(resp.url.join(location))
                resp = await client.post(_normalize_discord_webhook(location), json={"content": text})
        latency_ms = (time.perf_counter() - start) * 1000
        if resp.status_code in (200, 204):
            return DispatchResult(success=True, latency_ms=latency_ms)
        hint = ""
        if resp.status_code in (301, 302, 404, 401, 403):
            hint = " בדקו שהעתקתם Copy Webhook URL מהערוץ, לא את הכתובת של הערוץ עצמו."
        body = (resp.text or "").strip()[:200]
        return DispatchResult(
            success=False,
            latency_ms=latency_ms,
            error_message=f"דיסקורד החזיר {resp.status_code}.{hint} {body}".strip(),
        )
    except httpx.HTTPError as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.warning("Discord dispatch failed: %s", exc)
        return DispatchResult(success=False, latency_ms=latency_ms, error_message=str(exc)[:300])
