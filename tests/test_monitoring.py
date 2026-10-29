"""Synthetic official Basic 2.1.0 contracts, never live account fixtures."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiointercept import aiointercept

from aiosolaredge.monitoring import BasicMonitoring, energy, period_start
from aiosolaredge.v2 import InvalidResponseError, _timestamp


def test_iso_z_supported_on_minimum_python():
    """Official timestamps allow Z, including the supported Python 3.10 runtime."""
    assert _timestamp("2026-10-25T12:00:00Z") == datetime(
        2026, 10, 25, 12, tzinfo=timezone.utc
    )


BASE = "https://monitoringapi.solaredge.com/v2/sites/123"
NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "when,hours",
    [
        (datetime(2026, 3, 29, 22, tzinfo=timezone.utc), 23),
        (datetime(2026, 10, 25, 23, tzinfo=timezone.utc), 25),
    ],
)
def test_calendar_dst(when, hours):
    start = period_start(when - timedelta(seconds=1), "Europe/Amsterdam", "day")
    assert (when - start.astimezone(timezone.utc)).total_seconds() == hours * 3600
    assert start.hour == 0


@pytest.mark.parametrize("value", [True, -1, float("inf"), 10**1000, 1e308, "4"])
def test_numeric_normalization(value):
    with pytest.raises(InvalidResponseError):
        energy(value, "GWH")


@pytest.mark.asyncio
async def test_overview_direct_ranges_and_null():
    async with aiohttp.ClientSession() as session:
        reserve = AsyncMock()
        api = BasicMonitoring(session, AsyncMock(return_value="synthetic"), reserve)
        async with aiointercept(mock_external_urls=True) as mock:
            mock.get(
                re.compile(re.escape(BASE + "/overview") + r"(?:\?.*)?$"),
                payload={
                    "siteId": 123,
                    "production": {
                        "total": 2,
                        "unit": "KWH",
                        "toGrid": 0,
                        "toSelfConsumption": None,
                    },
                    "consumption": {"unit": "WH", "total": None, "fromGrid": 4},
                },
            )
            daily = await api.overview("123", NOW, "Europe/Amsterdam", "day")
            assert daily["energy_today"].value == 2000
            assert daily["production_energy"].value == 2000
            assert daily["purchased_energy"].value == 4
            assert daily["feedin_energy"].value == 0
            assert daily["selfconsumption_energy"].value is None
            assert daily["consumption_energy"].value is None
            assert daily["energy_today"].timestamp == NOW
            url = next(iter(mock.requests))[1]
            assert url.query["from"] == "2026-10-25T00:00:00+02:00"
            reserve.assert_awaited_once()
            for period in ("month", "year"):
                mock.get(
                    re.compile(re.escape(BASE + "/overview") + r"(?:\?.*)?$"),
                    payload={"siteId": 123, "production": {"total": 2, "unit": "KWH"}},
                )
                result = await api.overview("123", NOW, "Europe/Amsterdam", period)
                assert result[f"energy_this_{period}"].value == 2000


@pytest.mark.asyncio
async def test_inventory_explicit_types_and_allowlist():
    async with aiohttp.ClientSession() as session:
        api = BasicMonitoring(session, AsyncMock(return_value="synthetic"))
        async with aiointercept(mock_external_urls=True) as mock:
            mock.get(
                re.compile(re.escape(BASE + "/devices") + r"(?:\?.*)?$"),
                payload=[
                    {
                        "serialNumber": "B1",
                        "type": "BATTERY",
                        "model": "x",
                        "owner": "PRIVATE",
                    }
                ],
            )
            data = await api.inventory("123")
            assert data["batteries"] == [
                {"serialNumber": "B1", "type": "BATTERY", "model": "x"}
            ]
            assert data["meters"] == []
            assert set(next(iter(mock.requests))[1].query.getall("types")) == {
                "INVERTER",
                "BATTERY",
                "GATEWAY",
                "METER",
            }


@pytest.mark.asyncio
async def test_inventory_virtual_and_multi_role_meters():
    """One physical meter is listed per role; calculated meters have no serial."""
    meters: list[dict[str, Any]] = [
        {"serialNumber": None, "meterType": "SelfConsumption", "form": "virtual"},
        {"serialNumber": "M1", "meterType": "FeedIn", "form": "physical"},
        {"serialNumber": "M1", "meterType": "Purchased", "form": "physical"},
        {"serialNumber": None, "meterType": "Consumption", "form": "virtual"},
    ]
    async with aiohttp.ClientSession() as session:
        api = BasicMonitoring(session, AsyncMock(return_value="synthetic"))
        async with aiointercept(mock_external_urls=True) as mock:
            mock.get(
                re.compile(re.escape(BASE + "/devices") + r"(?:\?.*)?$"),
                payload=[
                    {"serialNumber": "I1", "type": "INVERTER", "connectedTo": None},
                    *(
                        {**meter, "type": "METER", "connectedTo": "I1"}
                        for meter in meters
                    ),
                ],
            )
            data = await api.inventory("123")
    assert data["inverters"] == [{"serialNumber": "I1", "type": "INVERTER"}]
    assert data["meters"] == [{**meter, "type": "METER"} for meter in meters]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "devices",
    [
        ["not-a-device"],
        [{"serialNumber": "X1", "type": "OPTIMIZER"}],
        [{"serialNumber": None, "type": "METER", "meterType": "FeedIn"}],
        [
            {
                "serialNumber": None,
                "type": "METER",
                "meterType": "FeedIn",
                "form": "physical",
            }
        ],
        [
            {
                "serialNumber": "",
                "type": "METER",
                "meterType": "Consumption",
                "form": "virtual",
            }
        ],
        [{"serialNumber": None, "type": "BATTERY", "form": "virtual"}],
        [
            {"serialNumber": "M1", "type": "METER", "meterType": "FeedIn"},
            {"serialNumber": "M1", "type": "METER", "meterType": "FeedIn"},
        ],
        [
            {"type": "METER", "meterType": "Consumption", "form": "virtual"},
            {"type": "METER", "meterType": "Consumption", "form": "virtual"},
        ],
        [
            {"serialNumber": "I1", "type": "INVERTER"},
            {"serialNumber": "I1", "type": "INVERTER"},
        ],
    ],
    ids=[
        "non-object-device",
        "unrequested-type",
        "meter-without-serial-or-form",
        "physical-meter-without-serial",
        "virtual-meter-empty-serial",
        "battery-without-serial",
        "same-meter-role-twice",
        "same-virtual-role-twice",
        "same-inverter-twice",
    ],
)
async def test_inventory_rejects_ambiguous_identity(devices):
    async with aiohttp.ClientSession() as session:
        api = BasicMonitoring(session, AsyncMock(return_value="synthetic"))
        async with aiointercept(mock_external_urls=True) as mock:
            mock.get(
                re.compile(re.escape(BASE + "/devices") + r"(?:\?.*)?$"),
                payload=devices,
            )
            with pytest.raises(InvalidResponseError):
                await api.inventory("123")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values,expected",
    [([], None), ([0], None), ([0, None], None), ([2, 5], 3000), ([0, 0], 0)],
)
async def test_battery_delta_missing_not_zero(values, expected):
    async with aiohttp.ClientSession() as session:
        api = BasicMonitoring(session, AsyncMock(return_value="synthetic"))
        samples = [
            {"timestamp": (NOW - timedelta(minutes=15 * i)).isoformat(), "value": value}
            for i, value in enumerate(reversed(values))
        ]
        async with aiointercept(mock_external_urls=True) as mock:
            mock.get(
                re.compile(
                    re.escape(BASE + "/storage/lifetime-energy") + r"(?:\?.*)?$"
                ),
                payload={
                    "batteries": [
                        {
                            "serialNumber": "B1",
                            "unit": "KWH",
                            "lifetimeEnergyCharged": samples,
                            "lifetimeEnergyDischarged": samples,
                        }
                    ]
                },
            )
            result = await api.storage_daily(
                "123", NOW, "Europe/Amsterdam", ["B1", "B2"]
            )
            assert result["B1_battery_charge_energy"].value == expected
            assert result["B2_battery_charge_energy"].value is None
            assert result["storage_charge_energy"].value is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "samples",
    [
        [
            {"timestamp": NOW.isoformat(), "value": 2},
            {"timestamp": NOW.isoformat(), "value": 3},
        ],
        [{"timestamp": (NOW + timedelta(hours=1)).isoformat(), "value": 1}],
        [
            {"timestamp": (NOW - timedelta(minutes=15)).isoformat(), "value": 10},
            {"timestamp": NOW.isoformat(), "value": 1},
        ],
    ],
)
async def test_invalid_battery_windows_and_counter_reset(samples):
    async with aiohttp.ClientSession() as session:
        api = BasicMonitoring(session, AsyncMock(return_value="synthetic"))
        async with aiointercept(mock_external_urls=True) as mock:
            mock.get(
                re.compile(
                    re.escape(BASE + "/storage/lifetime-energy") + r"(?:\?.*)?$"
                ),
                payload={
                    "batteries": [
                        {
                            "serialNumber": "B1",
                            "unit": "WH",
                            "lifetimeEnergyCharged": samples,
                            "lifetimeEnergyDischarged": samples,
                        }
                    ]
                },
            )
            with pytest.raises(InvalidResponseError):
                await api.storage_daily("123", NOW, "Europe/Amsterdam", ["B1"])
