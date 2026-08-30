from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.models.webhook import WebhookEndpoint
from app.schemas.webhook import validate_target_config

ALLOWED_TYPES = ("telegram", "discord", "whatsapp")
MAX_DESTINATIONS = 3

MSG_NEED_DEST = "בחרו לפחות יעד אחד."
MSG_MAX_DEST = "אפשר לחבר עד שלושה יעדים לאותו קישור."
MSG_DUP_DEST = "כל סוג יעד יכול להופיע פעם אחת בלבד."
MSG_BAD_DEST = "סוג יעד לא נתמך"


def dest_label(target_type: str) -> str:
    return {"telegram": "טלגרם", "whatsapp": "וואטסאפ", "discord": "דיסקורד"}.get(
        target_type, target_type
    )


def _as_dest(target_type: str | None, config: dict[str, Any] | None) -> dict[str, Any] | None:
    if not target_type:
        return None
    if target_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=422, detail=MSG_BAD_DEST)
    cleaned = validate_target_config(target_type, config or {})
    return {"type": target_type, "config": cleaned}


def normalize_destinations(
    *,
    destinations: list[dict[str, Any]] | None = None,
    target_type: str | None = None,
    target_config: dict[str, Any] | None = None,
    extra_target_type: str | None = None,
    extra_target_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Accept a destinations list or legacy primary + extra fields."""
    dests: list[dict[str, Any]] = []
    if destinations:
        for raw in destinations:
            dest_type = (raw.get("type") or raw.get("target_type") or "").strip().lower()
            dest_config = raw.get("config") or raw.get("target_config") or {}
            item = _as_dest(dest_type, dest_config)
            if item:
                dests.append(item)
    else:
        primary = _as_dest(target_type, target_config)
        if primary:
            dests.append(primary)
        extra = _as_dest(extra_target_type, extra_target_config) if extra_target_type else None
        if extra:
            dests.append(extra)

    if not dests:
        raise HTTPException(status_code=422, detail=MSG_NEED_DEST)
    if len(dests) > MAX_DESTINATIONS:
        raise HTTPException(status_code=422, detail=MSG_MAX_DEST)
    types = [d["type"] for d in dests]
    if len(types) != len(set(types)):
        raise HTTPException(status_code=422, detail=MSG_DUP_DEST)
    return dests


def destinations_of(endpoint: WebhookEndpoint) -> list[dict[str, Any]]:
    stored = endpoint.destinations
    if isinstance(stored, list) and stored:
        return stored
    dests: list[dict[str, Any]] = []
    if endpoint.target_type:
        dests.append({"type": endpoint.target_type, "config": endpoint.target_config or {}})
    if endpoint.extra_target_type and endpoint.extra_target_config:
        dests.append({"type": endpoint.extra_target_type, "config": endpoint.extra_target_config})
    return dests


def apply_destinations(endpoint: WebhookEndpoint, dests: list[dict[str, Any]]) -> None:
    endpoint.destinations = dests
    first = dests[0]
    endpoint.target_type = first["type"]
    endpoint.target_config = first["config"]
    if len(dests) > 1:
        endpoint.extra_target_type = dests[1]["type"]
        endpoint.extra_target_config = dests[1]["config"]
    else:
        endpoint.extra_target_type = None
        endpoint.extra_target_config = None


def public_destinations(dests: list[dict[str, Any]], mask_config) -> list[dict[str, Any]]:
    return [{"type": d["type"], "config": mask_config(d.get("config") or {})} for d in dests]
