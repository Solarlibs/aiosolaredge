import pytest

from aiosolaredge import BatteryStorageData, StorageData, integrate_power


def _telemetry(timestamp, power):
    return {"timeStamp": timestamp, "power": power}


@pytest.mark.parametrize(
    ("telemetries", "expected"),
    [
        # Not enough data points to integrate anything.
        ([], (0.0, 0.0)),
        ([_telemetry("2026-06-05 00:00:00", 1000)], (0.0, 0.0)),
        # Constant 2000 W charge over two hourly intervals -> 2000 Wh charged.
        (
            [
                _telemetry("2026-06-05 00:00:00", 0),
                _telemetry("2026-06-05 01:00:00", 2000),
                _telemetry("2026-06-05 02:00:00", 0),
            ],
            (2000.0, 0.0),
        ),
        # Discharge (negative power) is accumulated as a positive number.
        (
            [
                _telemetry("2026-06-05 00:00:00", 0),
                _telemetry("2026-06-05 01:00:00", -1000),
            ],
            (0.0, 500.0),
        ),
        # Mixed charge then discharge. The middle hour crosses zero at 01:30,
        # so it adds 250 Wh to each side instead of cancelling out.
        (
            [
                _telemetry("2026-06-05 00:00:00", 1000),
                _telemetry("2026-06-05 01:00:00", 1000),
                _telemetry("2026-06-05 02:00:00", -1000),
                _telemetry("2026-06-05 03:00:00", -1000),
            ],
            (1250.0, 1250.0),
        ),
        # Unparsable / missing timestamps are skipped.
        (
            [
                _telemetry("not-a-timestamp", 1000),
                _telemetry("2026-06-05 01:00:00", 2000),
                _telemetry(None, 2000),
            ],
            (0.0, 0.0),
        ),
        # An invalid entry between valid ones does not drop the interval.
        (
            [
                _telemetry("2026-06-05 00:00:00", 1000),
                _telemetry("not-a-timestamp", 5000),
                _telemetry("2026-06-05 02:00:00", 1000),
            ],
            (2000.0, 0.0),
        ),
        # A sign change within an interval is split at the zero crossing,
        # so charge and discharge do not cancel out.
        (
            [
                _telemetry("2026-06-05 00:00:00", 1000),
                _telemetry("2026-06-05 01:00:00", -1000),
            ],
            (250.0, 250.0),
        ),
        # Asymmetric crossing: zero is reached after 45 minutes.
        (
            [
                _telemetry("2026-06-05 00:00:00", 3000),
                _telemetry("2026-06-05 01:00:00", -1000),
            ],
            (1125.0, 125.0),
        ),
        # Discharge to charge.
        (
            [
                _telemetry("2026-06-05 00:00:00", -2000),
                _telemetry("2026-06-05 01:00:00", 2000),
            ],
            (500.0, 500.0),
        ),
        # Non-monotonic timestamps (interval <= 0) are skipped.
        (
            [
                _telemetry("2026-06-05 02:00:00", 2000),
                _telemetry("2026-06-05 01:00:00", 2000),
            ],
            (0.0, 0.0),
        ),
        # Missing power is treated as 0 W.
        (
            [
                _telemetry("2026-06-05 00:00:00", None),
                _telemetry("2026-06-05 01:00:00", 2000),
            ],
            (1000.0, 0.0),
        ),
    ],
)
def test_integrate_power(telemetries, expected):
    assert integrate_power(telemetries) == expected


def test_battery_from_dict():
    battery = {
        "serialNumber": "SN1",
        "modelNumber": "BAT-1",
        "nameplate": 10000,
        "telemetries": [
            _telemetry("2026-06-05 00:00:00", 0) | {"batteryPercentageState": 50},
            _telemetry("2026-06-05 01:00:00", 2000) | {"batteryPercentageState": 70},
        ],
    }
    parsed = BatteryStorageData.from_dict(battery)
    assert parsed is not None
    assert parsed.serial_number == "SN1"
    assert parsed.model_number == "BAT-1"
    assert parsed.nameplate == 10000
    assert parsed.state_of_charge == 70
    assert parsed.power == 2000
    assert parsed.charge_energy == 1000.0
    assert parsed.discharge_energy == 0.0


def test_battery_from_dict_without_serial():
    assert BatteryStorageData.from_dict({"telemetries": []}) is None


def test_battery_from_dict_without_telemetry():
    assert BatteryStorageData.from_dict({"serialNumber": "SN1"}) is None
    assert (
        BatteryStorageData.from_dict({"serialNumber": "SN1", "telemetries": []}) is None
    )


def test_storage_data_from_response_totals():
    response = {
        "storageData": {
            "batteryCount": 2,
            "batteries": [
                {
                    "serialNumber": "SN1",
                    "telemetries": [
                        _telemetry("2026-06-05 00:00:00", 0),
                        _telemetry("2026-06-05 01:00:00", 2000),
                    ],
                },
                {
                    "serialNumber": "SN2",
                    "telemetries": [
                        _telemetry("2026-06-05 00:00:00", 0),
                        _telemetry("2026-06-05 01:00:00", -1000),
                    ],
                },
                # Skipped: no serial number.
                {"telemetries": []},
            ],
        }
    }
    storage = StorageData.from_response(response)
    assert len(storage.batteries) == 2
    assert storage.total_charge_energy == 1000.0
    assert storage.total_discharge_energy == 500.0


def test_storage_data_from_response_empty():
    storage = StorageData.from_response(
        {"storageData": {"batteryCount": 0, "batteries": []}}
    )
    assert storage.batteries == []
    assert storage.total_charge_energy == 0.0
    assert storage.total_discharge_energy == 0.0


def test_storage_data_from_response_missing_keys():
    with pytest.raises(KeyError):
        StorageData.from_response({})
    with pytest.raises(KeyError):
        StorageData.from_response({"storageData": {}})
