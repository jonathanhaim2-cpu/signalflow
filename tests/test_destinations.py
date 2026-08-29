from tests.conftest import signup


async def _create(client, **kwargs):
    return await client.post("/api/v1/endpoints", json=kwargs)


async def test_free_multi_destination_allowed(client):
    await signup(client)
    res = await _create(
        client,
        name="כולם",
        destinations=[
            {"type": "telegram", "config": {"chat_id": "1", "bot_token": "tok-secret-value"}},
            {"type": "discord", "config": {"discord_webhook_url": "https://discord.com/api/webhooks/1/abc"}},
            {"type": "whatsapp", "config": {"phone": "972501234567", "apikey": "wa-secret"}},
        ],
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["target_type"] == "telegram"
    assert body["extra_target_type"] == "discord"
    assert len(body["destinations"]) == 3
    types = [d["type"] for d in body["destinations"]]
    assert types == ["telegram", "discord", "whatsapp"]
    assert "••••" in body["destinations"][0]["config"]["bot_token"]


async def test_legacy_primary_plus_extra_becomes_destinations(client):
    await signup(client)
    res = await _create(
        client,
        name="ישן",
        target_type="telegram",
        target_config={"chat_id": "9", "bot_token": "legacy-token"},
        extra_target_type="discord",
        extra_target_config={"discord_webhook_url": "https://discord.com/api/webhooks/9/xyz"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert [d["type"] for d in body["destinations"]] == ["telegram", "discord"]
    assert body["target_type"] == "telegram"
    assert body["extra_target_type"] == "discord"


async def test_multi_destination_relay_hits_all(client, fake_http):
    await signup(client)
    created = await _create(
        client,
        name="פיצול",
        destinations=[
            {"type": "telegram", "config": {"chat_id": "1", "bot_token": "t"}},
            {"type": "discord", "config": {"discord_webhook_url": "https://discord.com/api/webhooks/1/abc"}},
            {"type": "whatsapp", "config": {"phone": "0501234567", "apikey": "k"}},
        ],
    )
    token = created.json()["token"]
    sent = await client.post(
        f"/api/v1/webhook/{token}",
        json={"ticker": "BTCUSDT", "action": "BUY", "price": 1},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "delivered"
    assert sent.json()["error_message"] is None
    methods = [c["method"] for c in fake_http.calls]
    urls = [c["url"] for c in fake_http.calls]
    assert methods.count("POST") == 2
    assert methods.count("GET") == 1
    assert any("api.telegram.org" in u for u in urls)
    assert any("discord.com/api/webhooks" in u for u in urls)
    assert any("api.callmebot.com" in u for u in urls)


async def test_partial_failure_still_sends_others(client, fake_http):
    await signup(client)
    created = await _create(
        client,
        name="חלקי",
        destinations=[
            {"type": "telegram", "config": {"chat_id": "1", "bot_token": "t"}},
            {"type": "discord", "config": {"discord_webhook_url": "https://discord.com/api/webhooks/1/abc"}},
        ],
    )
    token = created.json()["token"]
    fake_http.fail_times = 1
    sent = await client.post(
        f"/api/v1/webhook/{token}",
        json={"ticker": "ETHUSDT", "action": "SELL", "price": 2},
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["status"] == "delivered"
    assert "טלגרם" in (body["error_message"] or "")
    assert len(fake_http.calls) == 2


async def test_duplicate_destination_rejected(client):
    await signup(client)
    res = await _create(
        client,
        name="כפול",
        destinations=[
            {"type": "telegram", "config": {"chat_id": "1"}},
            {"type": "telegram", "config": {"chat_id": "2"}},
        ],
    )
    assert res.status_code == 422
