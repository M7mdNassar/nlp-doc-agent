import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_health_endpoint(monkeypatch):
    # Mock the external connections so the test runs instantly without Docker.

    # 1. Mock SQLite Engine connect
    class MockConnect:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute(self, *args):
            pass

    class MockEngine:
        def connect(self):
            return MockConnect()

    monkeypatch.setattr("src.api.routers.health.engine", MockEngine())

    # 2. Mock Redis
    class MockRedis:
        async def ping(self):
            return True

    monkeypatch.setattr(
        "src.api.routers.health.get_redis_client",
        lambda: MockRedis(),
    )

    # 3. Mock Qdrant
    class MockQdrant:
        class MockClient:
            async def get_collections(self):
                return True

        client = MockClient()

    monkeypatch.setattr(
        "src.api.routers.health.QdrantAdapter",
        lambda: MockQdrant(),
    )

    # 4. Run the actual HTTP test
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as ac:
        response = await ac.get("/health")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
