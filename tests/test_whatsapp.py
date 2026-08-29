from tests.conftest import signup


async def test_whatsapp_green_api_real_http(client, fake_http):
    await signup(client)
    res = await client.post(
        "/api/v1/endpoints",
        json={
            "name": "וואטסאפ",
            "target_type": "whatsapp",
            "target_config": {
                "provider": "green_api",
                "id_instance": "110100001",
                "api_token": "super-secret-token",
                "chat_id": "972501234567",
            },
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["target_type"] == "whatsapp"
    assert body["target_config"]["api_token"] == "••••oken"

    token = body["token"]
    sent = await client.post(
        f"/api/v1/webhook/{token}",
        json={"ticker": "BTCUSDT", "action": "BUY", "price": 67250},
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "delivered"
    assert len(fake_http.calls) == 1
    call = fake_http.calls[0]
    assert call["url"] == "https://api.green-api.com/waInstance110100001/sendMessage/super-secret-token"
    assert call["json"]["chatId"] == "972501234567@c.us"
    assert "BTCUSDT" in call["json"]["message"]
    assert "— SignalFlow" in call["json"]["message"]


async def test_whatsapp_meta_real_http(client, fake_http, session_factory):
    await signup(client, email="meta@example.com")
    from app.services.plans import grant_pro

    async with session_factory() as db:
        await grant_pro(db, "meta@example.com")

    res = await client.post(
        "/api/v1/endpoints",
        json={
            "name": "מטא",
            "target_type": "whatsapp",
            "target_config": {
                "provider": "meta",
                "phone_number_id": "10987654321",
                "access_token": "EAAB-secret",
                "to": "+972509999999",
            },
        },
    )
    assert res.status_code == 201, res.text
    token = res.json()["token"]
    sent = await client.post(
        f"/api/v1/webhook/{token}",
        json={"ticker": "ETHUSDT", "action": "SELL", "price": 3200},
    )
    assert sent.status_code == 200
    call = fake_http.calls[0]
    assert call["url"] == "https://graph.facebook.com/v21.0/10987654321/messages"
    assert call["headers"]["Authorization"] == "Bearer EAAB-secret"
    assert call["json"]["to"] == "972509999999"
    assert call["json"]["messaging_product"] == "whatsapp"
    assert call["json"]["type"] == "text"
    assert "ETHUSDT" in call["json"]["text"]["body"]
    assert "— SignalFlow" not in call["json"]["text"]["body"]


async def test_pro_retries_whatsapp_on_5xx(client, fake_http, session_factory):
    await signup(client, email="retry@example.com")
    from app.services.plans import grant_pro

    async with session_factory() as db:
        await grant_pro(db, "retry@example.com")

    fake_http.fail_times = 1
    res = await client.post(
        "/api/v1/endpoints",
        json={
            "name": "retry",
            "target_type": "whatsapp",
            "target_config": {
                "provider": "green_api",
                "id_instance": "1",
                "api_token": "tok",
                "chat_id": "97250",
            },
        },
    )
    token = res.json()["token"]
    sent = await client.post(f"/api/v1/webhook/{token}", json={"action": "ALERT"})
    assert sent.status_code == 200
    assert sent.json()["status"] == "delivered"
    assert len(fake_http.calls) == 2
