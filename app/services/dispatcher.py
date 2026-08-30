import asyncio
import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.core.logging import logger
from app.i18n import t

_client: httpx.AsyncClient | None = None

GREEN_API_DEFAULT = "https://api.green-api.com"
META_GRAPH_VERSION = "v21.0"
RETRY_DELAY_SECONDS = 3.0
CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"
CALLMEBOT_TIMEOUT = httpx.Timeout(20.0)
CALLMEBOT_BODY_ERROR_MARKERS = (
    "error",
    "invalid",
    "apikey",
    "failed",
    "failure",
    "not valid",
    "not_valid",
)

MSG_CALLMEBOT_MISSING = t("en", "api.callmebot_missing")
MSG_CALLMEBOT_BODY = t("en", "api.callmebot_body")
MSG_UNKNOWN_PROVIDER = t("en", "api.unknown_wa")


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


class _RetryableHTTPError(Exception):
    pass


async def _post_json(
    url: str,
    payload: dict,
    *,
    headers: dict | None = None,
    retry: bool = False,
) -> tuple[httpx.Response | None, str | None, float]:
    client = get_http_client()
    start = time.perf_counter()
    last_error: str | None = None
    attempts = 2 if retry else 1

    for attempt in range(attempts):
        if attempt > 0:
            await asyncio.sleep(RETRY_DELAY_SECONDS)
        try:
            resp = await client.post(url, json=payload, headers=headers)
            if retry and attempt == 0 and resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                continue
            return resp, None, (time.perf_counter() - start) * 1000
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.ConnectTimeout,
        ) as exc:
            last_error = str(exc)[:300]
            if not retry or attempt == attempts - 1:
                return None, last_error, (time.perf_counter() - start) * 1000
        except httpx.HTTPError as exc:
            last_error = str(exc)[:300]
            return None, last_error, (time.perf_counter() - start) * 1000

    return None, last_error, (time.perf_counter() - start) * 1000


async def _get(
    url: str,
    *,
    timeout: httpx.Timeout | None = None,
    retry: bool = False,
) -> tuple[httpx.Response | None, str | None, float]:
    client = get_http_client()
    start = time.perf_counter()
    last_error: str | None = None
    attempts = 2 if retry else 1

    for attempt in range(attempts):
        if attempt > 0:
            await asyncio.sleep(RETRY_DELAY_SECONDS)
        try:
            kwargs: dict = {}
            if timeout is not None:
                kwargs["timeout"] = timeout
            resp = await client.get(url, **kwargs)
            if retry and attempt == 0 and resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                continue
            return resp, None, (time.perf_counter() - start) * 1000
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.ConnectTimeout,
        ) as exc:
            last_error = str(exc)[:300]
            if not retry or attempt == attempts - 1:
                return None, last_error, (time.perf_counter() - start) * 1000
        except httpx.HTTPError as exc:
            last_error = str(exc)[:300]
            return None, last_error, (time.perf_counter() - start) * 1000

    return None, last_error, (time.perf_counter() - start) * 1000


async def send_telegram(
    chat_id: str,
    text: str,
    bot_token: str | None = None,
    *,
    retry: bool = False,
) -> DispatchResult:
    token = bot_token or get_settings().TELEGRAM_DEFAULT_BOT_TOKEN
    if not token:
        return DispatchResult(success=False, latency_ms=0.0, error_message="לא הוגדר קוד בוט בטלגרם")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}

    resp, error, latency_ms = await _post_json(url, payload, retry=retry)
    if error:
        logger.warning("Telegram dispatch failed: %s", error)
        return DispatchResult(success=False, latency_ms=latency_ms, error_message=error)
    if resp is not None and resp.status_code == 200:
        return DispatchResult(success=True, latency_ms=latency_ms)
    status = resp.status_code if resp is not None else "?"
    body = (resp.text if resp is not None else "")[:300]
    return DispatchResult(
        success=False, latency_ms=latency_ms, error_message=f"טלגרם החזיר {status}: {body}"
    )


