"""Basic V2 mappings for native monitoring; no Advanced/control requests."""

from datetime import datetime, timezone
from typing import Any

from zoneinfo import ZoneInfo

from .v2 import (
    InvalidResponseError,
    Reading,
    SolarEdgeV2,
    _number,
    _site_path,
    _timestamp,
)

ENERGY_FACTORS = {"WH": 1, "KWH": 1000, "MWH": 1000000, "GWH": 1000000000}
INVENTORY = {
    "inverters": "INVERTER",
    "meters": "METER",
    "batteries": "BATTERY",
    "gateways": "GATEWAY",
}
DAILY_FIELDS = {
    "production_energy": ("production", "total"),
    "purchased_energy": ("consumption", "fromGrid"),
    "consumption_energy": ("consumption", "total"),
    "selfconsumption_energy": ("production", "toSelfConsumption"),
    "feedin_energy": ("production", "toGrid"),
}


def period_start(now: datetime, zone: str, period: str) -> datetime:
    """Calendar boundaries in the site's zone, not the HA server's zone."""
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware time required")
    local = now.astimezone(ZoneInfo(zone))
    start = local.replace(hour=0, minute=0, second=0, microsecond=0, fold=0)
    if period in ("month", "year"):
        start = start.replace(day=1)
    if period == "year":
        start = start.replace(month=1)
    if period not in ("day", "month", "year"):
        raise ValueError("Unknown calendar period")
    return start


def energy(value: Any, unit: Any) -> float | None:
    """Preserve null and reject overflow after unit conversion."""
    try:
        factor = ENERGY_FACTORS[unit]
    except (KeyError, TypeError):
        raise InvalidResponseError("Invalid energy unit") from None
    number = _number(value, nullable=True)
    return None if number is None else _number(number * factor)


class StorageMembershipChanged(InvalidResponseError):
    """Valid site-wide counters require scheduled inventory reconciliation."""


