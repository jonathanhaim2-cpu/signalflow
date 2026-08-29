from tests.conftest import signup


async def test_webhook_url_uses_public_render_host(client):
    await signup(client)
    res = await client.post(
        "/api/v1/endpoints",
        json={
            "name": "ציבורי",
            "target_type": "discord",
            "target_config": {"discord_webhook_url": "http://discordapp.com/api/webhooks/1/abc"},
        },
    )
    assert res.status_code == 201, res.text
    url = res.json()["webhook_url"]
    token = res.json()["token"]
    assert url == f"https://signalflow-cl0v.onrender.com/api/v1/webhook/{token}"
    assert "localhost" not in url
    assert res.json()["target_config"]["discord_webhook_url"].startswith("••••")


async def test_app_base_url_override(client, monkeypatch, clear_settings):
    monkeypatch.setenv("APP_BASE_URL", "https://custom.example.com")
    from app.core.config import get_settings

    get_settings.cache_clear()
    await signup(client)
    res = await client.post(
        "/api/v1/endpoints",
        json={
            "name": "override",
            "target_type": "telegram",
            "target_config": {"chat_id": "9"},
        },
    )
    assert res.json()["webhook_url"].startswith("https://custom.example.com/api/v1/webhook/")


async def test_forwarded_host_beats_localhost(client):
    await signup(client)
    res = await client.post(
        "/api/v1/endpoints",
        headers={
            "Host": "localhost:8000",
            "X-Forwarded-Host": "signalflow-cl0v.onrender.com",
            "X-Forwarded-Proto": "https",
        },
        json={
            "name": "fwd",
            "target_type": "telegram",
            "target_config": {"chat_id": "1"},
        },
    )
    url = res.json()["webhook_url"]
    assert url.startswith("https://signalflow-cl0v.onrender.com/api/v1/webhook/")
    assert "localhost" not in url


async def test_discord_url_normalized_on_save(client, fake_http):
    await signup(client)
    res = await client.post(
        "/api/v1/endpoints",
        json={
            "name": "דיסקורד",
            "target_type": "discord",
            "target_config": {"discord_webhook_url": "http://discordapp.com/api/webhooks/99/xyzsecret"},
        },
    )
    token = res.json()["token"]
    await client.post(f"/api/v1/webhook/{token}", json={"action": "BUY", "ticker": "AAPL"})
    assert fake_http.calls[0]["url"] == "https://discord.com/api/webhooks/99/xyzsecret"


async def test_logs_hebrew_status_payload(client, fake_http):
    await signup(client)
    created = await client.post(
        "/api/v1/endpoints",
        json={"name": "לוג", "target_type": "telegram", "target_config": {"chat_id": "1", "bot_token": "tok"}},
    )
    endpoint_id = created.json()["id"]
    token = created.json()["token"]
    await client.post(f"/api/v1/webhook/{token}", json={"ticker": "X", "action": "BUY"})
    logs = await client.get(f"/api/v1/endpoints/{endpoint_id}/logs")
    assert logs.status_code == 200
    row = logs.json()[0]
    assert row["status"] == "delivered"
