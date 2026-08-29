from tests.conftest import signup


OWNER = "jonathanhaim2@gmail.com"


async def test_owner_signup_is_admin_and_pro(client):
    user = await signup(client, email=OWNER)
    assert user["tier"] == "pro"
    assert user["is_admin"] is True
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["is_admin"] is True
    assert me["tier"] == "pro"


async def test_admin_emails_env(client, monkeypatch, clear_settings):
    monkeypatch.setenv("ADMIN_EMAILS", "boss@example.com")
    from app.core.config import get_settings

    get_settings.cache_clear()
    user = await signup(client, email="boss@example.com")
    assert user["is_admin"] is True
    assert user["tier"] == "pro"


async def test_non_admin_admin_page_404(client):
    await signup(client, email="trader@example.com")
    res = await client.get("/admin")
    assert res.status_code == 404


async def test_anonymous_admin_redirects_login(client):
    res = await client.get("/admin", follow_redirects=False)
    assert res.status_code == 303
    assert "/login" in res.headers["location"]


async def test_admin_list_and_toggle_tier(client):
    await signup(client, email="trader2@example.com")
    await signup(client, email=OWNER)
    page = await client.get("/admin")
    assert page.status_code == 200
    html = page.text
    assert "ניהול" in html
    assert "הפוך לפרו" in html
    assert "trader2@example.com" in html
    assert "חינם" in html

    # trader2 is id 1, owner is id 2
    res = await client.post("/admin/users/1/pro", follow_redirects=False)
    assert res.status_code == 303
    page = await client.get("/admin")
    assert "הורד לחינם" in page.text

    res = await client.post("/admin/users/1/free", follow_redirects=False)
    assert res.status_code == 303


async def test_admin_create_user_shows_password_once(client):
    await signup(client, email=OWNER)
    res = await client.post(
        "/admin/users/create",
        data={"email": "newtrader@example.com", "password": ""},
    )
    assert res.status_code == 200
    assert "newtrader@example.com" in res.text
    assert "המשתמש נוצר" in res.text
    assert "font-mono" in res.text


async def test_invite_qr_and_single_use_redeem(client):
    await signup(client, email=OWNER)
    created = await client.post("/admin/invites", data={"days": "7"}, follow_redirects=False)
    assert created.status_code == 303
    location = created.headers["location"]
    assert location.startswith("/admin/invites/")
    invite_id = location.split("/")[3]

    qr = await client.get(f"/admin/invites/{invite_id}/qr.png")
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/png"
    assert qr.content[:8] == b"\x89PNG\r\n\x1a\n"

    print_page = await client.get(f"/admin/invites/{invite_id}/print")
    assert print_page.status_code == 200
    assert "הדפס / שמור" in print_page.text
    assert "SF-" in print_page.text

    admin = await client.get("/admin")
    assert "SF-" in admin.text
    # extract code from large text
    import re

    match = re.search(r"SF-[0-9A-F]{4}-[0-9A-F]{4}", admin.text)
    assert match
    code = match.group(0)

    await signup(client, email="redeemer@example.com")
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["tier"] == "free"

    redeemed = await client.get(f"/redeem/{code}")
    assert redeemed.status_code == 200
    assert "שודרג לפרו" in redeemed.text
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["tier"] == "pro"

    await signup(client, email="second@example.com")
    again = await client.get(f"/redeem/{code}")
    assert "כבר מומש" in again.text
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["tier"] == "free"


async def test_redeem_logged_out_then_login(client):
    await signup(client, email=OWNER)
    await client.post("/admin/invites", data={"days": "7"}, follow_redirects=True)
    admin = await client.get("/admin")
    import re

    code = re.search(r"SF-[0-9A-F]{4}-[0-9A-F]{4}", admin.text).group(0)
    await client.post("/api/v1/auth/logout")
    page = await client.get(f"/redeem/{code}")
    assert "להירשם או להיכנס" in page.text
    assert f"/signup?next=/redeem/{code}" in page.text


async def test_revoke_unused_code(client):
    await signup(client, email=OWNER)
    created = await client.post("/admin/invites", data={"days": "7"}, follow_redirects=False)
    invite_id = created.headers["location"].split("/")[3]
    await client.post(f"/admin/invites/{invite_id}/revoke")
    admin = await client.get("/admin")
    assert "אין קודים פתוחים" in admin.text or "בטל קוד" not in admin.text


async def test_disable_user_blocks_login(client):
    await signup(client, email="blocked@example.com", password="password1")
    await signup(client, email=OWNER)
    await client.post("/admin/users/1/disable")
    await client.post("/api/v1/auth/logout")
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "blocked@example.com", "password": "password1"},
    )
    assert res.status_code == 401
    assert "מושבת" in res.json()["detail"]


async def test_grant_pro_script_still_works(client, session_factory):
    await signup(client, email="cli@example.com")
    from app.services.plans import grant_pro

    async with session_factory() as db:
        user = await grant_pro(db, "cli@example.com")
        assert user.tier == "pro"
