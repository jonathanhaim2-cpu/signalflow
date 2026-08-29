# SignalFlow

A lightweight webhook relay that receives TradingView alerts, formats them into rich messages, and forwards them instantly to Telegram and Discord.

## Stack

- FastAPI + Pydantic v2 + async SQLAlchemy (SQLite for dev, Postgres-ready)
- Jinja2 + Tailwind CSS (CDN) dashboard, no build step
- httpx for async outbound delivery
- slowapi for rate limiting on the public webhook

## Local setup (virtualenv)

```bash
cd signalflow
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set SECRET_KEY, optionally TELEGRAM_DEFAULT_BOT_TOKEN

uvicorn app.main:app --reload
```

Visit http://localhost:8000, sign up, and create your first webhook endpoint.

## Local setup (Docker)

```bash
cp .env.example .env
docker compose up --build
```

The app is available at http://localhost:8000. SQLite data persists in `./signalflow.db` on the host.

## Connecting TradingView

1. In the SignalFlow dashboard, create a webhook endpoint (choose Telegram or Discord as the target).
2. Copy the generated webhook URL, e.g. `https://your-domain.com/api/v1/webhook/<token>`.
3. In TradingView, open your alert's settings → **Notifications** → **Webhook URL**, and paste the URL.
4. Set the alert message to JSON matching SignalFlow's schema, e.g.:

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

If TradingView sends plain text instead of JSON (or the JSON is malformed), SignalFlow falls back to forwarding the raw text as the alert message — delivery never fails silently, and every attempt is logged.

## Telegram bot setup

1. Message [@BotFather](https://t.me/BotFather), run `/newbot`, and copy the bot token.
2. Start a chat with your bot (or add it to a group) and send any message.
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` and read the `chat.id` field — that's your `chat_id`.
4. Enter the bot token and chat_id when creating a webhook endpoint in SignalFlow (or leave the token blank to use `TELEGRAM_DEFAULT_BOT_TOKEN` from `.env`).

## Discord setup

1. In your Discord server, go to Channel Settings → Integrations → Webhooks → New Webhook.
2. Copy the webhook URL and paste it when creating a Discord-target endpoint in SignalFlow.

## API reference

- `POST /api/v1/webhook/{endpoint_token}` — public receiver for TradingView alerts (JSON or plain text).
- `POST /api/v1/webhook/{endpoint_token}/test` — auth-only, sends a simulated alert (used by the dashboard's payload tester).
- `GET /api/v1/health` — health check.
- `POST /api/v1/auth/signup`, `/login`, `/logout` — session auth via HTTP-only cookie.
- `GET/POST /api/v1/endpoints`, `DELETE /api/v1/endpoints/{id}`, `PATCH /api/v1/endpoints/{id}/toggle` — manage webhook endpoints.
- `GET /api/v1/endpoints/{id}/logs` — recent delivery logs for an endpoint.

## Production notes

- Swap `DATABASE_URL` to a Postgres DSN (e.g. `postgresql+asyncpg://user:pass@host/db`) — models are ORM-only, no SQLite-specific code.
- Set a strong random `SECRET_KEY`.
- Put SignalFlow behind a reverse proxy (Caddy/Nginx) with TLS; TradingView requires HTTPS webhook URLs.
- The webhook receiver never raises on malformed input — it always logs a delivery attempt (delivered/failed) so nothing is lost silently.
