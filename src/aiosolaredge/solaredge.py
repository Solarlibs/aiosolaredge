from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Iterable, Literal

import aiohttp
import yarl

_BASE_URL = yarl.URL("https://monitoringapi.solaredge.com")
_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_DATE_FORMAT = "%Y-%m-%d"

_LOGGER = logging.getLogger(__name__)

Meter = Literal[
    "PRODUCTION", "CONSUMPTION", "SELFCONSUMPTION", "FEEDIN", "PURCHASED"
]
TimeUnit = Literal[
    "QUARTER_OF_AN_HOUR", "HOUR", "DAY", "WEEK", "MONTH", "YEAR"
]
SystemUnits = Literal["Metrics", "Imperial"]
SortOrder = Literal["ASC", "DESC"]


def _format_date(value: date | datetime | str) -> str:
    """Format a date value for the SolarEdge API (YYYY-MM-DD)."""
    if isinstance(value, str):
        return value
    return value.strftime(_DATE_FORMAT)


def _format_datetime(value: datetime | str) -> str:
    """Format a datetime value for the SolarEdge API (YYYY-MM-DD hh:mm:ss)."""
    if isinstance(value, str):
        return value
    return value.strftime(_DATETIME_FORMAT)


def _join_ids(site_ids: Iterable[int | str]) -> str:
    """Join site IDs with a comma for bulk API calls."""
    return ",".join(str(site_id) for site_id in site_ids)


