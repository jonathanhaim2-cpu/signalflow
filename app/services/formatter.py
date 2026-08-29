from app.schemas.webhook import TradingViewAlert

ACTION_EMOJI = {
    "BUY": "🟢",
    "LONG": "🟢",
    "SELL": "🔴",
    "SHORT": "🔴",
    "ALERT": "🟡",
    "CLOSE": "⚪",
}


def _emoji_for_action(action: str | None) -> str:
    if not action:
        return "🔔"
    return ACTION_EMOJI.get(action.strip().upper(), "🔔")


def format_telegram_html(alert: TradingViewAlert) -> str:
    """Rich HTML-formatted message for Telegram's parse_mode=HTML."""
    action = (alert.action or "ALERT").strip().upper()
    emoji = _emoji_for_action(action)

    lines = [f"{emoji} <b>{action}</b>" + (f" — <b>{alert.ticker}</b>" if alert.ticker else "")]

    if alert.strategy_name:
        lines.append(f"📊 Strategy: <i>{alert.strategy_name}</i>")
    if alert.timeframe:
        lines.append(f"⏱ Timeframe: {alert.timeframe}")
    if alert.price is not None:
        lines.append(f"💰 Price: <code>{alert.price}</code>")
    if alert.stop_loss is not None:
        lines.append(f"🛑 Stop Loss: <code>{alert.stop_loss}</code>")
    if alert.take_profit is not None:
        lines.append(f"🎯 Take Profit: <code>{alert.take_profit}</code>")
    if alert.message:
        lines.append(f"\n📝 {alert.message}")

    return "\n".join(lines)


def format_discord_markdown(alert: TradingViewAlert) -> str:
    action = (alert.action or "ALERT").strip().upper()
    emoji = _emoji_for_action(action)

    lines = [f"{emoji} **{action}**" + (f" — **{alert.ticker}**" if alert.ticker else "")]

    if alert.strategy_name:
        lines.append(f"📊 Strategy: *{alert.strategy_name}*")
    if alert.timeframe:
        lines.append(f"⏱ Timeframe: {alert.timeframe}")
    if alert.price is not None:
        lines.append(f"💰 Price: `{alert.price}`")
    if alert.stop_loss is not None:
        lines.append(f"🛑 Stop Loss: `{alert.stop_loss}`")
    if alert.take_profit is not None:
        lines.append(f"🎯 Take Profit: `{alert.take_profit}`")
    if alert.message:
        lines.append(f"\n📝 {alert.message}")

    return "\n".join(lines)


def parse_alert_payload(raw_body: bytes, content_type: str | None) -> TradingViewAlert:
    """Parse JSON payload; fall back to treating the whole body as a plain-text message."""
    import json

    text = raw_body.decode("utf-8", errors="replace").strip()

    if content_type and "application/json" in content_type:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return TradingViewAlert(**data)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    else:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return TradingViewAlert(**data)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return TradingViewAlert(message=text or "(empty alert)")
