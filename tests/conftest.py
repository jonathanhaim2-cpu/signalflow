from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.config import get_settings
from app.main import app
from app.models import AlertLog, User, WebhookEndpoint  # noqa: F401


@dataclass
class FakeResponse:
    status_code: int = 200
    text: str = '{"ok":true}'
    headers: dict = field(default_factory=dict)
    url: str = "https://example.test"


class FakeHTTP:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.status_code = 200
        self.fail_times = 0
        self._failures_seen = 0
        self.exc: Exception | None = None

    async def post(self, url: str, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.exc and self._failures_seen < self.fail_times:
            self._failures_seen += 1
            raise self.exc
        if self._failures_seen < self.fail_times:
            self._failures_seen += 1
            return FakeResponse(status_code=503, text="upstream down")
        return FakeResponse(status_code=self.status_code)


@pytest.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(bind=db_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture
async def client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://signalflow-cl0v.onrender.com") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def fake_http(monkeypatch):
    fake = FakeHTTP()
    monkeypatch.setattr("app.services.dispatcher.get_http_client", lambda: fake)

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr("app.services.dispatcher.asyncio.sleep", _no_sleep)
    return fake


@pytest.fixture
def clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def signup(client: AsyncClient, email: str = "trader@example.com", password: str = "password1"):
    res = await client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    assert res.status_code == 201, res.text
    return res.json()