def normalize_discord_webhook(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    url = url.replace("http://", "https://")
    url = url.replace("ptb.discord.com", "discord.com")
    url = url.replace("canary.discord.com", "discord.com")
    url = url.replace("discordapp.com", "discord.com")
    return url.rstrip("/")


async def send_discord(webhook_url: str, text: str, *, retry: bool = False) -> DispatchResult:
    url = normalize_discord_webhook(webhook_url)
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

    resp, error, latency_ms = await _post_json(url, {"content": text}, retry=retry)
    if error:
        logger.warning("Discord dispatch failed: %s", error)
        return DispatchResult(success=False, latency_ms=latency_ms, error_message=error)

    if resp is not None and resp.status_code in (301, 302, 307, 308):
        location = resp.headers.get("location")
        if location:
            if location.startswith("/"):
                location = str(resp.url.join(location))
            resp, error, latency_ms = await _post_json(
                normalize_discord_webhook(location), {"content": text}, retry=retry
            )
            if error:
                return DispatchResult(success=False, latency_ms=latency_ms, error_message=error)

    if resp is not None and resp.status_code in (200, 204):
        return DispatchResult(success=True, latency_ms=latency_ms)

    hint = ""
    status = resp.status_code if resp is not None else "?"
    if resp is not None and resp.status_code in (301, 302, 404, 401, 403):
        hint = " בדקו שהעתקתם Copy Webhook URL מהערוץ, לא את הכתובת של הערוץ עצמו."
    body = ((resp.text if resp is not None else "") or "").strip()[:200]
    return DispatchResult(
        success=False,
        latency_ms=latency_ms,
        error_message=f"דיסקורד החזיר {status}.{hint} {body}".strip(),
    )


def normalize_whatsapp_chat_id(raw: str) -> str:
    value = (raw or "").strip().replace(" ", "").replace("-", "")
    if not value:
        return ""
    if "@" in value:
        return value
    value = value.lstrip("+")
    if value.startswith("00"):
        value = value[2:]
    return f"{value}@c.us"


def normalize_e164(raw: str) -> str:
    value = (raw or "").strip().replace(" ", "").replace("-", "")
    return value.lstrip("+")


def normalize_callmebot_phone(raw: str) -> str:
    """Digits with country code. Israeli 05… → 9725…; +972… stays 972…"""
    value = (raw or "").strip()
    if not value:
        return ""
    if "@" in value:
        value = value.split("@", 1)[0]
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("05"):
        digits = "972" + digits[1:]
    return digits


def _callmebot_body_is_error(body: str) -> bool:
    lowered = (body or "").lower()
    if not lowered.strip():
        return False
    return any(marker in lowered for marker in CALLMEBOT_BODY_ERROR_MARKERS)


def callmebot_request_url(phone: str, text: str, apikey: str) -> str:
    return (
        f"{CALLMEBOT_URL}"
        f"?phone={quote(phone, safe='')}"
        f"&text={quote(text, safe='')}"
        f"&apikey={quote(apikey, safe='')}"
    )


async def send_whatsapp_callmebot(config: dict, text: str, *, retry: bool = False) -> DispatchResult:
    phone = normalize_callmebot_phone(
        config.get("phone") or config.get("chat_id") or config.get("to") or ""
    )
    apikey = (config.get("apikey") or config.get("api_token") or "").strip()

    if not phone or not apikey:
        return DispatchResult(success=False, latency_ms=0.0, error_message=MSG_CALLMEBOT_MISSING)

    url = callmebot_request_url(phone, text, apikey)
    resp, error, latency_ms = await _get(url, timeout=CALLMEBOT_TIMEOUT, retry=retry)
    if error:
        logger.warning("CallMeBot dispatch failed: %s", error)
        return DispatchResult(success=False, latency_ms=latency_ms, error_message=error)
    body = (resp.text if resp is not None else "") or ""
    if resp is not None and resp.status_code == 200 and not _callmebot_body_is_error(body):
        return DispatchResult(success=True, latency_ms=latency_ms)
    if resp is not None and resp.status_code == 200:
        return DispatchResult(success=False, latency_ms=latency_ms, error_message=MSG_CALLMEBOT_BODY)
    status = resp.status_code if resp is not None else "?"
    snippet = body.strip()[:200]
    return DispatchResult(
        success=False,
        latency_ms=latency_ms,
        error_message=f"וואטסאפ (CallMeBot) החזיר {status}. {snippet}".strip(),
    )


async def send_whatsapp_green_api(config: dict, text: str, *, retry: bool = False) -> DispatchResult:
    id_instance = (config.get("id_instance") or "").strip()
    api_token = (config.get("api_token") or "").strip()
    chat_id = normalize_whatsapp_chat_id(config.get("chat_id") or "")
    api_url = (config.get("api_url") or GREEN_API_DEFAULT).strip().rstrip("/")

    if not id_instance or not api_token or not chat_id:
        return DispatchResult(
            success=False,
            latency_ms=0.0,
            error_message="חסרים פרטי Green-API. צריך מזהה מופע, קוד, ומספר טלפון.",
        )

    url = f"{api_url}/waInstance{id_instance}/sendMessage/{api_token}"
    payload = {"chatId": chat_id, "message": text}
    resp, error, latency_ms = await _post_json(url, payload, retry=retry)
    if error:
        logger.warning("Green-API dispatch failed: %s", error)
        return DispatchResult(success=False, latency_ms=latency_ms, error_message=error)
    if resp is not None and resp.status_code in (200, 201):
        return DispatchResult(success=True, latency_ms=latency_ms)
    status = resp.status_code if resp is not None else "?"
    body = (resp.text if resp is not None else "")[:300]
    return DispatchResult(
        success=False,
        latency_ms=latency_ms,
        error_message=f"וואטסאפ (Green-API) החזיר {status}: {body}",
    )


async def send_whatsapp_meta(config: dict, text: str, *, retry: bool = False) -> DispatchResult:
    phone_number_id = (config.get("phone_number_id") or "").strip()
    access_token = (config.get("access_token") or "").strip()
    to = normalize_e164(config.get("to") or "")

    if not phone_number_id or not access_token or not to:
        return DispatchResult(
            success=False,
            latency_ms=0.0,
            error_message="חסרים פרטי Meta. צריך מזהה מספר, קוד גישה, ומספר נמען.",
        )

    url = f"https://graph.facebook.com/{META_GRAPH_VERSION}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    resp, error, latency_ms = await _post_json(url, payload, headers=headers, retry=retry)
    if error:
        logger.warning("Meta WhatsApp dispatch failed: %s", error)
        return DispatchResult(success=False, latency_ms=latency_ms, error_message=error)
    if resp is not None and resp.status_code in (200, 201):
        return DispatchResult(success=True, latency_ms=latency_ms)
    status = resp.status_code if resp is not None else "?"
    body = (resp.text if resp is not None else "")[:300]
    return DispatchResult(
        success=False,
        latency_ms=latency_ms,
        error_message=f"וואטסאפ (Meta) החזיר {status}: {body}",
    )


async def send_whatsapp(config: dict, text: str, *, retry: bool = False) -> DispatchResult:
    provider = (config.get("provider") or "callmebot").strip().lower().replace("-", "_")
    if provider in {"callmebot", "call_me_bot"}:
        return await send_whatsapp_callmebot(config, text, retry=retry)
    if provider in {"green_api", "greenapi"}:
        return await send_whatsapp_green_api(config, text, retry=retry)
    if provider in {"meta", "meta_cloud", "cloud"}:
        return await send_whatsapp_meta(config, text, retry=retry)
    return DispatchResult(success=False, latency_ms=0.0, error_message=MSG_UNKNOWN_PROVIDER)
