from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class HttpRequestError(RuntimeError):
    status_code: int
    response_text: str

    def __str__(self) -> str:
        return f"HTTP {self.status_code}: {self.response_text}"


class AsyncHttpClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.timeout_seconds = timeout_seconds
        self.default_headers = default_headers or {}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> AsyncHttpClient:
        await self.start()
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                headers=self.default_headers,
            )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = await self._request("GET", url, params=params, headers=headers)
        return self._json_response(response)

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        data: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = await self._request("POST", url, json=json, data=data, headers=headers)
        return self._json_response(response)

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        await self.start()
        assert self._client is not None
        response = await self._client.request(method, url, **kwargs)
        if response.status_code >= 400:
            raise HttpRequestError(
                status_code=response.status_code,
                response_text=response.text,
            )
        return response

    def _json_response(self, response: httpx.Response) -> dict[str, Any]:
        if not response.content:
            return {}
        data = response.json()
        if isinstance(data, dict):
            return data
        return {"data": data}

