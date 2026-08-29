# SignalFlow

A lightweight webhook relay that receives TradingView alerts, formats them, and forwards them to Telegram, Discord, and WhatsApp. The dashboard is Hebrew RTL for non-technical traders.

## Plans

- **Free:** 1 channel, 3 alerts per UTC day, SignalFlow footer on outbound messages.
- **Pro:** unlimited channels and alerts, no footer, one retry after ~3s on Telegram/Discord/WhatsApp 5xx or timeout. Optional second destination per channel.

There is no Stripe and no payment keys. A free user clicks «רוצה פרו» to join a waitlist (`upgrade_requested_at`). Grant Pro with:

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

1. Create a webhook endpoint (Telegram, Discord, or WhatsApp).
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

**Easy path (Green-API):** create an account, scan the QR, copy `idInstance` + `apiTokenInstance`, paste the recipient phone (e.g. `9725…`). SignalFlow POSTs to `https://api.green-api.com/waInstance{id}/sendMessage/{token}`.

**Meta Cloud API:** `phone_number_id` + `access_token` + recipient `to` (E.164). Secrets are masked in the UI.

## Telegram / Discord

Telegram: BotFather token + chat id. Discord: Channel Settings → Integrations → Webhooks → Copy Webhook URL. `discordapp.com` and `http://` URLs are normalized.

## API

- `POST /api/v1/webhook/{endpoint_token}` — public TradingView receiver
- `POST /api/v1/webhook/{endpoint_token}/test` — dashboard tester
- `GET /api/v1/health` — health check
- `GET /api/v1/auth/me`, `POST /api/v1/auth/request-pro` — plan + waitlist
- `POST /api/v1/auth/signup`, `/login`, `/logout`
- `GET/POST /api/v1/endpoints`, `DELETE /api/v1/endpoints/{id}`, `PATCH /api/v1/endpoints/{id}/toggle`
- `GET /api/v1/endpoints/{id}/logs`

## Production (Render)

- The Dockerfile runs `sh -c "uvicorn … --port ${PORT:-8000}"`.
- Public webhook URLs are built from the request host (`X-Forwarded-Host` / `Host`). Set `APP_BASE_URL` only to override.
- Set a strong `SECRET_KEY`. Do not commit `.env`.
- Free Render sleeps after ~15 minutes idle; the dashboard explains this in Hebrew.
- Swap `DATABASE_URL` to Postgres when you want persistence across deploys.

## Tests

```bash
pip install -r requirements.txt
pytest
```