class SolarEdge:
    """SolarEdge API client."""

    def __init__(
        self,
        api_key: str,
        session: aiohttp.ClientSession | None = None,
        timeout: int = 10,
    ) -> None:
        """Initialize the SolarEdge API client."""
        self.api_key = api_key
        self.session = session or aiohttp.ClientSession()
        self._created_session = not session
        self.timeout = timeout

    async def close(self) -> None:
        """Close the SolarEdge API client."""
        if self._created_session:
            await self.session.close()

    def _get_site_url(self, site_id: int | str) -> yarl.URL:
        """Get the site URL."""
        return _BASE_URL.joinpath("site", str(site_id))

    def _get_sites_url(self, site_ids: Iterable[int | str]) -> yarl.URL:
        """Get the bulk sites URL."""
        return _BASE_URL.joinpath("sites", _join_ids(site_ids))

    def _get_equipment_url(self, site_id: int | str) -> yarl.URL:
        """Get the equipment URL."""
        return _BASE_URL.joinpath("equipment", str(site_id))

    async def get_sites(
        self,
        size: int | None = None,
        start_index: int | None = None,
        search_text: str | None = None,
        sort_property: str | None = None,
        sort_order: SortOrder | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """
        Get the list of sites for the given account API key.

        :param size: Maximum number of sites to return (default 100, max 100).
        :param start_index: First site index to be returned in the results.
        :param search_text: Search text for sites
            (Name, Notes, Address, City, Zip, Full address, Country).
        :param sort_property: Sorting option for the site list (e.g. "Name",
            "Country", "Status", "PeakPower", "InstallationDate", etc.).
        :param sort_order: Sort order: "ASC" or "DESC" (default "ASC").
        :param status: Filter sites by status. A comma-separated combination
            of "Active", "Pending", "Disabled" or "All".
        :return: The list of sites.
        """
        params: dict[str, Any] = {}
        if size is not None:
            params["size"] = size
        if start_index is not None:
            params["startIndex"] = start_index
        if search_text is not None:
            params["searchText"] = search_text
        if sort_property is not None:
            params["sortProperty"] = sort_property
        if sort_order is not None:
            params["sortOrder"] = sort_order
        if status is not None:
            params["status"] = status
        return await self._get_json(
            _BASE_URL.joinpath("sites", "list"), params=params
        )

    async def get_details(self, site_id: int | str) -> dict[str, Any]:
        """
        Get details of the SolarEdge system.

        :param site_id: The site ID.
        :return: The details of the SolarEdge system.
        """
        return await self._get_json(self._get_site_url(site_id).joinpath("details"))

    async def get_data_period(self, site_id: int | str) -> dict[str, Any]:
        """
        Get the energy production start and end dates for the site.

        :param site_id: The site ID.
        :return: The data period.
        """
        return await self._get_json(
            self._get_site_url(site_id).joinpath("dataPeriod")
        )

    async def get_data_period_bulk(
        self, site_ids: Iterable[int | str]
    ) -> dict[str, Any]:
        """
        Get the energy production start and end dates for multiple sites.

        :param site_ids: An iterable of site IDs (up to 100).
        :return: The data period for each site.
        """
        return await self._get_json(
            self._get_sites_url(site_ids).joinpath("dataPeriod")
        )

    async def get_energy(
        self,
        site_id: int | str,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
        time_unit: TimeUnit = "DAY",
    ) -> dict[str, Any]:
        """
        Get site energy measurements.

        :param site_id: The site ID.
        :param start_date: The start date.
        :param end_date: The end date.
        :param time_unit: Aggregation granularity. Default "DAY".
            Allowed values: "QUARTER_OF_AN_HOUR", "HOUR", "DAY",
            "WEEK", "MONTH", "YEAR".
        :return: Site energy measurements.
        """
        params = {
            "startDate": _format_date(start_date),
            "endDate": _format_date(end_date),
            "timeUnit": time_unit,
        }
        return await self._get_json(
            self._get_site_url(site_id).joinpath("energy"), params=params
        )

    async def get_energy_bulk(
        self,
        site_ids: Iterable[int | str],
        start_date: date | datetime | str,
        end_date: date | datetime | str,
        time_unit: TimeUnit = "DAY",
    ) -> dict[str, Any]:
        """
        Get site energy measurements for multiple sites.

        :param site_ids: An iterable of site IDs (up to 100).
        :param start_date: The start date.
        :param end_date: The end date.
        :param time_unit: Aggregation granularity. Default "DAY".
        :return: Site energy measurements per site.
        """
        params = {
            "startDate": _format_date(start_date),
            "endDate": _format_date(end_date),
            "timeUnit": time_unit,
        }
        return await self._get_json(
            self._get_sites_url(site_ids).joinpath("energy"), params=params
        )

    async def get_time_frame_energy(
        self,
        site_id: int | str,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
    ) -> dict[str, Any]:
        """
        Get the site total energy produced for a given time period.

        :param site_id: The site ID.
        :param start_date: The start date.
        :param end_date: The end date.
        :return: The total energy for the period.
        """
        params = {
            "startDate": _format_date(start_date),
            "endDate": _format_date(end_date),
        }
        return await self._get_json(
            self._get_site_url(site_id).joinpath("timeFrameEnergy"),
            params=params,
        )

    async def get_time_frame_energy_bulk(
        self,
        site_ids: Iterable[int | str],
        start_date: date | datetime | str,
        end_date: date | datetime | str,
    ) -> dict[str, Any]:
        """
        Get the total energy produced for a given time period for multiple sites.

        :param site_ids: An iterable of site IDs (up to 100).
        :param start_date: The start date.
        :param end_date: The end date.
        :return: The total energy per site.
        """
        params = {
            "startDate": _format_date(start_date),
            "endDate": _format_date(end_date),
        }
        return await self._get_json(
            self._get_sites_url(site_ids).joinpath("timeFrameEnergy"),
            params=params,
        )

    async def get_power(
        self,
        site_id: int | str,
        start_time: datetime | str,
        end_time: datetime | str,
    ) -> dict[str, Any]:
        """
        Get site power measurements at 15-minute resolution.

        :param site_id: The site ID.
        :param start_time: The start time.
        :param end_time: The end time.
        :return: Site power measurements.
        """
        params = {
            "startTime": _format_datetime(start_time),
            "endTime": _format_datetime(end_time),
        }
        return await self._get_json(
            self._get_site_url(site_id).joinpath("power"), params=params
        )

    async def get_power_bulk(
        self,
        site_ids: Iterable[int | str],
        start_time: datetime | str,
        end_time: datetime | str,
    ) -> dict[str, Any]:
        """
        Get power measurements at 15-minute resolution for multiple sites.

        :param site_ids: An iterable of site IDs (up to 100).
        :param start_time: The start time.
        :param end_time: The end time.
        :return: Site power measurements per site.
        """
        params = {
            "startTime": _format_datetime(start_time),
            "endTime": _format_datetime(end_time),
        }
        return await self._get_json(
            self._get_sites_url(site_ids).joinpath("power"), params=params
        )

    async def get_overview(self, site_id: int | str) -> dict[str, Any]:
        """
        Get overview of the SolarEdge system.

        :param site_id: The site ID.
        :return: The overview of the SolarEdge system.
        """
        return await self._get_json(self._get_site_url(site_id).joinpath("overview"))

    async def get_overview_bulk(
        self, site_ids: Iterable[int | str]
    ) -> dict[str, Any]:
        """
        Get overview data for multiple sites.

        :param site_ids: An iterable of site IDs (up to 100).
        :return: The overview per site.
        """
        return await self._get_json(
            self._get_sites_url(site_ids).joinpath("overview")
        )

    async def get_power_details(
        self,
        site_id: int | str,
        start_time: datetime | str,
        end_time: datetime | str,
        meters: Iterable[Meter] = (),
    ) -> dict[str, Any]:
        """
        Get detailed site power measurements from meters.

        :param site_id: The site ID.
        :param start_time: The start time.
        :param end_time: The end time.
        :param meters: Optional iterable of meter types
            (PRODUCTION, CONSUMPTION, SELFCONSUMPTION, FEEDIN, PURCHASED).
        :return: Detailed site power measurements.
        """
        params: dict[str, Any] = {
            "startTime": _format_datetime(start_time),
            "endTime": _format_datetime(end_time),
        }
        if meters:
            params["meters"] = ",".join(meters)
        return await self._get_json(
            self._get_site_url(site_id).joinpath("powerDetails"), params=params
        )

    async def get_energy_details(
        self,
        site_id: int | str,
        start_time: datetime,
        end_time: datetime,
        meters: Iterable[Meter] = (),
        time_unit: TimeUnit = "DAY",
    ) -> dict[str, Any]:
        """
        Get energy details of the SolarEdge system.

        :param site_id: The site ID.
        :param start_time: The start time.
        :param end_time: The end time.
        :param meters: The meters.
               an iterable of PRODUCTION,CONSUMPTION,SELFCONSUMPTION,FEEDIN,PURCHASED
        :param time_unit: The time unit.
               one of "QUARTER_OF_AN_HOUR", "HOUR", "DAY", "WEEK", "MONTH", "YEAR"
        :return: The energy details of the SolarEdge system.
        """
        url = self._get_site_url(site_id).joinpath("energyDetails")
        params = {
            "startTime": _format_datetime(start_time),
            "endTime": _format_datetime(end_time),
            "timeUnit": time_unit,
        }
        if meters:
            params["meters"] = ",".join(meters)
        return await self._get_json(url, params=params)

    async def get_current_power_flow(self, site_id: int | str) -> dict[str, Any]:
        """
        Get current power flow of the SolarEdge system.

        :param site_id: The site ID.
        :return: The current power flow of the SolarEdge system.
        """
        return await self._get_json(
            self._get_site_url(site_id).joinpath("currentPowerFlow")
        )

    async def get_storage_data(
        self,
        site_id: int | str,
        start_time: datetime | str,
        end_time: datetime | str,
        serials: Iterable[str] = (),
    ) -> dict[str, Any]:
        """
        Get detailed storage information from batteries.

        :param site_id: The site ID.
        :param start_time: The start time.
        :param end_time: The end time.
        :param serials: Optional iterable of battery serial numbers.
        :return: Storage data.
        """
        params: dict[str, Any] = {
            "startTime": _format_datetime(start_time),
            "endTime": _format_datetime(end_time),
        }
        if serials:
            params["serials"] = ",".join(serials)
        return await self._get_json(
            self._get_site_url(site_id).joinpath("storageData"), params=params
        )

    async def get_environmental_benefits(
        self,
        site_id: int | str,
        system_units: SystemUnits | None = None,
    ) -> dict[str, Any]:
        """
        Get environmental benefits based on site energy production.

        :param site_id: The site ID.
        :param system_units: Optional unit system: "Metrics" or "Imperial".
        :return: Environmental benefits (CO2 saved, trees planted, etc.).
        """
        params: dict[str, Any] = {}
        if system_units is not None:
            params["systemUnits"] = system_units
        return await self._get_json(
            self._get_site_url(site_id).joinpath("envBenefits"), params=params
        )

    async def get_inventory(self, site_id: int | str) -> dict[str, Any]:
        """
        Get inventory of the SolarEdge system.

        :param site_id: The site ID.
        :return: The inventory of the SolarEdge system.
        """
        return await self._get_json(self._get_site_url(site_id).joinpath("inventory"))

    async def get_components_list(self, site_id: int | str) -> dict[str, Any]:
        """
        Get the list of inverters/SMIs in the site.

        :param site_id: The site ID.
        :return: The components list.
        """
        return await self._get_json(
            self._get_equipment_url(site_id).joinpath("list")
        )

    async def get_inverter_technical_data(
        self,
        site_id: int | str,
        serial_number: str,
        start_time: datetime | str,
        end_time: datetime | str,
    ) -> dict[str, Any]:
        """
        Get technical data for a specific inverter.

        :param site_id: The site ID.
        :param serial_number: The inverter short serial number.
        :param start_time: The start time.
        :param end_time: The end time.
        :return: Inverter technical data.
        """
        params = {
            "startTime": _format_datetime(start_time),
            "endTime": _format_datetime(end_time),
        }
        return await self._get_json(
            self._get_equipment_url(site_id).joinpath(serial_number, "data"),
            params=params,
        )

    async def get_equipment_change_log(
        self, site_id: int | str, serial_number: str
    ) -> dict[str, Any]:
        """
        Get the equipment change log for a component.

        :param site_id: The site ID.
        :param serial_number: Inverter, battery, optimizer or gateway short
            serial number.
        :return: Equipment change log.
        """
        return await self._get_json(
            self._get_equipment_url(site_id).joinpath(serial_number, "changeLog")
        )

    async def get_accounts(
        self,
        size: int | None = None,
        start_index: int | None = None,
        search_text: str | None = None,
        sort_property: str | None = None,
        sort_order: SortOrder | None = None,
    ) -> dict[str, Any]:
        """
        Get the account and list of sub-accounts for the API key.

        :param size: Maximum number of accounts to return (default 100).
        :param start_index: First account index to be returned in the results.
        :param search_text: Search text for accounts
            (Name, Notes, Email, Country, State, City, Zip, Full address).
        :param sort_property: Sorting option for the account list.
        :param sort_order: Sort order: "ASC" or "DESC" (default "ASC").
        :return: The accounts list.
        """
        params: dict[str, Any] = {}
        if size is not None:
            params["size"] = size
        if start_index is not None:
            params["startIndex"] = start_index
        if search_text is not None:
            params["searchText"] = search_text
        if sort_property is not None:
            params["sortProperty"] = sort_property
        if sort_order is not None:
            params["sortOrder"] = sort_order
        return await self._get_json(
            _BASE_URL.joinpath("accounts", "list"), params=params
        )

    async def get_meters_data(
        self,
        site_id: int | str,
        start_time: datetime | str,
        end_time: datetime | str,
        meters: Iterable[Meter] = (),
        time_unit: TimeUnit = "DAY",
    ) -> dict[str, Any]:
        """
        Get meters data for the site.

        :param site_id: The site ID.
        :param start_time: The start time.
        :param end_time: The end time.
        :param meters: Optional iterable of meter types
            (PRODUCTION, CONSUMPTION, FEEDIN, PURCHASED).
        :param time_unit: Aggregation granularity. Default "DAY".
        :return: Meters data.
        """
        params: dict[str, Any] = {
            "startTime": _format_datetime(start_time),
            "endTime": _format_datetime(end_time),
            "timeUnit": time_unit,
        }
        if meters:
            params["meters"] = ",".join(meters)
        return await self._get_json(
            self._get_site_url(site_id).joinpath("meters"), params=params
        )

    async def get_sensors_list(self, site_id: int | str) -> dict[str, Any]:
        """
        Get the list of sensors installed at the site.

        :param site_id: The site ID.
        :return: The sensors list.
        """
        return await self._get_json(
            self._get_equipment_url(site_id).joinpath("sensors")
        )

    async def get_sensors_data(
        self,
        site_id: int | str,
        start_date: datetime | str,
        end_date: datetime | str,
    ) -> dict[str, Any]:
        """
        Get the data measured by all sensors at the site.

        :param site_id: The site ID.
        :param start_date: The start date+time.
        :param end_date: The end date+time.
        :return: Sensor data.
        """
        params = {
            "startDate": _format_datetime(start_date),
            "endDate": _format_datetime(end_date),
        }
        return await self._get_json(
            self._get_site_url(site_id).joinpath("sensors"), params=params
        )

    async def get_current_version(self) -> dict[str, Any]:
        """
        Get the current SolarEdge API version.

        :return: The current version.
        """
        return await self._get_json(_BASE_URL.joinpath("version", "current"))

    async def get_supported_versions(self) -> dict[str, Any]:
        """
        Get the list of supported SolarEdge API versions.

        :return: The supported versions.
        """
        return await self._get_json(_BASE_URL.joinpath("version", "supported"))

    async def _get_json(
        self, url: yarl.URL, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Get JSON from the SolarEdge API."""
        _LOGGER.debug("Calling %s with params: %s", url, params)
        response = await self.session.get(
            url,
            params={"api_key": self.api_key, **(params or {})},
            timeout=self.timeout,
        )
        _LOGGER.debug("Response from %s: %s", url, response.status)
        response.raise_for_status()
        json = await response.json()
        _LOGGER.debug("JSON from %s: %s", url, json)
        return json
