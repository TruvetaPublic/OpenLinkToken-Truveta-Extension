# NOTE: This file is auto-generated .  Do not edit manually.

from .types import ExchangeRequest, ExchangeResponse, FinalizeSessionRequest, InitializeSessionResponse

from httpx import AsyncClient

from urllib.parse import quote


class OpenLinkTokenServiceClient:
    def __init__(self, base_url: str, client: AsyncClient) -> None:
        self._base_url = base_url
        self._client = client

    async def exchange_exchange(self, version: str, body: ExchangeRequest) -> ExchangeResponse:
        url = f"{self._base_url}/v{quote(str(version))}/Exchange"
        response = await self._client.post(url, content=body.model_dump_json(by_alias=True), headers={"Content-Type": "application/json"})
        response.raise_for_status()
        return ExchangeResponse.model_validate(response.json())

    async def uploads_initialize_session(self, exchange_id: str, version: str) -> InitializeSessionResponse:
        url = f"{self._base_url}/v{quote(str(version))}/Uploads/{quote(str(exchange_id))}"
        response = await self._client.post(url)
        response.raise_for_status()
        return InitializeSessionResponse.model_validate(response.json())

    async def uploads_upload_chunk(self, exchange_id: str, chunk_index: int, version: str, body: bytes) -> None:
        url = f"{self._base_url}/v{quote(str(version))}/Uploads/{quote(str(exchange_id))}/chunks/{quote(str(chunk_index))}"
        response = await self._client.put(url, content=body, headers={"Content-Type": "application/octet-stream"})
        response.raise_for_status()

    async def uploads_finalize_session(self, exchange_id: str, version: str, body: FinalizeSessionRequest) -> None:
        url = f"{self._base_url}/v{quote(str(version))}/Uploads/{quote(str(exchange_id))}/complete"
        response = await self._client.post(url, content=body.model_dump_json(by_alias=True), headers={"Content-Type": "application/json"})
        response.raise_for_status()
