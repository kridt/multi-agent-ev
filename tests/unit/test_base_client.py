"""Tests for the base API client: retry, rate limiting, error handling."""

import pytest
import respx
from httpx import Response

from ingestion.base_client import APIError, AuthenticationError, BaseAPIClient, RateLimitError


@pytest.fixture
def client():
    return BaseAPIClient(base_url="https://api.example.com", rate_limit_per_second=100.0)


@respx.mock
@pytest.mark.asyncio
async def test_successful_get(client):
    respx.get("https://api.example.com/test").mock(
        return_value=Response(200, json={"ok": True})
    )
    async with client:
        result = await client.get("/test")
    assert result == {"ok": True}


@respx.mock
@pytest.mark.asyncio
async def test_auth_error_raises(client):
    respx.get("https://api.example.com/test").mock(return_value=Response(401, text="Unauthorized"))
    async with client:
        with pytest.raises(AuthenticationError):
            await client.get("/test")


@respx.mock
@pytest.mark.asyncio
async def test_client_error_raises(client):
    respx.get("https://api.example.com/test").mock(return_value=Response(404, text="Not Found"))
    async with client:
        with pytest.raises(APIError) as exc_info:
            await client.get("/test")
        assert exc_info.value.status_code == 404


@respx.mock
@pytest.mark.asyncio
async def test_rate_limit_retries(client):
    client.max_retries = 1
    route = respx.get("https://api.example.com/test")
    route.side_effect = [
        Response(429, headers={"Retry-After": "0"}),
        Response(200, json={"ok": True}),
    ]
    async with client:
        result = await client.get("/test")
    assert result == {"ok": True}
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_server_error_retries(client):
    client.max_retries = 1
    route = respx.get("https://api.example.com/test")
    route.side_effect = [
        Response(500, text="Internal Server Error"),
        Response(200, json={"retried": True}),
    ]
    async with client:
        result = await client.get("/test")
    assert result == {"retried": True}


@respx.mock
@pytest.mark.asyncio
async def test_max_retries_exceeded(client):
    client.max_retries = 0
    respx.get("https://api.example.com/test").mock(return_value=Response(500, text="Fail"))
    async with client:
        with pytest.raises(APIError):
            await client.get("/test")


@respx.mock
@pytest.mark.asyncio
async def test_params_passed(client):
    route = respx.get("https://api.example.com/test").mock(
        return_value=Response(200, json={"ok": True})
    )
    async with client:
        await client.get("/test", params={"key": "value"})
    assert route.calls[0].request.url.params["key"] == "value"
