"""Values the sensors report, per router model."""

import unittest
from types import SimpleNamespace

from custom_components.speedport.sensor import SENSORS, SpeedportSensor

DESCRIPTIONS = {description.key: description for description in SENSORS}


def value(model: str, key: str, raw: str):
    sensor = SimpleNamespace(
        _speedport=SimpleNamespace(device_name=model, get={key: raw}.get),
        entity_description=DESCRIPTIONS[key],
    )
    return SpeedportSensor.native_value.fget(sensor)


class DslLinkRateTest(unittest.TestCase):
    """Issue #19: a Smart 3 showed 224990 bit/s for a link of about 225 Mbit/s."""

    def test_smart_3_reports_kbit(self):
        self.assertEqual(
            value("Speedport Smart 3", "dsl_downstream", "224990"), 224990000
        )
        self.assertEqual(value("Speedport Smart 3", "dsl_upstream", "40000"), 40000000)

    def test_smart_4_reports_bit(self):
        raw = "204416000"
        self.assertEqual(value("Speedport Smart 4", "dsl_downstream", raw), raw)

    def test_other_values_stay_as_reported(self):
        self.assertEqual(value("Speedport Smart 3", "inet_download", "1200"), "1200")
        self.assertEqual(value("Speedport Smart 3", "dsl_downstream", ""), "")


if __name__ == "__main__":
    unittest.main()
