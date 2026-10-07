from httpx import AsyncClient


async def test_liveness(client: AsyncClient) -> None:
    res = await client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


async def test_readiness_reports_database_and_redis(client: AsyncClient) -> None:
    res = await client.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "database": True, "redis": True}


async def test_api_does_not_allow_cross_origin_browser_calls(client: AsyncClient) -> None:
    """Browsers reach the API only via the same-origin Next.js proxy, so no CORS is granted."""
    res = await client.get("/healthz", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in res.headers
