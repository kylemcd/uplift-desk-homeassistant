"""Constants for the UPLIFT Desk integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "uplift_desk"
CONF_CONNECTION_TYPE: Final = "connection_type"
CONF_BROKER_URL: Final = "broker_url"
CONF_DESK_ID: Final = "desk_id"
CONNECTION_BLUETOOTH: Final = "bluetooth"
CONNECTION_BROKER: Final = "broker"
DEFAULT_SCAN_INTERVAL_SECONDS: Final = 5
SUPPORTED_SERVICE_UUIDS: Final = {
    "000000ff-0000-1000-8000-00805f9b34fb",
    "0000fe60-0000-1000-8000-00805f9b34fb",
    "0000ff00-0000-1000-8000-00805f9b34fb",
    "0000ff12-0000-1000-8000-00805f9b34fb",
}
PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]
CONF_VIRTUAL_PRESETS: Final = "virtual_presets"
MM_PER_INCH: Final = 25.4
