from httpx import AsyncClient


async def test_liveness(client: AsyncClient) -> None:
    res = await client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


async def test_readiness_reports_database_and_redis(client: AsyncClient) -> None:
    res = await client.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "database": True, "redis": True}


async def test_cors_allows_school_subdomain_only(client: AsyncClient) -> None:
    ok = await client.options(
        "/healthz",
        headers={
            "Origin": "http://progress.digitallearning360.localhost:3360",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert ok.headers.get("access-control-allow-origin") == (
        "http://progress.digitallearning360.localhost:3360"
    )
    bad = await client.options(
        "/healthz",
        headers={"Origin": "http://evil.example.com", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in bad.headers
