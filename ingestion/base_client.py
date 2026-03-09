"""Base async HTTP client with retry, rate limiting, and structured logging."""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class APIError(Exception):
    def __init__(self, status_code: int, message: str, url: str):
        self.status_code = status_code
        self.url = url
        super().__init__(f"API error {status_code} from {url}: {message}")


class RateLimitError(APIError):
    pass


class AuthenticationError(APIError):
    pass


class BaseAPIClient:
    """Async HTTP client with retry, rate limiting, and logging."""

    def __init__(
        self,
        base_url: str,
        rate_limit_per_second: float = 1.0,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(int(rate_limit_per_second) or 1)
        self._min_interval = 1.0 / rate_limit_per_second
        self._last_request_time: float = 0.0
        self._client: httpx.AsyncClient | None = None

    def _build_client(self) -> httpx.AsyncClient:
        """Override in subclass to add auth headers."""
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            http2=True,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = self._build_client()
        return self._client

    async def _rate_limit(self) -> None:
        async with self._semaphore:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_time = time.monotonic()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with retry and rate limiting."""
        await self._rate_limit()
        client = await self._get_client()
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                start = time.monotonic()
                response = await client.request(method, path, params=params, json=json)
                duration_ms = int((time.monotonic() - start) * 1000)

                logger.debug(
                    "API %s %s -> %d (%dms)",
                    method,
                    url,
                    response.status_code,
                    duration_ms,
                )

                if response.status_code == 401:
                    raise AuthenticationError(401, "Authentication failed", url)

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 2 ** (attempt + 1)))
                    logger.warning("Rate limited on %s, retrying in %.1fs", url, retry_after)
                    await asyncio.sleep(retry_after)
                    last_error = RateLimitError(429, "Rate limited", url)
                    continue

                if response.status_code >= 500:
                    backoff = 2 ** (attempt + 1)
                    logger.warning(
                        "Server error %d on %s, retrying in %ds",
                        response.status_code,
                        url,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    last_error = APIError(response.status_code, response.text, url)
                    continue

                if response.status_code >= 400:
                    raise APIError(response.status_code, response.text, url)

                self._on_response(response)
                return response.json()

            except httpx.TransportError as e:
                backoff = 2 ** (attempt + 1)
                logger.warning("Transport error on %s: %s, retrying in %ds", url, e, backoff)
                await asyncio.sleep(backoff)
                last_error = e

        raise last_error or APIError(0, "Max retries exceeded", url)

    def _on_response(self, response: httpx.Response) -> None:
        """Hook for subclasses to process response headers (e.g., credit tracking)."""

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def post(
        self, path: str, json: dict[str, Any] | None = None, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._request("POST", path, params=params, json=json)

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
