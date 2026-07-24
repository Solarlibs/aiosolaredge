import datetime
import re

import aiohttp
import pytest
from aiointercept import aiointercept

from aiosolaredge import SolarEdge


@pytest.mark.asyncio
async def test_create_object():
    """Creating an object works as expected."""
    solar_edge = SolarEdge("API_KEY")
    assert solar_edge.timeout == 10
    assert solar_edge.api_key == "API_KEY"
    assert solar_edge._created_session is True
    await solar_edge.close()


@pytest.mark.asyncio
async def test_create_object_passed_session():
    """Creating an object works as expected with a passed session."""
    session = aiohttp.ClientSession()
    solar_edge = SolarEdge("API_KEY", session)
    assert solar_edge.timeout == 10
    assert solar_edge.api_key == "API_KEY"
    assert solar_edge._created_session is False
    await solar_edge.close()
    await session.close()


@pytest.mark.asyncio
async def test_simple_requests() -> None:
    """Creating an object works as expected."""
    async with aiointercept(mock_external_urls=True) as mocked:
        solar_edge = SolarEdge("API_KEY")
        assert solar_edge.timeout == 10
        assert solar_edge.api_key == "API_KEY"
        assert solar_edge._created_session is True
        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/details?api_key=API_KEY",
            payload={"details": "details"},
        )
        assert await solar_edge.get_details(123) == {"details": "details"}
        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/overview?api_key=API_KEY",
            payload={"overview": "overview"},
        )

        assert await solar_edge.get_overview(123) == {"overview": "overview"}
        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/inventory?api_key=API_KEY",
            payload={"inventory": "inventory"},
        )
        assert await solar_edge.get_inventory(123) == {"inventory": "inventory"}

        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/currentPowerFlow?api_key=API_KEY",
            payload={"currentPowerFlow": "currentPowerFlow"},
        )
        assert await solar_edge.get_current_power_flow(123) == {
            "currentPowerFlow": "currentPowerFlow"
        }

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/energyDetails"
        )
        mocked.get(
            pattern,
            payload={"energyDetails": "energyDetails"},
        )
        assert await solar_edge.get_energy_details(
            123, datetime.datetime.now(), datetime.datetime.now()
        ) == {"energyDetails": "energyDetails"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/energyDetails.*meters="
        )
        mocked.get(
            pattern,
            payload={"meters": "meters"},
        )
        assert await solar_edge.get_energy_details(
            123, datetime.datetime.now(), datetime.datetime.now(), meters=["FEEDIN"]
        ) == {"meters": "meters"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/storageData"
        )
        mocked.get(
            pattern,
            payload={"storageData": {"batteryCount": 1, "batteries": []}},
        )
        assert await solar_edge.get_storage_data(
            123, datetime.datetime.now(), datetime.datetime.now()
        ) == {"storageData": {"batteryCount": 1, "batteries": []}}

        serials_pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/storageData.*serials="
        )
        mocked.get(
            serials_pattern,
            payload={"storageData": {"batteryCount": 1, "batteries": []}},
        )
        assert await solar_edge.get_storage_data(
            123,
            datetime.datetime.now(),
            datetime.datetime.now(),
            serials=["SN1", "SN2"],
        ) == {"storageData": {"batteryCount": 1, "batteries": []}}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_sites() -> None:
    """Test getting the list of sites with all options."""
    async with aiointercept(mock_external_urls=True) as mocked:
        solar_edge = SolarEdge("API_KEY")
        mocked.get(
            "https://monitoringapi.solaredge.com/sites/list?api_key=API_KEY",
            payload={"sites": "sites"},
        )
        assert await solar_edge.get_sites() == {"sites": "sites"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/sites/list\?"
            r"(?=.*api_key=API_KEY)(?=.*size=5)(?=.*startIndex=10)(?=.*searchText=Lyon)"
            r"(?=.*sortProperty=Name)(?=.*sortOrder=DESC)(?=.*status=Active).*$"
        )
        mocked.get(pattern, payload={"sites": "filtered"})
        assert await solar_edge.get_sites(
            size=5,
            start_index=10,
            search_text="Lyon",
            sort_property="Name",
            sort_order="DESC",
            status="Active",
        ) == {"sites": "filtered"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_data_period() -> None:
    """Test getting data period for a single site and bulk."""
    async with aiointercept(mock_external_urls=True) as mocked:
        solar_edge = SolarEdge("API_KEY")
        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/dataPeriod?api_key=API_KEY",
            payload={"dataPeriod": "dataPeriod"},
        )
        assert await solar_edge.get_data_period(123) == {"dataPeriod": "dataPeriod"}

        mocked.get(
            "https://monitoringapi.solaredge.com/sites/1,4/dataPeriod?api_key=API_KEY",
            payload={"dataPeriod": "bulk"},
        )
        assert await solar_edge.get_data_period_bulk([1, 4]) == {"dataPeriod": "bulk"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_energy() -> None:
    """Test getting energy and bulk energy."""
    async with aiointercept(mock_external_urls=True) as mocked:
        solar_edge = SolarEdge("API_KEY")
        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/energy\?"
            r"(?=.*startDate=2013-05-01)(?=.*endDate=2013-05-30)(?=.*timeUnit=DAY).*$"
        )
        mocked.get(pattern, payload={"energy": "energy"})
        assert await solar_edge.get_energy(
            123,
            datetime.date(2013, 5, 1),
            datetime.date(2013, 5, 30),
        ) == {"energy": "energy"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/energy\?"
            r"(?=.*startDate=2013-05-01)(?=.*endDate=2013-05-30)(?=.*timeUnit=HOUR).*$"
        )
        mocked.get(pattern, payload={"energy": "energy_str"})
        assert await solar_edge.get_energy(
            123, "2013-05-01", "2013-05-30", time_unit="HOUR"
        ) == {"energy": "energy_str"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/sites/1,4/energy\?"
            r"(?=.*startDate=2013-05-01)(?=.*endDate=2013-05-30)(?=.*timeUnit=DAY).*$"
        )
        mocked.get(pattern, payload={"energy": "bulk"})
        assert await solar_edge.get_energy_bulk(
            [1, 4],
            datetime.date(2013, 5, 1),
            datetime.date(2013, 5, 30),
        ) == {"energy": "bulk"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_time_frame_energy() -> None:
    """Test getting time frame energy and bulk."""
    async with aiointercept(mock_external_urls=True) as mocked:
        solar_edge = SolarEdge("API_KEY")
        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/timeFrameEnergy\?"
            r"(?=.*startDate=2013-05-01)(?=.*endDate=2013-05-06).*$"
        )
        mocked.get(pattern, payload={"timeFrameEnergy": "tfe"})
        assert await solar_edge.get_time_frame_energy(
            123,
            datetime.date(2013, 5, 1),
            datetime.date(2013, 5, 6),
        ) == {"timeFrameEnergy": "tfe"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/sites/1,4/timeFrameEnergy\?"
            r"(?=.*startDate=2013-05-01)(?=.*endDate=2013-05-06).*$"
        )
        mocked.get(pattern, payload={"timeFrameEnergy": "bulk"})
        assert await solar_edge.get_time_frame_energy_bulk(
            [1, 4], "2013-05-01", "2013-05-06"
        ) == {"timeFrameEnergy": "bulk"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_power() -> None:
    """Test getting power and bulk power."""
    async with aiointercept(mock_external_urls=True) as mocked:
        solar_edge = SolarEdge("API_KEY")
        start = datetime.datetime(2013, 6, 4, 11, 0, 0)
        end = datetime.datetime(2013, 6, 4, 14, 0, 0)
        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/power\?"
            r"(?=.*startTime=2013-06-04)(?=.*endTime=2013-06-04).*$"
        )
        mocked.get(pattern, payload={"power": "power"})
        assert await solar_edge.get_power(123, start, end) == {"power": "power"}

        mocked.get(pattern, payload={"power": "power_str"})
        assert await solar_edge.get_power(
            123, "2013-06-04 11:00:00", "2013-06-04 14:00:00"
        ) == {"power": "power_str"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/sites/1,4/power\?"
        )
        mocked.get(pattern, payload={"power": "bulk"})
        assert await solar_edge.get_power_bulk([1, 4], start, end) == {"power": "bulk"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_overview_bulk() -> None:
    """Test getting bulk overview."""
    async with aiointercept(mock_external_urls=True) as mocked:
        solar_edge = SolarEdge("API_KEY")
        mocked.get(
            "https://monitoringapi.solaredge.com/sites/1,4/overview?api_key=API_KEY",
            payload={"overview": "bulk"},
        )
        assert await solar_edge.get_overview_bulk([1, 4]) == {"overview": "bulk"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_power_details() -> None:
    """Test getting power details."""
    async with aiointercept(mock_external_urls=True) as mocked:
        solar_edge = SolarEdge("API_KEY")
        start = datetime.datetime(2015, 11, 21, 11, 0, 0)
        end = datetime.datetime(2015, 11, 21, 11, 30, 0)
        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/powerDetails\?"
        )
        mocked.get(pattern, payload={"powerDetails": "pd"})
        assert await solar_edge.get_power_details(123, start, end) == {
            "powerDetails": "pd"
        }

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/powerDetails\?.*"
            r"meters=PRODUCTION.*CONSUMPTION"
        )
        mocked.get(pattern, payload={"powerDetails": "pd_meters"})
        assert await solar_edge.get_power_details(
            123, start, end, meters=["PRODUCTION", "CONSUMPTION"]
        ) == {"powerDetails": "pd_meters"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_environmental_benefits() -> None:
    """Test getting environmental benefits."""
    async with aiointercept(mock_external_urls=True) as mocked:
        solar_edge = SolarEdge("API_KEY")
        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/envBenefits?api_key=API_KEY",
            payload={"envBenefits": "eb"},
        )
        assert await solar_edge.get_environmental_benefits(123) == {"envBenefits": "eb"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/envBenefits\?.*"
            r"systemUnits=Imperial"
        )
        mocked.get(pattern, payload={"envBenefits": "imperial"})
        assert await solar_edge.get_environmental_benefits(
            123, system_units="Imperial"
        ) == {"envBenefits": "imperial"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_bulk_endpoints_reject_empty_site_ids() -> None:
    """Bulk endpoints fail fast rather than building an invalid /sites// URL."""
    solar_edge = SolarEdge("API_KEY")
    with pytest.raises(ValueError, match="at least one site ID"):
        await solar_edge.get_data_period_bulk([])
    with pytest.raises(ValueError, match="at least one site ID"):
        await solar_edge.get_overview_bulk([])
    with pytest.raises(ValueError, match="at least one site ID"):
        await solar_edge.get_energy_bulk([], "2013-05-01", "2013-05-30")
    with pytest.raises(ValueError, match="at least one site ID"):
        await solar_edge.get_time_frame_energy_bulk([], "2013-05-01", "2013-05-06")
    with pytest.raises(ValueError, match="at least one site ID"):
        await solar_edge.get_power_bulk(
            [], "2013-06-04 11:00:00", "2013-06-04 14:00:00"
        )
    await solar_edge.close()
