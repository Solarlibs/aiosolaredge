"""Models and parsing for the SolarEdge Monitoring API storage data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from typing import Any

_TELEMETRY_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse a storageData telemetry timestamp, returning None when invalid."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, _TELEMETRY_DATETIME_FORMAT)
    except ValueError:
        return None


def integrate_power(telemetries: list[dict[str, Any]]) -> tuple[float, float]:
    """
    Integrate battery power telemetry into charged and discharged energy.

    SolarEdge frequently reports ``lifeTimeEnergyCharged`` and
    ``lifeTimeEnergyDischarged`` as 0 in the ``storageData`` response, even
    while the battery is actively charging or discharging. The ``power``
    telemetry is reliably populated though, so the energy (Wh) is derived by
    trapezoidal integration of the power (W) over time. Positive power means
    the battery is charging, negative power means it is discharging.

    :param telemetries: The ``telemetries`` list of a single battery, ordered
        chronologically. Each entry is expected to have a ``timeStamp``
        (``"%Y-%m-%d %H:%M:%S"``) and a ``power`` value in Watts.
    :return: A ``(charge_energy, discharge_energy)`` tuple in Wh.
    """
    charge_energy = 0.0
    discharge_energy = 0.0
    for previous, current in pairwise(telemetries):
        previous_time = _parse_timestamp(previous.get("timeStamp"))
        current_time = _parse_timestamp(current.get("timeStamp"))
        if previous_time is None or current_time is None:
            continue
        interval = (current_time - previous_time).total_seconds() / 3600
        if interval <= 0:
            continue
        # Trapezoidal integration of power (W) over the interval (h) -> Wh.
        average_power = (
            (previous.get("power") or 0.0) + (current.get("power") or 0.0)
        ) / 2
        energy = average_power * interval
        if energy >= 0:
            charge_energy += energy
        else:
            discharge_energy -= energy
    return charge_energy, discharge_energy


@dataclass(slots=True)
class BatteryStorageData:
    """
    Parsed storage data for a single battery.

    The ``charge_energy`` and ``discharge_energy`` values are derived by
    integrating the ``power`` telemetry rather than read from
    ``lifeTimeEnergyCharged`` / ``lifeTimeEnergyDischarged``, because SolarEdge
    frequently reports those lifetime counters as 0 in the ``storageData``
    response even while the battery is actively cycling.
    """

    serial_number: str
    model_number: str | None
    nameplate: float | None
    state_of_charge: float | None
    power: float | None
    charge_energy: float
    discharge_energy: float

    @classmethod
    def from_dict(cls, battery: dict[str, Any]) -> BatteryStorageData | None:
        """
        Create a ``BatteryStorageData`` from a raw ``storageData`` battery.

        :param battery: A single entry from ``storageData.batteries``.
        :return: The parsed battery, or ``None`` when the battery has no serial
            number or no telemetry to derive values from.
        """
        serial_number = battery.get("serialNumber")
        if not serial_number:
            return None
        telemetries = battery.get("telemetries") or []
        if not telemetries:
            return None
        latest = telemetries[-1]
        charge_energy, discharge_energy = integrate_power(telemetries)
        return cls(
            serial_number=serial_number,
            model_number=battery.get("modelNumber"),
            nameplate=battery.get("nameplate"),
            state_of_charge=latest.get("batteryPercentageState"),
            power=latest.get("power"),
            charge_energy=charge_energy,
            discharge_energy=discharge_energy,
        )


@dataclass(slots=True)
class StorageData:
    """Parsed storage data for all batteries at a SolarEdge site."""

    batteries: list[BatteryStorageData] = field(default_factory=list)

    @property
    def total_charge_energy(self) -> float:
        """Total charged energy across all batteries in Wh."""
        return sum(battery.charge_energy for battery in self.batteries)

    @property
    def total_discharge_energy(self) -> float:
        """Total discharged energy across all batteries in Wh."""
        return sum(battery.discharge_energy for battery in self.batteries)

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> StorageData:
        """
        Create ``StorageData`` from a raw ``storageData`` API response.

        :param response: The JSON returned by the ``storageData`` endpoint.
        :raises KeyError: if the response is missing ``storageData`` or its
            ``batteries`` list.
        :return: The parsed storage data; batteries without a serial number or
            telemetry are skipped.
        """
        batteries = response["storageData"]["batteries"]
        parsed = [
            parsed_battery
            for battery in batteries
            if (parsed_battery := BatteryStorageData.from_dict(battery)) is not None
        ]
        return cls(batteries=parsed)
