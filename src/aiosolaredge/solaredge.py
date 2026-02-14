from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable, Literal

import aiohttp
import yarl

_BASE_URL = yarl.URL("https://monitoringapi.solaredge.com")
_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

_LOGGER = logging.getLogger(__name__)


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

    async def get_details(self, site_id: int | str) -> dict[str, Any]:
        """
        Get details of the SolarEdge system.

        :param site_id: The site ID.
        :return: The details of the SolarEdge system.
        """
        return await self._get_json(self._get_site_url(site_id).joinpath("details"))

    async def get_overview(self, site_id: int | str) -> dict[str, Any]:
        """
        Get overview of the SolarEdge system.

        :param site_id: The site ID.
        :return: The overview of the SolarEdge system.
        """
        return await self._get_json(self._get_site_url(site_id).joinpath("overview"))

    async def get_inventory(self, site_id: int | str) -> dict[str, Any]:
        """
        Get inventory of the SolarEdge system.

        :param site_id: The site ID.
        :return: The inventory of the SolarEdge system.
        """
        return await self._get_json(self._get_site_url(site_id).joinpath("inventory"))

    async def get_energy_details(
        self,
        site_id: int | str,
        start_time: datetime,
        end_time: datetime,
        meters: Iterable[
            Literal[
                "PRODUCTION", "CONSUMPTION", "SELFCONSUMPTION", "FEEDIN", "PURCHASED"
            ]
        ] = [],
        time_unit: str = "DAY",
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
            "startTime": start_time.strftime(_DATETIME_FORMAT),
            "endTime": end_time.strftime(_DATETIME_FORMAT),
            "timeUnit": time_unit,
        }
        if meters:
            params["meters"] = ",".join(meters)
        return await self._get_json(url, params=params)

    async def get_storage_data(
        self,
        site_id: int | str,
        start_time: datetime,
        end_time: datetime,
        serials: Iterable[str] = [],
    ) -> dict[str, Any]:
        """
        Get storage data from batteries at the SolarEdge site.

        Returns detailed battery telemetry including charge/discharge energy.
        Limited to a one-week period.

        :param site_id: The site ID.
        :param start_time: The start time.
        :param end_time: The end time.
        :param serials: Optional battery serial numbers to filter by.
        :return: The storage data of the SolarEdge system.
        """
        url = self._get_site_url(site_id).joinpath("storageData")
        params: dict[str, Any] = {
            "startTime": start_time.strftime(_DATETIME_FORMAT),
            "endTime": end_time.strftime(_DATETIME_FORMAT),
        }
        if serials:
            params["serials"] = ",".join(serials)
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
