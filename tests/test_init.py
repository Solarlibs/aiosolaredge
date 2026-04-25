import datetime
import re

import aiohttp
import pytest
from aioresponses import aioresponses

from aiosolaredge import SolarEdge, SolarEdgeImage


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
    with aioresponses() as mocked:
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
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        mocked.get(
            "https://monitoringapi.solaredge.com/sites/list?api_key=API_KEY",
            payload={"sites": "sites"},
        )
        assert await solar_edge.get_sites() == {"sites": "sites"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/sites/list\?.*"
            r"searchText=Lyon.*size=5.*sortOrder=DESC.*sortProperty=Name.*"
            r"startIndex=10.*status=Active"
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
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/dataPeriod?api_key=API_KEY",
            payload={"dataPeriod": "dataPeriod"},
        )
        assert await solar_edge.get_data_period(123) == {
            "dataPeriod": "dataPeriod"
        }

        mocked.get(
            "https://monitoringapi.solaredge.com/sites/1,4/dataPeriod?api_key=API_KEY",
            payload={"dataPeriod": "bulk"},
        )
        assert await solar_edge.get_data_period_bulk([1, 4]) == {
            "dataPeriod": "bulk"
        }
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_energy() -> None:
    """Test getting energy and bulk energy."""
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/energy\?.*"
            r"endDate=2013-05-30.*startDate=2013-05-01.*timeUnit=DAY"
        )
        mocked.get(pattern, payload={"energy": "energy"})
        assert await solar_edge.get_energy(
            123,
            datetime.date(2013, 5, 1),
            datetime.date(2013, 5, 30),
        ) == {"energy": "energy"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/energy\?.*"
            r"endDate=2013-05-30.*startDate=2013-05-01.*timeUnit=HOUR"
        )
        mocked.get(pattern, payload={"energy": "energy_str"})
        assert await solar_edge.get_energy(
            123, "2013-05-01", "2013-05-30", time_unit="HOUR"
        ) == {"energy": "energy_str"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/sites/1,4/energy\?.*"
            r"endDate=2013-05-30.*startDate=2013-05-01"
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
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/timeFrameEnergy\?.*"
            r"endDate=2013-05-06.*startDate=2013-05-01"
        )
        mocked.get(pattern, payload={"timeFrameEnergy": "tfe"})
        assert await solar_edge.get_time_frame_energy(
            123,
            datetime.date(2013, 5, 1),
            datetime.date(2013, 5, 6),
        ) == {"timeFrameEnergy": "tfe"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/sites/1,4/timeFrameEnergy\?.*"
            r"endDate=2013-05-06.*startDate=2013-05-01"
        )
        mocked.get(pattern, payload={"timeFrameEnergy": "bulk"})
        assert await solar_edge.get_time_frame_energy_bulk(
            [1, 4], "2013-05-01", "2013-05-06"
        ) == {"timeFrameEnergy": "bulk"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_power() -> None:
    """Test getting power and bulk power."""
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        start = datetime.datetime(2013, 6, 4, 11, 0, 0)
        end = datetime.datetime(2013, 6, 4, 14, 0, 0)
        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/power\?.*"
            r"endTime=2013-06-04.*startTime=2013-06-04"
        )
        mocked.get(pattern, payload={"power": "power"})
        assert await solar_edge.get_power(123, start, end) == {"power": "power"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/sites/1,4/power\?"
        )
        mocked.get(pattern, payload={"power": "bulk"})
        assert await solar_edge.get_power_bulk([1, 4], start, end) == {
            "power": "bulk"
        }
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_overview_bulk() -> None:
    """Test getting bulk overview."""
    with aioresponses() as mocked:
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
    with aioresponses() as mocked:
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
async def test_get_storage_data() -> None:
    """Test getting storage data."""
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        start = datetime.datetime(2015, 5, 22, 11, 0, 0)
        end = datetime.datetime(2015, 5, 25, 13, 0, 0)
        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/storageData\?"
        )
        mocked.get(pattern, payload={"storageData": "sd"})
        assert await solar_edge.get_storage_data(123, start, end) == {
            "storageData": "sd"
        }

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/storageData\?.*"
            r"serials=1111.*2222"
        )
        mocked.get(pattern, payload={"storageData": "sd_serials"})
        assert await solar_edge.get_storage_data(
            123, start, end, serials=["1111", "2222"]
        ) == {"storageData": "sd_serials"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_environmental_benefits() -> None:
    """Test getting environmental benefits."""
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/envBenefits?api_key=API_KEY",
            payload={"envBenefits": "eb"},
        )
        assert await solar_edge.get_environmental_benefits(123) == {
            "envBenefits": "eb"
        }

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
async def test_get_components_list() -> None:
    """Test getting components list."""
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        mocked.get(
            "https://monitoringapi.solaredge.com/equipment/123/list?api_key=API_KEY",
            payload={"list": "components"},
        )
        assert await solar_edge.get_components_list(123) == {"list": "components"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_inverter_technical_data() -> None:
    """Test getting inverter technical data."""
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        start = datetime.datetime(2013, 5, 5, 11, 0, 0)
        end = datetime.datetime(2013, 5, 5, 13, 0, 0)
        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/equipment/123/12345678-90/data\?"
        )
        mocked.get(pattern, payload={"data": "inverter"})
        assert await solar_edge.get_inverter_technical_data(
            123, "12345678-90", start, end
        ) == {"data": "inverter"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_equipment_change_log() -> None:
    """Test getting equipment change log."""
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        mocked.get(
            "https://monitoringapi.solaredge.com/equipment/123/12345678-90/changeLog?api_key=API_KEY",
            payload={"ChangeLog": "log"},
        )
        assert await solar_edge.get_equipment_change_log(
            123, "12345678-90"
        ) == {"ChangeLog": "log"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_accounts() -> None:
    """Test getting accounts list."""
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        mocked.get(
            "https://monitoringapi.solaredge.com/accounts/list?api_key=API_KEY",
            payload={"accounts": "accounts"},
        )
        assert await solar_edge.get_accounts() == {"accounts": "accounts"}

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/accounts/list\?.*"
            r"searchText=foo.*size=5.*sortOrder=ASC.*sortProperty=Name.*startIndex=10"
        )
        mocked.get(pattern, payload={"accounts": "filtered"})
        assert await solar_edge.get_accounts(
            size=5,
            start_index=10,
            search_text="foo",
            sort_property="Name",
            sort_order="ASC",
        ) == {"accounts": "filtered"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_meters_data() -> None:
    """Test getting meters data."""
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        start = datetime.datetime(2013, 5, 5, 11, 0, 0)
        end = datetime.datetime(2013, 5, 5, 13, 0, 0)
        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/meters\?"
        )
        mocked.get(pattern, payload={"meterEnergyDetails": "md"})
        assert await solar_edge.get_meters_data(123, start, end) == {
            "meterEnergyDetails": "md"
        }

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/meters\?.*"
            r"meters=PRODUCTION.*CONSUMPTION"
        )
        mocked.get(pattern, payload={"meterEnergyDetails": "md_filtered"})
        assert await solar_edge.get_meters_data(
            123, start, end, meters=["PRODUCTION", "CONSUMPTION"]
        ) == {"meterEnergyDetails": "md_filtered"}
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_sensors() -> None:
    """Test getting sensors list and data."""
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        mocked.get(
            "https://monitoringapi.solaredge.com/equipment/123/sensors?api_key=API_KEY",
            payload={"SiteSensors": "list"},
        )
        assert await solar_edge.get_sensors_list(123) == {"SiteSensors": "list"}

        start = datetime.datetime(2013, 5, 5, 11, 0, 0)
        end = datetime.datetime(2013, 5, 5, 13, 0, 0)
        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/sensors\?"
        )
        mocked.get(pattern, payload={"siteSensors": "data"})
        assert await solar_edge.get_sensors_data(123, start, end) == {
            "siteSensors": "data"
        }
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_versions() -> None:
    """Test getting version endpoints."""
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")
        mocked.get(
            "https://monitoringapi.solaredge.com/version/current?api_key=API_KEY",
            payload={"version": "1.0.0"},
        )
        assert await solar_edge.get_current_version() == {"version": "1.0.0"}

        mocked.get(
            "https://monitoringapi.solaredge.com/version/supported?api_key=API_KEY",
            payload={"supported": ["0.9.5", "1.0.0"]},
        )
        assert await solar_edge.get_supported_versions() == {
            "supported": ["0.9.5", "1.0.0"]
        }
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_site_image() -> None:
    """Test fetching the site image, including 304/404 handling."""
    png_bytes = b"\x89PNG\r\n\x1a\nfake-png-bytes"
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")

        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/siteImage?api_key=API_KEY",
            status=200,
            body=png_bytes,
            headers={"Content-Type": "image/png", "ETag": "abc123"},
        )
        result = await solar_edge.get_site_image(123)
        assert isinstance(result, SolarEdgeImage)
        assert result.content == png_bytes
        assert result.content_type == "image/png"
        assert result.hash == "abc123"

        pattern = re.compile(
            r"^https://monitoringapi\.solaredge\.com/site/123/siteImage/myimage\.jpg\?.*"
            r"hash=abc123.*maxHeight=200.*maxWidth=300"
        )
        mocked.get(
            pattern,
            status=200,
            body=png_bytes,
            headers={"Content-Type": "image/jpeg"},
        )
        result = await solar_edge.get_site_image(
            123,
            name="myimage.jpg",
            max_width=300,
            max_height=200,
            hash="abc123",
        )
        assert isinstance(result, SolarEdgeImage)
        assert result.content_type == "image/jpeg"
        assert result.hash is None

        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/siteImage?api_key=API_KEY",
            status=304,
        )
        assert await solar_edge.get_site_image(123) is None

        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/siteImage?api_key=API_KEY",
            status=404,
        )
        assert await solar_edge.get_site_image(123) is None
        await solar_edge.close()


@pytest.mark.asyncio
async def test_get_installer_image() -> None:
    """Test fetching the installer logo image."""
    jpg_bytes = b"\xff\xd8\xff\xe0fake-jpeg"
    with aioresponses() as mocked:
        solar_edge = SolarEdge("API_KEY")

        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/installerImage?api_key=API_KEY",
            status=200,
            body=jpg_bytes,
            headers={"Content-Type": "image/jpeg"},
        )
        result = await solar_edge.get_installer_image(123)
        assert isinstance(result, SolarEdgeImage)
        assert result.content == jpg_bytes
        assert result.content_type == "image/jpeg"

        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/installerImage/logo.png?api_key=API_KEY",
            status=200,
            body=jpg_bytes,
            headers={"Content-Type": "image/png"},
        )
        result = await solar_edge.get_installer_image(123, name="logo.png")
        assert isinstance(result, SolarEdgeImage)
        assert result.content_type == "image/png"

        mocked.get(
            "https://monitoringapi.solaredge.com/site/123/installerImage?api_key=API_KEY",
            status=404,
        )
        assert await solar_edge.get_installer_image(123) is None
        await solar_edge.close()
