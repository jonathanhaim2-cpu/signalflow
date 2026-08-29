from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TelegramTargetConfig(BaseModel):
    bot_token: str | None = None
    chat_id: str


class DiscordTargetConfig(BaseModel):
    discord_webhook_url: str


class EndpointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    target_type: Literal["telegram", "discord"]
    target_config: dict[str, Any]

    @model_validator(mode="after")
    def validate_config(self) -> "EndpointCreate":
        if self.target_type == "telegram":
            TelegramTargetConfig(**self.target_config)
        else:
            DiscordTargetConfig(**self.target_config)
        return self


class EndpointOut(BaseModel):
    id: int
    name: str
    token: str
    target_type: str
    target_config: dict[str, Any]
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
