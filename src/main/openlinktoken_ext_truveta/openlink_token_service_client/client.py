# NOTE: This file is auto-generated. Do not edit manually.

from urllib.parse import quote

from httpx import AsyncClient

from .types import ExchangeRequest, ExchangeResponse


class OpenLinkTokenServiceClient:
    def __init__(self, base_url: str, client: AsyncClient) -> None:
        self._base_url = base_url
        self._client = client

    async def exchange_exchange(
        self, version: str, body: ExchangeRequest
    ) -> ExchangeResponse:
        url = f"{self._base_url}/v{quote(str(version))}/Exchange"
        response = await self._client.post(
            url,
            content=body.model_dump_json(by_alias=True),
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return ExchangeResponse.model_validate(response.json())

    async def exchange_exchange_2(
        self, version: str, body: ExchangeRequest
    ) -> ExchangeResponse:
        url = f"{self._base_url}/api/v{quote(str(version))}/Exchange"
        response = await self._client.post(
            url,
            content=body.model_dump_json(by_alias=True),
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return ExchangeResponse.model_validate(response.json())
