from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.api.dashboard import router as dashboard_router
from app.api.v1.router import api_router
from app.core.database import init_db
from app.core.limiter import limiter
from app.core.logging import setup_logging, logger
from app.services.dispatcher import close_http_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    logger.info("SignalFlow started")
    yield
    await close_http_client()
    logger.info("SignalFlow shut down")


app = FastAPI(title="SignalFlow", version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Please slow down."})


app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(api_router)
app.include_router(dashboard_router)
