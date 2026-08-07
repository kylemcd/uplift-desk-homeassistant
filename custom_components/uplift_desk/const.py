"""Constants for the UPLIFT Desk integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "uplift_desk"
CONF_BROKER_URL: Final = "broker_url"
DEFAULT_BROKER_URL: Final = "https://bluetooth.kpm.house"
DEFAULT_SCAN_INTERVAL_SECONDS: Final = 5
PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.NUMBER,
    Platform.SENSOR,
]
