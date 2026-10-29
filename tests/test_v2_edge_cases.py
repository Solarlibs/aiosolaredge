"""
Edge-case contracts for quota metadata, DST windows and numeric bounds.

All responses are synthetic.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from zoneinfo import ZoneInfo

from aiosolaredge import v2

NOW = datetime(2026, 10, 21, 10, tzinfo=timezone.utc)


class Response:
    """Synthetic in-memory response."""

    def __init__(self, payload=None, status=200, headers=None):
        self.payload = payload
        self.status = status
        self.headers = headers or {}

    async def __aenter__(self):
        """Enter the synthetic response."""
        return self

    async def __aexit__(self, *args):
        """Exit without suppressing errors."""
        pass

    async def json(self):
        return self.payload


class Session:
    """Capture the actual client wire arguments."""

    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def get(self, url, **kwargs):
        self.kwargs = kwargs
        return self.response


def api(response):
    session = Session(response)
    return v2.SolarEdgeV2(session, AsyncMock(return_value="synthetic-access")), session


@pytest.mark.asyncio
async def test_429_retains_distinguishing_quota_metadata():
    errors = []
    for headers in [
        {
            "Retry-After": "120",
            "x-ratelimit-remaining-month": "0",
            "x-ratelimit-remaining-minute": "8",
        },
        {"Retry-After": "120", "x-ratelimit-remaining-minute": "0"},
    ]:
        client, _ = api(Response(status=429, headers=headers))
        with pytest.raises(v2.RateLimitError) as err:
            await client.site("123")
        errors.append(err.value)
    assert vars(errors[0]) != vars(errors[1])
    assert errors[0].quota["x-ratelimit-remaining-month"] == 0
    assert errors[0].quota["x-ratelimit-remaining-minute"] == 8
    assert errors[1].quota["x-ratelimit-remaining-minute"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 3, 29, 3, 30, tzinfo=ZoneInfo("Europe/Amsterdam")),
        datetime(2026, 10, 25, 3, 30, tzinfo=ZoneInfo("Europe/Amsterdam")),
        datetime(2026, 10, 25, 2, 30, fold=1, tzinfo=ZoneInfo("Europe/Amsterdam")),
    ],
)
async def test_power_window_is_two_elapsed_hours_across_dst(now):
    delayed = now.astimezone(timezone.utc) - timedelta(minutes=90)
    client, session = api(
        Response(
            {
                "unit": "W",
                "resolution": "QUARTER_HOUR",
                "values": [{"timestamp": delayed.isoformat(), "value": 1}],
            }
        )
    )
    reading = await client.power("123", now)
    start = datetime.fromisoformat(session.kwargs["params"]["from"])
    end = datetime.fromisoformat(session.kwargs["params"]["to"])
    assert (end - start).total_seconds() == 7200
    assert end == now.astimezone(timezone.utc)
    assert reading.timestamp == delayed


@pytest.mark.asyncio
async def test_lifetime_conversion_never_returns_infinity():
    client, _ = api(
        Response({"energy": 1e308, "unit": "KWH", "lastUpdateTime": NOW.isoformat()})
    )
    with pytest.raises(v2.InvalidResponseError):
        await client.lifetime_energy("123")


@pytest.mark.asyncio
async def test_large_integer_maps_to_invalid_response():
    client, _ = api(
        Response({"energy": 10**400, "unit": "WH", "lastUpdateTime": NOW.isoformat()})
    )
    with pytest.raises(v2.InvalidResponseError):
        await client.lifetime_energy("123")


@pytest.mark.asyncio
async def test_quota_metadata_is_allowlisted_and_bounded():
    client, _ = api(
        Response(
            status=429,
            headers={
                "x-ratelimit-remaining-month": "0",
                "x-ratelimit-limit-month": "2000",
                "x-ratelimit-remaining-minute": "not-an-integer",
                "x-ratelimit-limit-minute": "9" * 30,
                "x-ratelimit-limit-second": "-1",
                "X-Private-Token": "synthetic-private",
                "Retry-After": "x" * 129,
            },
        )
    )
    with pytest.raises(v2.RateLimitError) as err:
        await client.site("123")
    assert err.value.quota == {
        "x-ratelimit-remaining-month": 0,
        "x-ratelimit-limit-month": 2000,
    }
    assert err.value.monthly_exhausted is True
    assert err.value.retry_after is None
    assert "synthetic-private" not in str(vars(err.value))
