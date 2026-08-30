from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.admin import router as admin_router
from app.api.dashboard import router as dashboard_router
from app.api.v1.router import api_router
from app.core.database import init_db
from app.core.limiter import limiter
from app.core.logging import setup_logging, logger
from app.i18n import SUPPORTED, apply_locale_cookie, locale_from_request, t
from app.services.dispatcher import close_http_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    logger.info("SignalFlow started")
    yield
    await close_http_client()
    logger.info("SignalFlow shut down")


app = FastAPI(title="SignalFlow", version="1.0.0", lifespan=lifespan)

app.state.limiter = limiter


class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        locale = locale_from_request(request)
        request.state.locale = locale
        response = await call_next(request)
        if request.query_params.get("lang") in SUPPORTED:
            apply_locale_cookie(response, locale)
        return response


app.add_middleware(LocaleMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    locale = locale_from_request(request)
    return JSONResponse(
        status_code=429,
        content={"detail": t(locale, "api.rate_limit")},
    )


app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(api_router)
app.include_router(admin_router)
app.include_router(dashboard_router)
