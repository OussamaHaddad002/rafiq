from httpx import AsyncClient


async def test_health_reports_database_ok(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_response_carries_generated_request_id(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert len(response.headers["x-request-id"]) == 32


async def test_valid_incoming_request_id_is_reused(client: AsyncClient) -> None:
    response = await client.get("/api/health", headers={"x-request-id": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


async def test_invalid_incoming_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/api/health", headers={"x-request-id": "bad id\nwith newline"})
    assert response.headers["x-request-id"] != "bad id\nwith newline"
