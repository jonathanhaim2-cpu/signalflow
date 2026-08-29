SECRET_KEYS = {
    "bot_token",
    "api_token",
    "access_token",
    "discord_webhook_url",
    "apitokeninstance",
    "token",
}


def mask_secret(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return text
    if len(text) <= 8:
        return "••••••••"
    return f"••••{text[-4:]}"


def mask_config(config: dict | None) -> dict:
    if not config:
        return {}
    masked: dict = {}
    for key, value in config.items():
        if value and str(key).lower() in SECRET_KEYS:
            masked[key] = mask_secret(str(value))
        else:
            masked[key] = value
    return masked
