"""Interior counter resets must not become observed daily energy."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from aiosolaredge.monitoring import BasicMonitoring
from aiosolaredge.v2 import InvalidResponseError


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["lifetimeEnergyCharged", "lifetimeEnergyDischarged"])
async def test_interior_counter_reset(field):
    now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)

    def samples(values):
        return [
            {
                "timestamp": (now - timedelta(minutes=15 * (2 - i))).isoformat(),
                "value": v,
            }
            for i, v in enumerate(values)
        ]

    battery = {
        "serialNumber": "B1",
        "unit": "KWH",
        "lifetimeEnergyCharged": samples([100, 110, 130]),
        "lifetimeEnergyDischarged": samples([100, 110, 130]),
    }
    battery[field] = samples([100, 10, 130])
    api = BasicMonitoring(None, AsyncMock(return_value="synthetic"))
    api._get = AsyncMock(return_value={"batteries": [battery]})
    with pytest.raises(InvalidResponseError):
        await api.storage_daily("123", now, "UTC", ["B1"])


@pytest.mark.asyncio
@pytest.mark.parametrize("serial", [None, [], {}, "", " ", 123])
async def test_malformed_unknown_storage_identity(serial):
    api = BasicMonitoring(None, AsyncMock(return_value="synthetic"))
    api._get = AsyncMock(return_value={"batteries": [{"serialNumber": serial}]})
    with pytest.raises(InvalidResponseError, match="Invalid battery identity"):
        await api.storage_daily(
            "123", datetime(2026, 10, 22, 12, tzinfo=timezone.utc), "UTC", ["B1"]
        )


@pytest.mark.asyncio
async def test_typed_inventory_drift_is_not_malformed_identity():
    from aiosolaredge.monitoring import StorageMembershipChanged

    api = BasicMonitoring(None, AsyncMock(return_value="synthetic"))
    api._get = AsyncMock(return_value={"batteries": [{"serialNumber": "B2"}]})
    with pytest.raises(StorageMembershipChanged):
        await api.storage_daily(
            "123", datetime(2026, 10, 22, 12, tzinfo=timezone.utc), "UTC", ["B1"]
        )
