# SignalFlow

A lightweight webhook relay that receives TradingView alerts, formats them, and forwards them to Telegram, Discord, and WhatsApp. The dashboard is Hebrew RTL for non-technical traders.

## Plans

- **Free:** 1 webhook URL, 3 alerts per UTC day, SignalFlow footer on outbound messages. That one URL may fan out to WhatsApp, Telegram, and Discord together.
- **Pro:** $9 / month (USD). Unlimited webhook URLs and alerts, no footer, one retry after ~3s on Telegram/Discord/WhatsApp 5xx or timeout.

### Paddle Billing (Merchant of Record)

Pro checkout uses [Paddle](https://www.paddle.com/) — foreign receipts in USD. Paddle is the merchant of record.

1. Create a Paddle account and a product with a **$9 USD / month** recurring price.
2. In Paddle → Developer tools → Notifications, add webhook URL:
   `https://signalflow-cl0v.onrender.com/api/v1/billing/paddle`
   Subscribe at least to `transaction.completed`, `subscription.created`, `subscription.activated`, `subscription.canceled`, `subscription.past_due`.
3. Set a default payment link (Checkout settings) so `checkout.url` is returned.
4. On Render, set these environment variables (never commit secrets):

```
PADDLE_API_KEY=...
PADDLE_WEBHOOK_SECRET=...
PADDLE_PRICE_ID=pri_...
PADDLE_SANDBOX=true            # use sandbox-api.paddle.com while testing
```

`POST /api/v1/billing/checkout` (logged-in) creates a transaction (`collection_mode: automatic`, `items: [{price_id, quantity: 1}]`, `custom_data.user_id`) and returns `checkout.url`. The webhook verifies `Paddle-Signature`.

If the keys are missing the API returns Hebrew `סליקה לא הוגדרה עדיין` (HTTP 503). The dashboard «רוצה פרו» button is hidden when the user is already Pro.

Admin / allowlist / invite-code Pro grants still work and are not revoked by a later Paddle cancellation.

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
- `POST /api/v1/billing/checkout` — Paddle transaction / checkout URL ($9 / month)
- `POST /api/v1/billing/paddle` — Paddle webhook
- `POST /api/v1/auth/signup`, `/login`, `/logout`
- `GET/POST /api/v1/endpoints` — `destinations: [{type, config}, …]` (legacy `target_type` / `extra_target_*` still work)
- `DELETE /api/v1/endpoints/{id}`, `PATCH /api/v1/endpoints/{id}/toggle`
- `GET /api/v1/endpoints/{id}/logs`

## Production (Render)

- The Dockerfile runs `sh -c "uvicorn … --port ${PORT:-8000}"`.
- Public webhook URLs are built from the request host (`X-Forwarded-Host` / `Host`). Set `APP_BASE_URL` only to override.
- Set a strong `SECRET_KEY`. Do not commit `.env` or Paddle keys.
- Swap `DATABASE_URL` to Postgres when you want persistence across deploys.

## Tests

```bash
pip install -r requirements.txt
pytest
```
