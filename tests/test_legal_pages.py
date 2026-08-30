LEGAL_PATHS = ("/pricing", "/terms", "/privacy", "/refunds")


async def test_legal_pages_return_200_with_hebrew(client):
    for path in LEGAL_PATHS:
        page = await client.get(path, follow_redirects=False)
        assert page.status_code == 200, path
        html = page.text
        assert 'lang="he"' in html
        assert 'dir="rtl"' in html
        assert "SignalFlow" in html
        for href in LEGAL_PATHS:
            assert f'href="{href}"' in html


async def test_pricing_states_pro_price_and_paddle(client):
    page = await client.get("/pricing")
    assert page.status_code == 200
    html = page.text
    assert "$9" in html
    assert "Paddle" in html
    assert "חינם" in html
    assert "פרו" in html
    assert "jonathanhaim2@gmail.com" in html


async def test_terms_privacy_refunds_content(client):
    terms = (await client.get("/terms")).text
    assert "תנאי שימוש" in terms
    assert "ג׳ונתן חיימוף" in terms or "Jonathan Haimoff" in terms
    assert "TradingView" in terms

    privacy = (await client.get("/privacy")).text
    assert "מדיניות פרטיות" in privacy
    assert "Paddle" in privacy
    assert "jonathanhaim2@gmail.com" in privacy

    refunds = (await client.get("/refunds")).text
    assert "מדיניות החזרים" in refunds
    assert "14" in refunds
    assert "Paddle" in refunds
    assert "jonathanhaim2@gmail.com" in refunds


async def test_landing_footer_links_legal_pages(client):
    page = await client.get("/")
    assert page.status_code == 200
    html = page.text
    for href in LEGAL_PATHS:
        assert f'href="{href}"' in html
