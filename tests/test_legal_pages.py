LEGAL_PATHS = ("/pricing", "/terms", "/privacy", "/refunds")


async def test_legal_pages_return_200_with_english_default(client):
    for path in LEGAL_PATHS:
        page = await client.get(path, follow_redirects=False)
        assert page.status_code == 200, path
        html = page.text
        assert 'lang="en"' in html
        assert 'dir="ltr"' in html
        assert "SignalFlow" in html
        for href in LEGAL_PATHS:
            assert f'href="{href}"' in html


async def test_legal_pages_hebrew(client):
    for path in LEGAL_PATHS:
        page = await client.get(f"{path}?lang=he")
        assert page.status_code == 200, path
        assert 'lang="he"' in page.text
        assert 'dir="rtl"' in page.text


async def test_pricing_states_pro_price_and_paddle(client):
    page = await client.get("/pricing")
    assert page.status_code == 200
    html = page.text
    assert "$9" in html
    assert "Paddle" in html
    assert "Free" in html
    assert "Pro" in html
    assert "Billed securely with Paddle. Cancel anytime." in html
    assert "jonathanhaim2@gmail.com" in html
    assert "Merchant of Record" not in html
    assert "foreign" not in html.lower()


async def test_terms_privacy_refunds_content(client):
    terms = (await client.get("/terms")).text
    assert "Terms of use" in terms
    assert "Jonathan Haimoff" in terms
    assert "TradingView" in terms
    assert "Merchant of Record" not in terms

    privacy = (await client.get("/privacy")).text
    assert "Privacy policy" in privacy
    assert "Paddle" in privacy
    assert "jonathanhaim2@gmail.com" in privacy

    refunds = (await client.get("/refunds")).text
    assert "Refund policy" in refunds
    assert "14" in refunds
    assert "Paddle" in refunds
    assert "jonathanhaim2@gmail.com" in refunds
    assert "foreign" not in refunds.lower()
    assert "חשבונית זרה" not in refunds


async def test_landing_footer_links_legal_pages(client):
    page = await client.get("/")
    assert page.status_code == 200
    html = page.text
    for href in LEGAL_PATHS:
        assert f'href="{href}"' in html
