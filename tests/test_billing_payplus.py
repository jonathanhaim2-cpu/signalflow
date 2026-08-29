import json

from app.services.billing import PRO_PRICE_ILS, payplus_hash
from tests.conftest import signup


def _payplus_env(monkeypatch, clear_settings):
    monkeypatch.setenv("PAYPLUS_API_KEY", "test-api-key")
    monkeypatch.setenv("PAYPLUS_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("PAYPLUS_PAYMENT_PAGE_UID", "page-uid-123")
    monkeypatch.setenv("PAYPLUS_TERMINAL_UID", "term-uid-9")
    monkeypatch.setenv("PAYPLUS_USE_STAGING", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()


async def test_checkout_requires_auth(client):
    res = await client.post("/api/v1/billing/checkout")
    assert res.status_code == 401


async def test_checkout_missing_keys_hebrew_error(client):
    await signup(client)
    res = await client.post("/api/v1/billing/checkout")
    assert res.status_code == 503
    assert res.json()["detail"] == "סליקה לא הוגדרה עדיין"


async def test_checkout_creates_payplus_link(client, monkeypatch, clear_settings):
    _payplus_env(monkeypatch, clear_settings)
    captured = {}

    async def fake_request(path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return {
            "results": {"status": "success", "code": 0},
            "data": {
                "page_request_uid": "req-uid-1",
                "payment_page_link": "https://paymentsdev.payplus.co.il/req-uid-1",
            },
        }

    monkeypatch.setattr("app.services.billing.payplus_request", fake_request)
    user = await signup(client, email="payer@example.com")
    res = await client.post("/api/v1/billing/checkout")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["url"] == "https://paymentsdev.payplus.co.il/req-uid-1"
    assert captured["path"] == "PaymentPages/generateLink"
    payload = captured["payload"]
    assert payload["charge_method"] == 3
    assert payload["currency_code"] == "ILS"
    assert payload["amount"] == PRO_PRICE_ILS == 39
    assert payload["recurring_settings"]["recurring_type"] == 2
    assert payload["recurring_settings"]["recurring_range"] == 1
    assert payload["recurring_settings"]["number_of_charges"] == 0
    assert payload["terminal_uid"] == "term-uid-9"
    assert "credit-card" in payload["allowed_charge_methods"]
    assert "bit" in payload["allowed_charge_methods"]
    assert payload["more_info"] == str(user["id"])
    assert payload["customer"]["email"] == "payer@example.com"
    assert payload["refURL_callback"].endswith("/api/v1/billing/payplus")
    assert "/dashboard" in payload["refURL_success"]


async def test_payplus_callback_grants_pro(client, monkeypatch, clear_settings, session_factory):
    _payplus_env(monkeypatch, clear_settings)
    user = await signup(client, email="charged@example.com")
    payload = {
        "transaction_type": "Charge",
        "transaction": {
            "status_code": "000",
            "more_info": str(user["id"]),
            "more_info_1": "charged@example.com",
            "recurring_charge_information": {"recurring_uid": "rec-1"},
        },
        "data": {"customer_uid": "cust-1"},
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    digest = payplus_hash(raw, "test-secret-key")
    res = await client.post(
        "/api/v1/billing/payplus",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "hash": digest,
            "user-agent": "PayPlus",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["action"] == "grant"
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["tier"] == "pro"
    async with session_factory() as db:
        from sqlalchemy import select

        from app.models.user import User

        stored = (await db.execute(select(User).where(User.email == "charged@example.com"))).scalar_one()
        assert stored.payplus_recurring_uid == "rec-1"
        assert stored.payplus_customer_uid == "cust-1"
        assert stored.manual_pro is False


async def test_payplus_callback_failure_reverts_free(client, monkeypatch, clear_settings, session_factory):
    _payplus_env(monkeypatch, clear_settings)
    await signup(client, email="later@example.com")
    from app.models.user import User, UserTier
    from sqlalchemy import select

    async with session_factory() as db:
        stored = (await db.execute(select(User).where(User.email == "later@example.com"))).scalar_one()
        stored.tier = UserTier.PRO.value
        stored.manual_pro = False
        stored.payplus_recurring_uid = "rec-fail"
        await db.commit()
        user_id = stored.id

    payload = {
        "transaction_type": "Charge",
        "status": "rejected",
        "transaction": {"status_code": "003", "more_info": str(user_id)},
    }
    res = await client.post("/api/v1/billing/payplus", json=payload)
    assert res.status_code == 200
    assert res.json()["action"] == "revoke"
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["tier"] == "free"


async def test_manual_pro_not_revoked_by_payplus(client, monkeypatch, clear_settings, session_factory):
    _payplus_env(monkeypatch, clear_settings)
    await signup(client, email="manual@example.com")
    from app.services.plans import grant_pro

    async with session_factory() as db:
        granted = await grant_pro(db, "manual@example.com")
        assert granted.manual_pro is True

    payload = {
        "transaction_type": "Cancel",
        "transaction": {"status_code": "003", "more_info_1": "manual@example.com"},
    }
    res = await client.post("/api/v1/billing/payplus", json=payload)
    assert res.status_code == 200
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["tier"] == "pro"


async def test_already_pro_cannot_checkout(client, monkeypatch, clear_settings, session_factory):
    _payplus_env(monkeypatch, clear_settings)
    await signup(client, email="haspro@example.com")
    from app.services.plans import grant_pro

    async with session_factory() as db:
        await grant_pro(db, "haspro@example.com")
    res = await client.post("/api/v1/billing/checkout")
    assert res.status_code == 400
    assert "פרו" in res.json()["detail"]
