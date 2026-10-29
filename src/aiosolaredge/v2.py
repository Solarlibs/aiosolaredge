"""
Read-only SolarEdge Basic Monitoring V2 client.

Protocol: Basic Monitoring 2.1.0, next - 10/2026. The caller owns OAuth
refresh/rotation persistence; credentials never appear in URLs or errors.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

BASE_URL = "https://monitoringapi.solaredge.com/v2"


class SolarEdgeV2Error(Exception):
    """A bounded, redacted API failure."""

    def __init__(self, message: str = "", *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class AuthenticationError(SolarEdgeV2Error):
    """Credentials were rejected."""


class PermissionDeniedError(SolarEdgeV2Error):
    """Site, scope or subscription does not allow this request."""


class InvalidResponseError(SolarEdgeV2Error):
    """The response violates the measurement contract."""


class RateLimitError(SolarEdgeV2Error):
    """No automatic retry is performed, including monthly exhaustion."""

    def __init__(
        self,
        retry_after: str | None,
        *,
        monthly_exhausted: bool = False,
        quota: dict[str, int] | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__("SolarEdge quota exceeded", http_status=http_status)
        self.retry_after = retry_after
        self.monthly_exhausted = monthly_exhausted
        self.quota = quota or {}


@dataclass(frozen=True)
class Reading:
    """A timestamped measurement, in Wh for energy and W for power."""

    value: float | None
    timestamp: datetime


def _timestamp(value: Any) -> datetime:
    if isinstance(value, str) and value.endswith("Z"):
        # Python 3.10's fromisoformat does not accept the ISO UTC designator.
        value = value[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise InvalidResponseError("Invalid measurement timestamp") from None
    if result.utcoffset() is None:
        raise InvalidResponseError("Missing measurement timezone")
    return result


def _number(value: Any, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidResponseError("Invalid measurement value")
    try:
        value = float(value)
    except OverflowError:
        raise InvalidResponseError("Invalid measurement value") from None
    if not math.isfinite(value) or value < 0:
        raise InvalidResponseError("Invalid measurement value")
    return float(value)


def _site_path(site_id: str) -> str:
    if not site_id.isascii() or not site_id.isdecimal():
        raise ValueError("Site ID must contain ASCII digits only")
    return f"/sites/{site_id}"


class SolarEdgeV2:
    """Basic site reads; no fleet enumeration, paid API or device commands."""

    def __init__(
        self,
        session: ClientSession,
        access_token: Callable[[], Awaitable[str]],
        before_request: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._session = session
        self._access_token = access_token
        self._before_request = before_request

    async def _get(
        self,
        path: str,
        params: Any = None,
        *,
        array: bool = False,
    ) -> Any:
        token = await self._access_token()
        if self._before_request is not None:
            await self._before_request()
        status = None
        try:
            async with self._session.get(
                BASE_URL + path,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=ClientTimeout(total=30),
                allow_redirects=False,
            ) as response:
                status = response.status
                if response.status == 401:
                    raise AuthenticationError(
                        "SolarEdge authentication rejected", http_status=401
                    )
                if response.status == 403:
                    raise PermissionDeniedError(
                        "SolarEdge access denied", http_status=403
                    )
                if response.status == 429:
                    quota = {}
                    for axis in ("minute", "month", "second"):
                        for field in ("limit", "remaining"):
                            key = f"x-ratelimit-{field}-{axis}"
                            raw = response.headers.get(key, "").strip()
                            if raw.isascii() and raw.isdecimal() and len(raw) <= 19:
                                parsed = int(raw)
                                if parsed <= 2**63 - 1:
                                    quota[key] = parsed
                    retry_after = response.headers.get("Retry-After")
                    if retry_after is not None and len(retry_after) > 128:
                        retry_after = None
                    raise RateLimitError(
                        retry_after,
                        monthly_exhausted=quota.get("x-ratelimit-remaining-month") == 0,
                        quota=quota,
                        http_status=429,
                    )
                if response.status != 200:
                    raise SolarEdgeV2Error(
                        "SolarEdge request failed", http_status=response.status
                    )
                data = await response.json()
        except (ClientError, TimeoutError):
            raise SolarEdgeV2Error("Connection failed", http_status=status) from None
        except ValueError:
            raise InvalidResponseError("Invalid JSON response") from None
        if not isinstance(data, list if array else dict):
            raise InvalidResponseError("Unexpected response shape")
        return data

    async def site(self, site_id: str) -> dict[str, Any]:
        """Read the authorized site directly; /sites is Fleet-only."""
        return await self._get(_site_path(site_id))

    async def lifetime_energy(self, site_id: str) -> Reading:
        """Read the native onboard production counter, never interval sums."""
        data = await self._get(_site_path(site_id) + "/lifetime-energy")
        try:
            factor = {"WH": 1, "KWH": 1000, "MWH": 1000000, "GWH": 1000000000}[
                data["unit"]
            ]
            value = _number(data["energy"])
            timestamp = _timestamp(data["lastUpdateTime"])
        except (KeyError, TypeError):
            raise InvalidResponseError("Invalid lifetime energy response") from None
        if value is None:
            raise InvalidResponseError("Missing lifetime energy")
        return Reading(_number(value * factor), timestamp)

    async def power(self, site_id: str, now: datetime) -> Reading:
        """
        Return the latest 15-minute sample, not instantaneous power.

        A latest null remains null; older non-null samples must not conceal it.
        """
        path = _site_path(site_id) + "/power"
        if now.utcoffset() is None:
            raise ValueError("A timezone-aware time is required")
        now = now.astimezone(timezone.utc)
        data = await self._get(
            path,
            {
                "from": (now - timedelta(hours=2)).isoformat(),
                "to": now.isoformat(),
                "resolution": "QUARTER_HOUR",
                "unit": "W",
            },
        )
        try:
            if data["unit"] != "W" or data["resolution"] != "QUARTER_HOUR":
                raise InvalidResponseError("Unexpected power units or resolution")
            readings = [
                Reading(
                    _number(item["value"], nullable=True), _timestamp(item["timestamp"])
                )
                for item in data["values"]
            ]
        except (KeyError, TypeError):
            raise InvalidResponseError("Invalid power response") from None
        if not readings:
            raise InvalidResponseError("No power samples")
        reading = max(readings, key=lambda item: item.timestamp)
        if reading.timestamp > now or now - reading.timestamp > timedelta(hours=2):
            raise InvalidResponseError("Power sample outside requested window")
        return reading
