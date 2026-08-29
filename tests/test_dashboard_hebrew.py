from tests.conftest import signup


async def test_dashboard_hebrew_and_sleep_banner(client):
    await signup(client)
    page = await client.get("/dashboard")
    assert page.status_code == 200
    html = page.text
    assert 'dir="rtl"' in html or "lang=\"he\"" in html
    assert "רוצה פרו" in html
    assert "15 דקות" in html
    assert "7 דולר" in html
    assert "וואטסאפ" in html
    assert "הגיע" in html
    assert "לא הגיע" in html
    assert "העתק תבנית" in html
    assert "green-api.com" in html
    assert "הדרך הקלה — לטלפון שלי" in html
    assert "+34 694 23 41 84" in html
    assert "I allow callmebot to send me messages" in html
    assert "בלי סריקת QR" in html
    assert "Integrations" in html
    assert "{{ticker}}" in html


async def test_landing_mentions_whatsapp(client):
    page = await client.get("/")
    assert page.status_code == 200
    assert "וואטסאפ" in page.text
