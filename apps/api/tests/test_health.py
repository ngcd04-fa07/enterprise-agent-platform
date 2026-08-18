from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import ping_database
from app.main import app


@pytest.fixture
def override_db_ping(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    reachable: bool = request.param

    async def fake_ping() -> bool:
        return reachable

    app.dependency_overrides[ping_database] = fake_ping
    yield
    app.dependency_overrides.pop(ping_database, None)


@pytest.mark.parametrize(
    ("override_db_ping", "expected_status", "expected_database"),
    [
        (True, "ok", "ok"),
        (False, "degraded", "unreachable"),
    ],
    indirect=["override_db_ping"],
)
async def test_health_reports_database_status(
    override_db_ping: None,
    expected_status: str,
    expected_database: str,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == expected_status
    assert body["database"] == expected_database
    assert body["environment"] == "development"
