from tests.conftest import signup


async def test_dashboard_hebrew_no_sleep_banner(client):
    await signup(client)
    page = await client.get("/dashboard")
    assert page.status_code == 200
    html = page.text
    assert 'dir="rtl"' in html or "lang=\"he\"" in html
    assert "רוצה פרו" in html
    assert "15 דקות" not in html
    assert "7 דולר" not in html
    assert "נרדם" not in html
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
    assert "מדריך וואטסאפ" in html
    assert "מדריך טלגרם" in html
    assert "מדריך דיסקורד" in html
    assert "$9" not in html
    assert "/api/v1/billing/checkout" in html


async def test_login_plan_cards_and_rtl_css(client):
    page = await client.get("/login")
    assert page.status_code == 200
    html = page.text
    assert "$9" in html
    assert "$0" in html
    assert "הרשמה כחינם" in html
    assert "הרשמה כפרו" in html
    assert "אין סליקה" not in html
    assert "₪" not in html
    assert "PayPlus" not in html
    css = await client.get("/static/css/app.css")
    assert css.status_code == 200
    assert "overflow-x: clip" in css.text
    assert "padding-inline" in css.text
    assert "minmax(0, 1fr)" in css.text


async def test_landing_mentions_whatsapp(client):
    page = await client.get("/")
    assert page.status_code == 200
    html = page.text
    assert "וואטסאפ" in html
    assert "חינם" in html
    assert "פרו" in html
    assert "מדריכים" in html
    assert "מחירים" in html
    assert "$9" in html
    assert "$0" in html
    assert "Paddle" in html
    assert "קבלה מחו״ל" in html
    assert "₪" not in html
    assert "PayPlus" not in html
    assert "אין סליקה" not in html
    assert "מושגים" not in html
    assert 'href="/static/css/app.css"' in html
    assert "#6366f1" not in html


async def test_guides_page(client):
    page = await client.get("/guides")
    assert page.status_code == 200
    html = page.text
    assert "I allow callmebot to send me messages" in html
    assert "+34 694 23 41 84" in html
    assert "BotFather" in html
    assert "Integrations" in html
    assert "Webhook URL" in html
    assert "green-api.com" in html
    assert "מדריכי התחברות" in html
    assert "בלי מושגים" not in html
    assert "שלב אחרי שלב" in html
