from urllib.parse import urlparse

from fastapi import Request

from app.core.config import get_settings

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "test", "testserver"}


def is_local_host(host: str | None) -> bool:
    if not host:
        return True
    hostname = host.split(",")[0].strip().split(":")[0].lower()
    return hostname in _LOCAL_HOSTS or hostname.endswith(".local")


def _first_header(request: Request, name: str) -> str:
    raw = request.headers.get(name) or ""
    return raw.split(",")[0].strip()


def public_base_url(request: Request | None = None) -> str:
    """Public origin used in copied webhook URLs.

    Preference:
    1. APP_BASE_URL if set
    2. Public host from the incoming request (X-Forwarded-* / Host) — never localhost
    3. BASE_URL only when it is not localhost
    4. Local request origin (dev only)
    """
    settings = get_settings()
    override = (settings.APP_BASE_URL or "").strip().rstrip("/")
    if override:
        return override

    if request is not None:
        forwarded_host = _first_header(request, "x-forwarded-host")
        host = forwarded_host or _first_header(request, "host") or (request.url.hostname or "")
        proto = _first_header(request, "x-forwarded-proto") or (request.url.scheme or "https")
        if host and not is_local_host(host):
            if proto == "http":
                proto = "https"
            return f"{proto}://{host}".rstrip("/")

    fallback = (settings.BASE_URL or "").strip().rstrip("/")
    if fallback:
        parsed = urlparse(fallback)
        if parsed.hostname and not is_local_host(parsed.hostname):
            return fallback.rstrip("/")

    if request is not None:
        host = _first_header(request, "host") or (request.url.hostname or "localhost")
        proto = _first_header(request, "x-forwarded-proto") or request.url.scheme or "http"
        return f"{proto}://{host}".rstrip("/")

    return fallback or "http://localhost:8000"


def webhook_url_for(token: str, request: Request | None = None) -> str:
    return f"{public_base_url(request)}/api/v1/webhook/{token}"
