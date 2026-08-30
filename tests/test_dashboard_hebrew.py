from tests.conftest import signup

PUBLIC = ("/", "/signup", "/login", "/guides", "/pricing", "/terms", "/privacy", "/refunds")

BANNED = (
    "מחו״ל",
    'מחו"ל',
    "קבלה מחו",
    "חשבונית זרה",
    "foreign invoice",
    "foreign receipt",
    "foreign receipts",
    "תנסו מחר",
    "try again tomorrow",
    "try tomorrow",
)


def _assert_no_banned(html: str, path: str) -> None:
    lower = html.lower()
    for phrase in BANNED:
        assert phrase.lower() not in lower, f"{phrase!r} found on {path}"


async def test_default_language_is_english_ltr(client):
    page = await client.get("/")
    assert page.status_code == 200
    html = page.text
    assert 'lang="en"' in html
    assert 'dir="ltr"' in html
    assert "Billed securely with Paddle. Cancel anytime." in html
    assert "Sign up" in html
    assert "Guides" in html
    assert "הרשמה" not in html
    assert "מדריכים" not in html
    _assert_no_banned(html, "/")


async def test_hebrew_via_query_is_rtl_and_sets_cookie(client):
    page = await client.get("/?lang=he")
    assert page.status_code == 200
    html = page.text
    assert 'lang="he"' in html
    assert 'dir="rtl"' in html
    assert "התשלום מאובטח ב-Paddle. אפשר לבטל בכל עת." in html
    assert "מדריכים" in html
    assert "Billed securely with Paddle" not in html
    _assert_no_banned(html, "/?lang=he")
    assert client.cookies.get("sf_lang") == "he"

    again = await client.get("/")
    assert 'lang="he"' in again.text
    assert 'dir="rtl"' in again.text


async def test_public_pages_both_langs_200(client):
    for path in PUBLIC:
        en = await client.get(f"{path}?lang=en")
        assert en.status_code == 200, path
        assert 'lang="en"' in en.text
        assert 'dir="ltr"' in en.text
        _assert_no_banned(en.text, path)

        he = await client.get(f"{path}?lang=he")
        assert he.status_code == 200, path
        assert 'lang="he"' in he.text
        assert 'dir="rtl"' in he.text
        _assert_no_banned(he.text, f"{path}?lang=he")
        assert 'class="lang-switch"' in en.text
        assert 'class="lang-switch"' in he.text


async def test_signup_billing_copy(client):
    page = await client.get("/signup")
    html = page.text
    assert "$9" in html
    assert "Billed securely with Paddle. Cancel anytime." in html
    assert "Paddle מוציא" not in html
    assert "₪" not in html
    he = (await client.get("/signup?lang=he")).text
    assert "התשלום מאובטח ב-Paddle. אפשר לבטל בכל עת." in he


async def test_login_plan_cards_and_rtl_css(client):
    page = await client.get("/login")
    assert page.status_code == 200
    html = page.text
    assert "$9" in html
    assert "$0" in html
    assert "Start free" in html
    assert "Start Pro" in html
    assert "אין סליקה" not in html
    assert "₪" not in html
    assert "PayPlus" not in html
    css = await client.get("/static/css/app.css")
    assert css.status_code == 200
    assert "overflow-x: clip" in css.text
    assert "padding-inline" in css.text
    assert "minmax(0, 1fr)" in css.text
    assert ".lang-switch" in css.text


async def test_landing_mentions_channels(client):
    page = await client.get("/")
    html = page.text
    assert "WhatsApp" in html
    assert "Telegram" in html
    assert "Free" in html
    assert "Pro" in html
    assert "Guides" in html
    assert "Pricing" in html
    assert "$9" in html
    assert "$0" in html
    assert "Paddle" in html
    assert "₪" not in html
    assert "PayPlus" not in html
    assert 'href="/static/css/app.css"' in html
    assert "#6366f1" not in html


async def test_guides_whatsapp_and_green_api(client):
    page = await client.get("/guides")
    html = page.text
    assert page.status_code == 200
    assert "I allow callmebot to send me messages" in html
    assert "+34 694 23 41 84" in html
    assert "BotFather" in html
    assert "Integrations" in html
    assert "Webhook URL" in html
    assert "green-api.com" in html
    assert "Most reliable easy setup" in html
    assert "If CallMeBot does not reply" in html
    assert "Open console.green-api.com and create an instance." in html
    assert "open Get QR" in html
    assert "not on the Green-API home page" in html
    assert "Linked devices" in html
    assert "Copy the instance id and API token" in html
    assert "try tomorrow" not in html.lower()
    assert "תנסו מחר" not in html
    assert "לא חובה" not in html
    assert "רק אם כבר משתמשים בזה" not in html
    he = (await client.get("/guides?lang=he")).text
    assert "אם CallMeBot לא משיב" in he
    assert "תנסו מחר" not in he
    assert "לא חובה" not in he
    assert "רק אם כבר משתמשים בזה" not in he
    assert "ממתינים כשתי דקות" not in he


async def test_dashboard_english_and_hebrew(client):
    await signup(client)
    page = await client.get("/dashboard?lang=en")
    assert page.status_code == 200
    html = page.text
    assert 'lang="en"' in html or 'dir="ltr"' in html
    assert "Get Pro" in html
    assert "15 דקות" not in html
    assert "7 דולר" not in html
    assert "WhatsApp" in html
    assert "Delivered" in html
    assert "Failed" in html
    assert "Copy template" in html
    assert "green-api.com" in html
    assert "CallMeBot — this phone" in html
    assert "+34 694 23 41 84" in html
    assert "I allow callmebot to send me messages" in html
    assert "If CallMeBot does not reply" in html
    assert "Open console.green-api.com and create an instance." in html
    assert "Integrations" in html
    assert "{{ticker}}" in html
    assert "WhatsApp guide" in html
    assert "Telegram guide" in html
    assert "Discord guide" in html
    assert "$9" not in html
    assert "/api/v1/billing/checkout" in html
    _assert_no_banned(html, "/dashboard")

    he = await client.get("/dashboard?lang=he")
    assert he.status_code == 200
    assert 'lang="he"' in he.text
    assert "רוצה פרו" in he.text
    assert "הגיע" in he.text
    assert "לא הגיע" in he.text
    assert "העתק תבנית" in he.text
    _assert_no_banned(he.text, "/dashboard?lang=he")
