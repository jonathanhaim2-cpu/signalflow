import json
import time

from app.services.billing import paddle_signature
from tests.conftest import signup


def _paddle_env(monkeypatch):
    monkeypatch.setenv("PADDLE_API_KEY", "pdl_test_api_key")
    monkeypatch.setenv("PADDLE_WEBHOOK_SECRET", "pdl_ntfset_test_secret")
    monkeypatch.setenv("PADDLE_PRICE_ID", "pri_01testpriceid000000000000")
    monkeypatch.setenv("PADDLE_SANDBOX", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()


def _signed_headers(body: bytes, secret: str = "pdl_ntfset_test_secret") -> dict[str, str]:
    ts = str(int(time.time()))
    return {
        "Content-Type": "application/json",
        "Paddle-Signature": f"ts={ts};h1={paddle_signature(ts, body, secret)}",
    }


async def test_checkout_requires_auth(client):
    res = await client.post("/api/v1/billing/checkout")
    assert res.status_code == 401


async def test_checkout_missing_keys_error(client):
    await signup(client)
    res = await client.post("/api/v1/billing/checkout")
    assert res.status_code == 503
    assert res.json()["detail"] == "Billing is not configured yet."

    he = await client.post("/api/v1/billing/checkout", params={"lang": "he"})
    assert he.status_code == 503
    assert he.json()["detail"] == "סליקה לא הוגדרה עדיין"


async def test_checkout_creates_paddle_transaction(client, monkeypatch, clear_settings):
    _paddle_env(monkeypatch)
    captured = {}

    async def fake_request(path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return {
            "data": {
                "id": "txn_01testtransaction000000000",
                "checkout": {"url": "https://sandbox-checkout.paddle.com/?_ptxn=txn_01testtransaction000000000"},
            }
        }

    monkeypatch.setattr("app.services.billing.paddle_request", fake_request)
    user = await signup(client, email="payer@example.com")
    res = await client.post("/api/v1/billing/checkout")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["url"].startswith("https://sandbox-checkout.paddle.com/")
    assert captured["path"] == "transactions"
    payload = captured["payload"]
    assert payload["collection_mode"] == "automatic"
    assert payload["currency_code"] == "USD"
    assert payload["items"] == [{"price_id": "pri_01testpriceid000000000000", "quantity": 1}]
    assert payload["custom_data"]["user_id"] == str(user["id"])
    assert payload["checkout"]["url"].endswith("/dashboard")


async def test_paddle_webhook_grants_pro(client, monkeypatch, clear_settings, session_factory):
    _paddle_env(monkeypatch)
    user = await signup(client, email="charged@example.com")
    payload = {
        "event_type": "transaction.completed",
        "data": {
            "id": "txn_01grant000000000000000000",
            "status": "completed",
            "customer_id": "ctm_01customer00000000000000",
            "subscription_id": "sub_01sub0000000000000000000",
            "custom_data": {"user_id": str(user["id"])},
        },
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    res = await client.post("/api/v1/billing/paddle", content=raw, headers=_signed_headers(raw))
    assert res.status_code == 200, res.text
    assert res.json()["action"] == "grant"
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["tier"] == "pro"
    async with session_factory() as db:
        from sqlalchemy import select

        from app.models.user import User

        stored = (await db.execute(select(User).where(User.email == "charged@example.com"))).scalar_one()
        assert stored.paddle_subscription_id == "sub_01sub0000000000000000000"
        assert stored.paddle_customer_id == "ctm_01customer00000000000000"
        assert stored.manual_pro is False


async def test_subscription_canceled_reverts_free(client, monkeypatch, clear_settings, session_factory):
    _paddle_env(monkeypatch)
    await signup(client, email="later@example.com")
    from sqlalchemy import select

    from app.models.user import User, UserTier

    async with session_factory() as db:
        stored = (await db.execute(select(User).where(User.email == "later@example.com"))).scalar_one()
        stored.tier = UserTier.PRO.value
        stored.manual_pro = False
        stored.paddle_subscription_id = "sub_01cancelfree00000000000"
        await db.commit()

    payload = {
        "event_type": "subscription.canceled",
        "data": {"id": "sub_01cancelfree00000000000", "status": "canceled"},
    }
    raw = json.dumps(payload).encode()
    res = await client.post("/api/v1/billing/paddle", content=raw, headers=_signed_headers(raw))
    assert res.status_code == 200
    assert res.json()["action"] == "revoke"
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["tier"] == "free"


async def test_subscription_created_grants_pro(client, monkeypatch, clear_settings):
    _paddle_env(monkeypatch)
    user = await signup(client, email="activated@example.com")
    payload = {
        "event_type": "subscription.activated",
        "data": {
            "id": "sub_01activated00000000000000",
            "status": "active",
            "custom_data": {"user_id": str(user["id"])},
        },
    }
    raw = json.dumps(payload).encode()
    res = await client.post("/api/v1/billing/paddle", content=raw, headers=_signed_headers(raw))
    assert res.status_code == 200
    assert res.json()["action"] == "grant"
    assert (await client.get("/api/v1/auth/me")).json()["tier"] == "pro"


async def test_manual_pro_not_revoked_by_paddle(client, monkeypatch, clear_settings, session_factory):
    _paddle_env(monkeypatch)
    await signup(client, email="manual@example.com")
    from app.services.plans import grant_pro

    async with session_factory() as db:
        granted = await grant_pro(db, "manual@example.com")
        assert granted.manual_pro is True
        granted.paddle_subscription_id = "sub_01manual0000000000000000"
        await db.commit()

    payload = {
        "event_type": "subscription.canceled",
        "data": {"id": "sub_01manual0000000000000000", "status": "canceled"},
    }
    raw = json.dumps(payload).encode()
    res = await client.post("/api/v1/billing/paddle", content=raw, headers=_signed_headers(raw))
    assert res.status_code == 200
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["tier"] == "pro"


async def test_bad_signature_rejected(client, monkeypatch, clear_settings):
    _paddle_env(monkeypatch)
    await signup(client, email="sig@example.com")
    payload = {"event_type": "transaction.completed", "data": {"custom_data": {"user_id": "1"}}}
    raw = json.dumps(payload).encode()
    res = await client.post(
        "/api/v1/billing/paddle",
        content=raw,
        headers={"Content-Type": "application/json", "Paddle-Signature": "ts=1;h1=deadbeef"},
    )
    assert res.status_code == 400
    assert "signature" in res.json()["detail"].lower()


async def test_already_pro_cannot_checkout(client, monkeypatch, clear_settings, session_factory):
    _paddle_env(monkeypatch)
    await signup(client, email="haspro@example.com")
    from app.services.plans import grant_pro

    async with session_factory() as db:
        await grant_pro(db, "haspro@example.com")
    res = await client.post("/api/v1/billing/checkout")
    assert res.status_code == 400
    assert "Pro" in res.json()["detail"]
