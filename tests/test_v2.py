"""Synthetic contract tests; no live SolarEdge data or credentials."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiointercept import aiointercept

from aiosolaredge.v2 import (
    AuthenticationError,
    InvalidResponseError,
    PermissionDeniedError,
    RateLimitError,
    SolarEdgeV2,
    SolarEdgeV2Error,
)

BASE = "https://monitoringapi.solaredge.com/v2/sites/123"
NOW = datetime(2026, 10, 21, 10, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_lifetime_native_counter():
    """Daily or TOTAL interval sums must not replace the onboard counter."""
    async with aiohttp.ClientSession() as session:
        token = AsyncMock(return_value="synthetic-access")
        api = SolarEdgeV2(session, token)
        async with aiointercept(mock_external_urls=True) as mock:
            mock.get(
                BASE + "/lifetime-energy",
                payload={
                    "energy": 123.5,
                    "unit": "KWH",
                    "lastUpdateTime": NOW.isoformat(),
                },
            )
            reading = await api.lifetime_energy("123")
            assert reading.value == 123500
            assert reading.timestamp == NOW
            request = next(iter(mock.requests.values()))[0]
            assert request.headers["Authorization"] == "Bearer synthetic-access"
            assert "api_key" not in str(next(iter(mock.requests))[1])
            token.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,exception",
    [
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (429, RateLimitError),
        (503, SolarEdgeV2Error),
    ],
)
async def test_errors_are_bounded_and_redacted(status, exception):
    async with aiohttp.ClientSession() as session:
        api = SolarEdgeV2(session, AsyncMock(return_value="synthetic-access"))
        async with aiointercept(mock_external_urls=True) as mock:
            mock.get(
                BASE,
                status=status,
                body="synthetic-secret-echo",
                headers={"Retry-After": "120"},
            )
            with pytest.raises(exception) as err:
                await api.site("123")
            assert "synthetic-secret" not in str(err.value)
            assert sum(map(len, mock.requests.values())) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unit,factor", [("WH", 1), ("KWH", 1000), ("MWH", 1000000), ("GWH", 1000000000)]
)
async def test_energy_units(unit, factor):
    async with aiohttp.ClientSession() as session:
        api = SolarEdgeV2(session, AsyncMock(return_value="synthetic-access"))
        async with aiointercept(mock_external_urls=True) as mock:
            mock.get(
                BASE + "/lifetime-energy",
                payload={"energy": 2, "unit": unit, "lastUpdateTime": NOW.isoformat()},
            )
            assert (await api.lifetime_energy("123")).value == 2 * factor


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, -1, "bad", float("inf"), True])
async def test_invalid_counter_not_zero(value):
    async with aiohttp.ClientSession() as session:
        api = SolarEdgeV2(session, AsyncMock(return_value="synthetic-access"))
        async with aiointercept(mock_external_urls=True) as mock:
            mock.get(
                BASE + "/lifetime-energy",
                payload={
                    "energy": value,
                    "unit": "WH",
                    "lastUpdateTime": NOW.isoformat(),
                },
            )
            with pytest.raises(InvalidResponseError):
                await api.lifetime_energy("123")


@pytest.mark.asyncio
async def test_power_selects_latest_including_null():
    async with aiohttp.ClientSession() as session:
        api = SolarEdgeV2(session, AsyncMock(return_value="synthetic-access"))
        async with aiointercept(mock_external_urls=True) as mock:
            import re

            mock.get(
                re.compile(BASE + "/power.*"),
                payload={
                    "unit": "W",
                    "resolution": "QUARTER_HOUR",
                    "values": [
                        {"timestamp": NOW.isoformat(), "value": None},
                        {
                            "timestamp": (NOW - timedelta(minutes=15)).isoformat(),
                            "value": 200,
                        },
                    ],
                },
            )
            reading = await api.power("123", NOW)
            assert reading.value is None
            assert reading.timestamp == NOW
            request = next(iter(mock.requests.values()))[0]
            assert request.query["resolution"] == "QUARTER_HOUR"
            assert request.query["from"].endswith("+00:00")


@pytest.mark.asyncio
async def test_power_reported_zero_is_valid():
    async with aiohttp.ClientSession() as session:
        api = SolarEdgeV2(session, AsyncMock(return_value="synthetic-access"))
        async with aiointercept(mock_external_urls=True) as mock:
            import re

            mock.get(
                re.compile(BASE + "/power.*"),
                payload={
                    "unit": "W",
                    "resolution": "QUARTER_HOUR",
                    "values": [{"timestamp": NOW.isoformat(), "value": 0}],
                },
            )
            assert (await api.power("123", NOW)).value == 0


@pytest.mark.asyncio
async def test_no_timezone_rejected_before_request():
    async with aiohttp.ClientSession() as session:
        token = AsyncMock(return_value="synthetic-access")
        api = SolarEdgeV2(session, token)
        with pytest.raises(ValueError):
            await api.power("123", NOW.replace(tzinfo=None))
        token.assert_not_awaited()


@pytest.mark.asyncio
async def test_network_error_redacted():
    async with aiohttp.ClientSession() as session:
        api = SolarEdgeV2(session, AsyncMock(return_value="synthetic-access"))
        async with aiointercept(mock_external_urls=True) as mock:
            mock.get(
                BASE, exception=aiohttp.ClientConnectionError("synthetic-secret-echo")
            )
            with pytest.raises(SolarEdgeV2Error, match="Connection failed"):
                await api.site("123")


@pytest.mark.asyncio
@pytest.mark.parametrize("site", ["../oauth2/token", "123?api_key=bad", "", "123/456"])
async def test_site_path_validation(site):
    async with aiohttp.ClientSession() as session:
        token = AsyncMock(return_value="synthetic-access")
        api = SolarEdgeV2(session, token)
        with pytest.raises(ValueError):
            await api.site(site)
        token.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "monthly"),
    [
        ({"Retry-After": "45", "x-ratelimit-remaining-minute": "0"}, False),
        ({"Retry-After": "1209600", "x-ratelimit-remaining-month": "0"}, True),
    ],
)
async def test_quota_axis_headers(headers, monthly):
    """Preserve documented monthly exhaustion separately from throughput."""
    async with aiohttp.ClientSession() as session:
        api = SolarEdgeV2(session, AsyncMock(return_value="synthetic-access"))
        async with aiointercept(mock_external_urls=True) as mock:
            mock.get(BASE, status=429, headers=headers)
            with pytest.raises(RateLimitError) as caught:
                await api.site("123")
            assert caught.value.monthly_exhausted is monthly
            assert caught.value.retry_after == headers["Retry-After"]