class BasicMonitoring(SolarEdgeV2):
    """Direct authoritative range totals, bounded inventory and daily counters."""

    async def overview(
        self, site_id: str, now: datetime, zone: str, period: str
    ) -> dict[str, Reading]:
        """Range end is a request boundary, NOT a source observation timestamp."""
        start = period_start(now, zone, period)
        now = now.astimezone(timezone.utc)
        data = await self._get(
            _site_path(site_id) + "/overview",
            {"from": start.isoformat(), "to": now.isoformat()},
        )
        if str(data.get("siteId")) != site_id:
            raise InvalidResponseError("Site mismatch")
        fields = {
            f"energy_{'today' if period == 'day' else 'this_' + period}": (
                "production",
                "total",
            )
        }
        if period == "day":
            fields.update(DAILY_FIELDS)
        result = {}
        for key, (section, field) in fields.items():
            part = data.get(section)
            if part is None:
                value = None
            elif not isinstance(part, dict):
                raise InvalidResponseError("Invalid overview section")
            else:
                raw = part.get(field)
                value = None if raw is None else energy(raw, part.get("unit"))
            result[key] = Reading(value, now)
        return result

    async def inventory(self, site_id: str) -> dict[str, list[dict[str, Any]]]:
        """
        Request native device types explicitly, not just the inverter default.

        Meters are identified per role: one physical meter is listed once per
        meterType (e.g. FeedIn and Purchased), and calculated meters with form
        "virtual" carry no serial. Every other device needs a unique serial.
        """
        data = await self._get(
            _site_path(site_id) + "/devices",
            [("types", kind) for kind in INVENTORY.values()],
            array=True,
        )
        result: dict[str, list[dict[str, Any]]] = {key: [] for key in INVENTORY}
        seen: set[tuple[Any, ...]] = set()
        for item in data:
            if not isinstance(item, dict):
                raise InvalidResponseError("Invalid inventory device")
            kind = item.get("type")
            serial = item.get("serialNumber")
            virtual_meter = kind == "METER" and item.get("form") == "virtual"
            if not (isinstance(serial, str) and serial) and not (
                virtual_meter and serial is None
            ):
                raise InvalidResponseError("Invalid inventory device")
            identity: tuple[Any, ...] = (kind, serial)
            if kind == "METER":
                identity += (item.get("meterType"),)
            if kind not in INVENTORY.values() or identity in seen:
                raise InvalidResponseError("Unexpected or duplicate inventory device")
            seen.add(identity)
            key = next(key for key, value in INVENTORY.items() if value == kind)
            result[key].append(
                {
                    field: item[field]
                    for field in (
                        "serialNumber",
                        "manufacturer",
                        "model",
                        "firmware",
                        "nameplate",
                        "type",
                        "active",
                        "meterType",
                        "form",
                    )
                    if field in item
                }
            )
        return result

    async def storage_daily(
        self, site_id: str, now: datetime, zone: str, serials: list[str]
    ) -> dict[str, Reading]:
        """Match V1 first-to-last counter deltas without inventing missing values."""
        start = period_start(now, zone, "day").astimezone(timezone.utc)
        now = now.astimezone(timezone.utc)
        data = await self._get(
            _site_path(site_id) + "/storage/lifetime-energy",
            {"from": start.isoformat(), "to": now.isoformat()},
        )
        batteries = data.get("batteries")
        if not isinstance(batteries, list):
            raise InvalidResponseError("Missing battery counters")
        result = {}
        seen = set()
        for battery in batteries:
            if (
                not isinstance(battery, dict)
                or not isinstance(battery.get("serialNumber"), str)
                or not battery["serialNumber"].strip()
                or battery["serialNumber"] in seen
            ):
                raise InvalidResponseError("Invalid battery identity")
            seen.add(battery["serialNumber"])
        if seen.difference(serials):
            # Do not invent inventory from telemetry or fetch devices outside its
            # cadence. The caller can gate storage until scheduled discovery.
            raise StorageMembershipChanged("Storage membership requires inventory")
        for battery in batteries:
            serial = battery["serialNumber"]
            for key, field in (
                ("charge", "lifetimeEnergyCharged"),
                ("discharge", "lifetimeEnergyDischarged"),
            ):
                values = battery.get(field)
                if not isinstance(values, list):
                    raise InvalidResponseError("Invalid battery samples")
                try:
                    samples = sorted(
                        (
                            Reading(
                                energy(item["value"], battery.get("unit")),
                                _timestamp(item["timestamp"]),
                            )
                            for item in values
                        ),
                        key=lambda reading: reading.timestamp,
                    )
                except (KeyError, TypeError):
                    raise InvalidResponseError("Invalid battery sample") from None
                if any(
                    sample.timestamp < start or sample.timestamp > now
                    for sample in samples
                ) or len({sample.timestamp for sample in samples}) != len(samples):
                    raise InvalidResponseError("Invalid battery sample window")
                observed = [
                    sample.value for sample in samples if sample.value is not None
                ]
                if any(after < before for before, after in zip(observed, observed[1:])):
                    raise InvalidResponseError("Battery counter reset")
                value = None
                if (
                    len(samples) >= 2
                    and samples[0].value is not None
                    and samples[-1].value is not None
                ):
                    value = _number(samples[-1].value - samples[0].value)
                # No fake midnight value: preserve V1's observed first/last delta.
                result[f"{serial}_battery_{key}_energy"] = Reading(
                    value, samples[-1].timestamp if samples else now
                )
        for serial in serials:
            for key in ("charge", "discharge"):
                result.setdefault(f"{serial}_battery_{key}_energy", Reading(None, now))
        for key in ("charge", "discharge"):
            readings = [result[f"{serial}_battery_{key}_energy"] for serial in serials]
            value = None
            if readings and all(reading.value is not None for reading in readings):
                value = _number(
                    sum(
                        reading.value
                        for reading in readings
                        if reading.value is not None
                    )
                )
            result[f"storage_{key}_energy"] = Reading(
                value, min((reading.timestamp for reading in readings), default=now)
            )
        return result
