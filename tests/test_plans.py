from tests.conftest import signup


async def _create_telegram(client, name="ערוץ ראשון"):
    return await client.post(
        "/api/v1/endpoints",
        json={
            "name": name,
            "target_type": "telegram",
            "target_config": {"chat_id": "123", "bot_token": "tok-secret-value"},
        },
    )


async def test_free_blocked_on_second_channel(client):
    await signup(client)
    first = await _create_telegram(client)
    assert first.status_code == 201
    assert "••••" in first.json()["target_config"]["bot_token"]

    second = await _create_telegram(client, name="ערוץ שני")
    assert second.status_code == 403
    assert "ערוץ אחד" in second.json()["detail"]


async def test_free_blocked_on_fourth_alert(client, fake_http):
    await signup(client)
    created = await _create_telegram(client)
    token = created.json()["token"]

    for i in range(3):
        res = await client.post(
            f"/api/v1/webhook/{token}",
            json={"ticker": "BTCUSDT", "action": "BUY", "price": 100 + i},
        )
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "delivered"

    fourth = await client.post(
        f"/api/v1/webhook/{token}",
        json={"ticker": "BTCUSDT", "action": "SELL", "price": 1},
    )
    assert fourth.status_code == 429
    assert "3" in fourth.json()["detail"]
    assert "התראות" in fourth.json()["detail"]
    assert len(fake_http.calls) == 3


async def test_free_extra_destination_forbidden(client):
    await signup(client)
    res = await client.post(
        "/api/v1/endpoints",
        json={
            "name": "כפול",
            "target_type": "telegram",
            "target_config": {"chat_id": "1"},
            "extra_target_type": "discord",
            "extra_target_config": {"discord_webhook_url": "https://discord.com/api/webhooks/1/abc"},
        },
    )
    assert res.status_code == 403
    assert "יעד שני" in res.json()["detail"]


async def test_pro_unlimited_channels_and_alerts(client, fake_http, session_factory):
    user = await signup(client, email="prouser@example.com")
    from app.services.plans import grant_pro

    async with session_factory() as db:
        granted = await grant_pro(db, user["email"])
        assert granted is not None
        assert granted.tier == "pro"

    first = await _create_telegram(client, "אחד")
    second = await _create_telegram(client, "שניים")
    assert first.status_code == 201
    assert second.status_code == 201

    token = first.json()["token"]
    for i in range(4):
        res = await client.post(
            f"/api/v1/webhook/{token}",
            json={"ticker": "ETHUSDT", "action": "BUY", "price": i},
        )
        assert res.status_code == 200, res.text
    assert len(fake_http.calls) == 4


async def test_signup_plan_pro_sets_waitlist(client):
    res = await client.post(
        "/api/v1/auth/signup",
        json={"email": "wantpro@example.com", "password": "password1", "plan": "pro"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["tier"] == "free"
    assert body["upgrade_requested_at"]
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["tier"] == "free"
    assert me["upgrade_requested_at"]


async def test_request_pro_waitlist(client):
    await signup(client)
    res = await client.post("/api/v1/auth/request-pro")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["charged"] is False
    assert body["upgrade_requested_at"]

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    data = me.json()
    assert data["tier"] == "free"
    assert data["alerts_remaining_today"] == 3
    assert data["upgrade_requested_at"]


async def test_allow_pro_emails(client, monkeypatch, clear_settings):
    monkeypatch.setenv("ALLOW_PRO_EMAILS", "vip@example.com")
    from app.core.config import get_settings

    get_settings.cache_clear()
    await signup(client, email="vip@example.com")
    me = await client.get("/api/v1/auth/me")
    assert me.json()["tier"] == "pro"


async def test_free_footer_pro_no_footer(client, fake_http, session_factory):
    await signup(client, email="free@example.com")
    created = await _create_telegram(client)
    token = created.json()["token"]
    await client.post(f"/api/v1/webhook/{token}", json={"ticker": "BTC", "action": "BUY", "price": 1})
    assert "— SignalFlow" in fake_http.calls[0]["json"]["text"]

    await signup(client, email="paid@example.com")
    from app.services.plans import grant_pro

    async with session_factory() as db:
        await grant_pro(db, "paid@example.com")
    created = await _create_telegram(client, "פרו")
    token = created.json()["token"]
    await client.post(f"/api/v1/webhook/{token}", json={"ticker": "BTC", "action": "SELL", "price": 2})
    last_text = fake_http.calls[-1]["json"]["text"]
    assert "— SignalFlow" not in last_text


async def test_me_remaining_decreases(client, fake_http):
    await signup(client)
    created = await _create_telegram(client)
    token = created.json()["token"]
    await client.post(f"/api/v1/webhook/{token}", json={"action": "BUY"})
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["alerts_used_today"] == 1
    assert me["alerts_remaining_today"] == 2
