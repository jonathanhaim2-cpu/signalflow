# SignalFlow

A lightweight webhook relay that receives TradingView alerts, formats them, and forwards them to Telegram, Discord, and WhatsApp. The dashboard is Hebrew RTL for non-technical traders.

## Plans

- **Free:** 1 webhook URL, 3 alerts per UTC day, SignalFlow footer on outbound messages. That one URL may fan out to WhatsApp, Telegram, and Discord together.
- **Pro:** ₪39 / month (ILS). Unlimited webhook URLs and alerts, no footer, one retry after ~3s on Telegram/Discord/WhatsApp 5xx or timeout.

### PayPlus billing (Israeli clearing)

Pro checkout uses [PayPlus](https://www.payplus.co.il/) payment pages — credit card or Bit — not Stripe.

1. Open a PayPlus account at [payplus.co.il](https://www.payplus.co.il/).
2. Create a payment page and copy its UID.
3. On Render, set these environment variables (never commit secrets):

```
PAYPLUS_API_KEY=...
PAYPLUS_SECRET_KEY=...
PAYPLUS_PAYMENT_PAGE_UID=...
PAYPLUS_TERMINAL_UID=          # optional, sent when the terminal requires it
PAYPLUS_USE_STAGING=true       # use restapidev.payplus.co.il while testing
```

`POST /api/v1/billing/checkout` (logged-in) calls `PaymentPages/generateLink` with `charge_method=3` (recurring), `currency_code=ILS`, amount **39**, monthly unlimited (`recurring_type=2`, `recurring_range=1`, `number_of_charges=0`). Success/failure return to `/dashboard`; IPN goes to `POST /api/v1/billing/payplus`.

If the keys are missing the API returns Hebrew `סליקה לא הוגדרה עדיין` (HTTP 503). The dashboard «רוצה פרו» button is hidden when the user is already Pro.

Admin / allowlist / invite-code Pro grants still work and are not revoked by a later PayPlus failure.

```bash
ALLOW_PRO_EMAILS=you@example.com
# and/or
python scripts/grant_pro.py you@example.com
```

## Owner admin

Jonathan (`jonathanhaim2@gmail.com`) is the owner. On first signup/login that email becomes **admin + Pro**. Additional admins: `ADMIN_EMAILS` (comma-separated).

Hebrew SSR at `/admin` (non-admins get 404 / login redirect):

- User list: email, חינם/פרו, date, alerts today, upgrade requested
- «הפוך לפרו» / «הורד לחינם» / השבת
- Create a user (email + temp password, shown once)
- One-time Pro invite codes with a large code + QR PNG (`/redeem/{code}`). Default expiry 7 days; unused codes can be revoked or printed («הדפס / שמור»).

Set on Render: `ADMIN_EMAILS=jonathanhaim2@gmail.com`.

API limit errors are Hebrew `403` / `429`.

## Stack

- FastAPI + Pydantic v2 + async SQLAlchemy (SQLite for dev, Postgres-ready)
- Jinja2 + Tailwind CSS (CDN) dashboard, no build step
- httpx for async outbound delivery
- slowapi for rate limiting on the public webhook

## Local setup (virtualenv)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# set SECRET_KEY; optionally ALLOW_PRO_EMAILS / APP_BASE_URL

uvicorn app.main:app --reload
```

Visit http://localhost:8000, sign up, and create your first webhook endpoint.

## Local setup (Docker)

```bash
cp .env.example .env
docker compose up --build
```

The container listens on `$PORT` (default 8000) for Render.

## Connecting TradingView

1. Create a webhook endpoint. One URL can include WhatsApp, Telegram, and Discord together.
2. Copy the generated webhook URL. On Render it looks like `https://signalflow-cl0v.onrender.com/api/v1/webhook/<token>` — never localhost. Set `APP_BASE_URL` only if you need to override host detection.
3. In TradingView: Alert → **Notifications** → check **Webhook URL** → paste → Save.
4. Use the dashboard copy button for the JSON template, e.g.:

```json
{
  "ticker": "{{ticker}}",
  "action": "BUY",
  "price": "{{close}}",
  "timeframe": "{{interval}}",
  "stop_loss": "{{plot_0}}",
  "take_profit": "{{plot_1}}",
  "strategy_name": "EMA Cross",
  "message": "Bullish crossover confirmed"
}
```

Plain text still forwards; every attempt is logged as הגיע / לא הגיע.

## WhatsApp

**Easy path (CallMeBot, default):** alerts go to *your* WhatsApp — the same number that activated the bot. No second device, no QR.

1. Add `+34 694 23 41 84` as a WhatsApp contact (name it SignalFlow / CallMeBot).
2. Send exactly: `I allow callmebot to send me messages`
3. The bot replies with an APIKEY. If nothing arrives within two minutes, try again tomorrow (bot limit).
4. In the dashboard, paste your number as `9725…` and the APIKEY, then use בדיקה מהירה.

SignalFlow sends a GET to `https://api.callmebot.com/whatsapp.php?phone=…&text=…&apikey=…` (personal use only). Israeli `05…` numbers are stored as `9725…`. The APIKEY is masked in API responses.

**Advanced — Green-API:** [console.green-api.com](https://console.green-api.com) → Create instance → wait ~2 minutes → Get QR → WhatsApp: Linked devices → Link a device. Then paste `idInstance`, `apiTokenInstance`, and the recipient phone. QR is not on the Green-API homepage.

**Advanced — Meta Cloud API:** `phone_number_id` + `access_token` + recipient `to` (E.164).

## Telegram / Discord

Telegram: BotFather token + chat id. Discord: Channel Settings → Integrations → Webhooks → Copy Webhook URL. `discordapp.com` and `http://` URLs are normalized.

## API

- `POST /api/v1/webhook/{endpoint_token}` — public TradingView receiver
- `POST /api/v1/webhook/{endpoint_token}/test` — dashboard tester
- `GET /api/v1/health` — health check
- `GET /api/v1/auth/me` — plan snapshot
- `POST /api/v1/billing/checkout` — PayPlus recurring payment page (₪39 / month)
- `POST /api/v1/billing/payplus` — PayPlus IPN / callback
- `POST /api/v1/auth/signup`, `/login`, `/logout`
- `GET/POST /api/v1/endpoints` — `destinations: [{type, config}, …]` (legacy `target_type` / `extra_target_*` still work)
- `DELETE /api/v1/endpoints/{id}`, `PATCH /api/v1/endpoints/{id}/toggle`
- `GET /api/v1/endpoints/{id}/logs`

## Production (Render)

- The Dockerfile runs `sh -c "uvicorn … --port ${PORT:-8000}"`.
- Public webhook URLs are built from the request host (`X-Forwarded-Host` / `Host`). Set `APP_BASE_URL` only to override.
- Set a strong `SECRET_KEY`. Do not commit `.env` or PayPlus keys.
- Swap `DATABASE_URL` to Postgres when you want persistence across deploys.

## Tests

```bash
pip install -r requirements.txt
pytest
```
