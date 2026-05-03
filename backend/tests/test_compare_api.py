import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_compare_endpoint_requires_two_unique_run_ids(client: AsyncClient) -> None:
    run_id = uuid.uuid4()

    response = await client.get(f"/api/v1/compare?run_ids={run_id}")

    assert response.status_code == 400
    assert response.json()["detail"] == "At least 2 unique run IDs are required"


@pytest.mark.asyncio
async def test_compare_endpoint_rejects_malformed_run_ids(client: AsyncClient) -> None:
    response = await client.get("/api/v1/compare?run_ids=not-a-uuid,also-bad")

    assert response.status_code == 400
    assert response.json()["detail"] == "run_ids must be comma-separated UUIDs"
