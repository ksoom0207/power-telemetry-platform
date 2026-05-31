from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from app.core.errors import ExternalApiError
from app.integrations.ilo.profiles import IloProfile, get_profile


class IloPowerReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    average_watts: Decimal
    auth_method_used: str
    profile_used: str


class IloClient:
    def __init__(
        self,
        *,
        host: str,
        username: str,
        password: str,
        profile: str,
        tls_verify: bool = False,
        timeout_seconds: int = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.profile: IloProfile = get_profile(profile)
        self.tls_verify = tls_verify
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def read_power(self) -> IloPowerReading:
        async with httpx.AsyncClient(
            base_url=self._base_url(),
            verify=self.tls_verify,
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            token = await self._create_session(client)
            if token is not None:
                response = await self._get_power_with_token(client, token)
                if response.status_code not in (401, 403):
                    return self._reading_from_response(response, auth_method="session")
            response = await self._get_power_with_basic(client)
            return self._reading_from_response(response, auth_method="basic")

    def _base_url(self) -> str:
        if self.host.startswith(("http://", "https://")):
            return self.host.rstrip("/")
        return f"https://{self.host.rstrip('/')}"

    async def _create_session(self, client: httpx.AsyncClient) -> str | None:
        try:
            response = await client.post(
                "/redfish/v1/SessionService/Sessions",
                json={"UserName": self.username, "Password": self.password},
            )
        except httpx.HTTPError:
            return None
        if not 200 <= response.status_code < 300:
            return None
        token = response.headers.get("X-Auth-Token")
        return token or None

    async def _get_power_with_token(
        self,
        client: httpx.AsyncClient,
        token: str,
    ) -> httpx.Response:
        try:
            return await client.get(self.profile.power_path, headers={"X-Auth-Token": token})
        except httpx.HTTPError as exc:
            raise self._external_error("iLO power request failed") from exc

    async def _get_power_with_basic(self, client: httpx.AsyncClient) -> httpx.Response:
        try:
            return await client.get(
                self.profile.power_path,
                auth=httpx.BasicAuth(self.username, self.password),
            )
        except httpx.HTTPError as exc:
            raise self._external_error("iLO power request failed") from exc

    def _reading_from_response(
        self,
        response: httpx.Response,
        *,
        auth_method: str,
    ) -> IloPowerReading:
        if not 200 <= response.status_code < 300:
            raise self._external_error(
                "iLO power request failed",
                status_code=response.status_code,
                auth_method=auth_method,
            )
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise self._external_error(
                "failed to parse iLO power response",
                auth_method=auth_method,
            ) from exc
        if not isinstance(payload, dict):
            raise self._external_error(
                "failed to parse iLO power response",
                auth_method=auth_method,
            )
        return IloPowerReading(
            average_watts=self.profile.parse_average_watts(payload),
            auth_method_used=auth_method,
            profile_used=self.profile.name,
        )

    def _external_error(
        self,
        message: str,
        *,
        status_code: int | None = None,
        auth_method: str | None = None,
    ) -> ExternalApiError:
        details: dict[str, object] = {"profile": self.profile.name, "host": self.host}
        if status_code is not None:
            details["status_code"] = status_code
        if auth_method is not None:
            details["auth_method"] = auth_method
        return ExternalApiError(message, details)
