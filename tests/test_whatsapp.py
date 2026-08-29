from urllib.parse import parse_qs, urlparse

from tests.conftest import signup


async def test_whatsapp_callmebot_get_normalized_phone_and_footer(client, fake_http):
    await signup(client)
    res = await client.post(
        "/api/v1/endpoints",
        json={
            "name": "הטלפון שלי",
            "target_type": "whatsapp",
            "target_config": {
                "phone": "0501234567",
                "apikey": "callme-secret-key",
            },
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["target_type"] == "whatsapp"
    assert body["target_config"]["provider"] == "callmebot"
    assert body["target_config"]["phone"] == "972501234567"
    assert body["target_config"]["apikey"] == "••••-key"

    token = body["token"]
    sent = await client.post(
        f"/api/v1/webhook/{token}",
        json={"ticker": "BTCUSDT", "action": "BUY", "price": 67250},
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "delivered"
    assert len(fake_http.calls) == 1
    call = fake_http.calls[0]
    assert call["method"] == "GET"
    assert call["timeout"] is not None
    parsed = urlparse(call["url"])
    assert parsed.scheme == "https"
    assert parsed.netloc == "api.callmebot.com"
    assert parsed.path == "/whatsapp.php"
    query = parse_qs(parsed.query)
    assert query["phone"] == ["972501234567"]
    assert query["apikey"] == ["callme-secret-key"]
    message = query["text"][0]
    assert "BTCUSDT" in message
    assert "— SignalFlow" in message


async def test_whatsapp_callmebot_plus972_and_pro_no_footer(client, fake_http, session_factory):
    await signup(client, email="cmb-pro@example.com")
    from app.services.plans import grant_pro

    async with session_factory() as db:
        await grant_pro(db, "cmb-pro@example.com")

    res = await client.post(
        "/api/v1/endpoints",
        json={
            "name": "פרו וואטסאפ",
            "target_type": "whatsapp",
            "target_config": {
                "provider": "callmebot",
                "chat_id": "+972509999999",
                "api_token": "alias-key",
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
    query = parse_qs(urlparse(fake_http.calls[0]["url"]).query)
    assert query["phone"] == ["972509999999"]
    assert query["apikey"] == ["alias-key"]
    assert "ETHUSDT" in query["text"][0]
    assert "— SignalFlow" not in query["text"][0]


async def test_whatsapp_callmebot_missing_apikey_hebrew(client):
    await signup(client)
    res = await client.post(
        "/api/v1/endpoints",
        json={
            "name": "בלי קוד",
            "target_type": "whatsapp",
            "target_config": {"phone": "972501234567"},
        },
    )
    assert res.status_code == 422
    assert "קוד" in res.text
    assert "ואטסאפ" in res.text


async def test_whatsapp_callmebot_body_error_on_http_200(client, fake_http):
    await signup(client)
    res = await client.post(
        "/api/v1/endpoints",
        json={
            "name": "קוד שגוי",
            "target_type": "whatsapp",
            "target_config": {"phone": "972501111111", "apikey": "bad-key"},
        },
    )
    token = res.json()["token"]
    fake_http.status_code = 200
    fake_http.response_text = "ERROR: invalid apikey"
    sent = await client.post(
        f"/api/v1/webhook/{token}",
        json={"ticker": "BTCUSDT", "action": "ALERT"},
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["status"] == "failed"
    assert body["error_message"]
    assert any(ch >= "א" for ch in body["error_message"])


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


async def test_callmebot_dispatch_missing_credentials_hebrew():
    from app.services.dispatcher import send_whatsapp

    result = await send_whatsapp({}, "בדיקה")
    assert result.success is False
    assert result.error_message
    assert "טלפון" in result.error_message
    assert "קוד" in result.error_message
    assert "WhatsApp" not in result.error_message
    assert "apikey" not in result.error_message.lower()
