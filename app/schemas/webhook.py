from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


TargetLiteral = Literal["telegram", "discord", "whatsapp"]


class TelegramTargetConfig(BaseModel):
    bot_token: str | None = None
    chat_id: str


class DiscordTargetConfig(BaseModel):
    discord_webhook_url: str


class WhatsAppTargetConfig(BaseModel):
    provider: Literal["callmebot", "green_api", "meta"] = "callmebot"
    # CallMeBot — alerts to the same phone that activated the bot
    phone: str | None = None
    apikey: str | None = None
    # Green-API
    id_instance: str | None = None
    api_token: str | None = None
    chat_id: str | None = None
    api_url: str | None = None
    # Meta Cloud API
    phone_number_id: str | None = None
    access_token: str | None = None
    to: str | None = None

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> str:
        if value is None or str(value).strip() == "":
            return "callmebot"
        key = str(value).strip().lower().replace("-", "_")
        aliases = {
            "callmebot": "callmebot",
            "call_me_bot": "callmebot",
            "green_api": "green_api",
            "greenapi": "green_api",
            "meta": "meta",
            "meta_cloud": "meta",
            "cloud": "meta",
        }
        return aliases.get(key, key)

    @model_validator(mode="after")
    def validate_provider_fields(self) -> "WhatsAppTargetConfig":
        if self.provider == "callmebot":
            phone = self.phone or self.chat_id or self.to
            key = self.apikey or self.api_token
            if not (phone and key):
                raise ValueError("חסרים מספר טלפון וקוד שקיבלתם בואטסאפ")
        elif self.provider == "green_api":
            if not (self.id_instance and self.api_token and self.chat_id):
                raise ValueError("חסרים פרטי Green-API: מזהה מופע, קוד, ומספר טלפון")
        elif self.provider == "meta":
            if not (self.phone_number_id and self.access_token and self.to):
                raise ValueError("חסרים פרטי Meta: מזהה מספר, קוד גישה, ומספר נמען")
        return self


def validate_target_config(target_type: str, config: dict[str, Any]) -> dict[str, Any]:
    if target_type == "telegram":
        return TelegramTargetConfig(**config).model_dump()
    if target_type == "discord":
        return DiscordTargetConfig(**config).model_dump()
    if target_type == "whatsapp":
        return WhatsAppTargetConfig(**config).model_dump()
    raise ValueError("סוג יעד לא נתמך")


class EndpointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    target_type: TargetLiteral
    target_config: dict[str, Any]
    extra_target_type: TargetLiteral | None = None
    extra_target_config: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_config(self) -> "EndpointCreate":
        validate_target_config(self.target_type, self.target_config)
        if self.extra_target_type:
            validate_target_config(self.extra_target_type, self.extra_target_config or {})
        return self


class EndpointOut(BaseModel):
    id: int
    name: str
    token: str
    target_type: str
    target_config: dict[str, Any]
    extra_target_type: str | None = None
    extra_target_config: dict[str, Any] | None = None
    is_active: bool
    created_at: datetime
    webhook_url: str | None = None

    model_config = {"from_attributes": True}


class AlertLogOut(BaseModel):
    id: int
    endpoint_id: int
    payload_raw: str
    status: str
    latency_ms: float
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TradingViewAlert(BaseModel):
    """Standard schema SignalFlow understands. All fields optional to be lenient with TradingView payloads."""

    ticker: str | None = None
    action: str | None = None
    price: float | str | None = None
    timeframe: str | None = None
    stop_loss: float | str | None = None
    take_profit: float | str | None = None
    message: str | None = None
    strategy_name: str | None = None
