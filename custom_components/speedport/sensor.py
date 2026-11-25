from datetime import datetime

from homeassistant.components.sensor import (
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfDataRate,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util
from .speedport_api import Speedport

from .const import DOMAIN
from .device import SpeedportEntity, get_coordinator

# The Speedport Smart 3 reports the DSL link rates in kbit/s, the Smart 4 in
# bit/s (#19). Confirmed for the downstream value; the upstream value is taken
# to follow the same unit.
SMART_3_KBIT = {"dsl_downstream", "dsl_upstream"}

SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="public_ip_v4",
        name="IPv4",
        icon="mdi:earth",
    ),
    SensorEntityDescription(
        key="public_ip_v6",
        name="IPv6",
        icon="mdi:earth",
    ),
    SensorEntityDescription(
        key="inet_uptime",
        name="Internet Uptime",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="inet_upload",
        name="Upload",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        icon="mdi:upload",
    ),
    SensorEntityDescription(
        key="inet_download",
        name="Download",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        icon="mdi:download",
    ),
    SensorEntityDescription(
        key="dsl_upstream",
        name="DSL-Link Upstream",
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        icon="mdi:upload",
    ),
    SensorEntityDescription(
        key="dsl_downstream",
        name="DSL-Link Downstream",
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        icon="mdi:download",
    ),
    SensorEntityDescription(
        key="router_state",
        name="Router State",
        icon="mdi:router-wireless",
    ),
    SensorEntityDescription(
        key="dsl_pop",
        name="DSL-PoP",
        icon="mdi:map-marker-radius",
    ),
    SensorEntityDescription(
        key="ex5g_signal_5g",
        name="5G Signal",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        icon="mdi:signal",
    ),
    SensorEntityDescription(
        key="ex5g_freq_5g", name="5G Frequency", icon="mdi:signal-5g"
    ),
    SensorEntityDescription(
        key="ex5g_signal_lte",
        name="LTE Signal",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        icon="mdi:signal",
    ),
    SensorEntityDescription(
        key="ex5g_freq_lte", name="LTE Frequency", icon="mdi:signal-4g"
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up entry."""
    speedport: Speedport = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _add_new_sensors() -> None:
        # Values that need a login can be missing at setup and arrive later.
        new = [
            description
            for description in SENSORS
            if description.key not in known
            and speedport.get(description.key) is not None
        ]
        known.update(description.key for description in new)
        if new:
            async_add_entities(
                SpeedportSensor(hass, speedport, description) for description in new
            )

    _add_new_sensors()
    entry.async_on_unload(
        get_coordinator(hass, speedport).async_add_listener(_add_new_sensors)
    )


class SpeedportSensor(SpeedportEntity, SensorEntity):
    entity_description: SensorEntityDescription

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        if (data := self._speedport.get(self.entity_description.key)) is None:
            return None
        if self.entity_description.device_class == SensorDeviceClass.TIMESTAMP:
            date = datetime.strptime(data, "%Y-%m-%d %H:%M:%S").replace(second=0)
            # Der Router meldet Ortszeit. Die Zeitzone der Instanz ist geladen; pytz.timezone()
            # las seine Datei in der Event-Schleife und HA meldete das als blockierend.
            return date.replace(tzinfo=dt_util.get_default_time_zone())
        if (
            self.entity_description.key in SMART_3_KBIT
            and "Smart 3" in self._speedport.device_name
            and data.isdigit()
        ):
            return int(data) * 1000
        return data

    @property
    def available(self) -> bool:
        if self._speedport.get(self.entity_description.key) is None:
            return False
        return super().available
