from decimal import Decimal

import httpx
import pytest

from app.core.errors import ExternalApiError
from app.integrations.ilo.client import IloClient
from app.integrations.ilo.profiles import get_profile


def test_parser_reads_average_consumed_watts_as_decimal() -> None:
    profile = get_profile("ilo5-redfish")

    watts = profile.parse_average_watts(
        {
            "PowerControl": [
                {
                    "PowerMetrics": {
                        "AverageConsumedWatts": 0,
                    },
                },
            ],
        }
    )

    assert watts == Decimal("0")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_parser_rejects_non_finite_average_consumed_watts(value: str) -> None:
    profile = get_profile("ilo5-redfish")

    with pytest.raises(ExternalApiError):
        profile.parse_average_watts(
            {
                "PowerControl": [
                    {
                        "PowerMetrics": {
                            "AverageConsumedWatts": value,
                        },
                    },
                ],
            }
        )


@pytest.mark.asyncio
async def test_session_token_success_uses_x_auth_token() -> None:
    seen_headers: list[httpx.Headers] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers)
        if request.url.path == "/redfish/v1/SessionService/Sessions":
            return httpx.Response(201, headers={"X-Auth-Token": "session-token"})
        if request.url.path == "/redfish/v1/Chassis/1/Power":
            assert request.headers["X-Auth-Token"] == "session-token"
            assert "Authorization" not in request.headers
            return httpx.Response(
                200,
                json={"PowerControl": [{"PowerMetrics": {"AverageConsumedWatts": 123.45}}]},
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = IloClient(
        host="ilo.example.test",
        username="Administrator",
        password="secret-password",
        profile="ilo5-redfish",
        transport=httpx.MockTransport(handler),
    )

    reading = await client.read_power()

    assert reading.average_watts == Decimal("123.45")
    assert reading.auth_method_used == "session"
    assert any(headers.get("X-Auth-Token") == "session-token" for headers in seen_headers)
    assert "secret-password" not in str(reading.model_dump())
    assert "session-token" not in str(reading.model_dump())


@pytest.mark.asyncio
async def test_session_auth_failure_falls_back_to_basic_and_zero_is_success() -> None:
    basic_requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal basic_requests
        if request.url.path == "/redfish/v1/SessionService/Sessions":
            return httpx.Response(401, json={"error": "denied"})
        if request.url.path == "/redfish/v1/Chassis/1/Power":
            assert request.headers["Authorization"].startswith("Basic ")
            basic_requests += 1
            return httpx.Response(
                200,
                json={"PowerControl": [{"PowerMetrics": {"AverageConsumedWatts": 0}}]},
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = IloClient(
        host="ilo.example.test",
        username="Administrator",
        password="secret-password",
        profile="ilo4-redfish",
        transport=httpx.MockTransport(handler),
    )

    reading = await client.read_power()

    assert reading.average_watts == Decimal("0")
    assert reading.auth_method_used == "basic"
    assert basic_requests == 1


@pytest.mark.asyncio
async def test_missing_session_token_falls_back_to_basic() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/redfish/v1/SessionService/Sessions":
            return httpx.Response(201)
        if request.url.path == "/redfish/v1/Chassis/1/Power":
            assert request.headers["Authorization"].startswith("Basic ")
            return httpx.Response(
                200,
                json={"PowerControl": [{"PowerMetrics": {"AverageConsumedWatts": 88}}]},
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = IloClient(
        host="ilo.example.test",
        username="Administrator",
        password="secret-password",
        profile="ilo6-redfish",
        transport=httpx.MockTransport(handler),
    )

    assert (await client.read_power()).auth_method_used == "basic"


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_power_get_auth_failure_with_token_falls_back_to_basic(status_code: int) -> None:
    token_power_requests = 0
    basic_power_requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_power_requests, basic_power_requests
        if request.url.path == "/redfish/v1/SessionService/Sessions":
            return httpx.Response(201, headers={"X-Auth-Token": "session-token"})
        if request.url.path == "/redfish/v1/Chassis/1/Power":
            if request.headers.get("X-Auth-Token") == "session-token":
                token_power_requests += 1
                return httpx.Response(status_code)
            assert request.headers["Authorization"].startswith("Basic ")
            basic_power_requests += 1
            return httpx.Response(
                200,
                json={"PowerControl": [{"PowerMetrics": {"AverageConsumedWatts": 101}}]},
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = IloClient(
        host="ilo.example.test",
        username="Administrator",
        password="secret-password",
        profile="ilo5-redfish",
        transport=httpx.MockTransport(handler),
    )

    reading = await client.read_power()

    assert reading.auth_method_used == "basic"
    assert token_power_requests == 1
    assert basic_power_requests == 1


@pytest.mark.asyncio
async def test_unknown_profile_and_parser_failure_raise_sanitized_external_api_error() -> None:
    with pytest.raises(ExternalApiError) as unknown_error:
        IloClient(
            host="ilo.example.test",
            username="Administrator",
            password="secret-password",
            profile="unknown-profile",
        )

    assert "secret-password" not in str(unknown_error.value.details)
    assert "token" not in str(unknown_error.value.details).lower()

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "secret-password"})

    client = IloClient(
        host="ilo.example.test",
        username="Administrator",
        password="secret-password",
        profile="legacy-hpe-rest",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ExternalApiError) as parser_error:
        await client.read_power()

    details = str(parser_error.value.details)
    assert "secret-password" not in details
    assert "unexpected" not in details
    assert "token" not in details.lower()
