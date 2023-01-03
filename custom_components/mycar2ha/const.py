"""Constants for the Detailed Hello World Push integration."""
from typing import DefaultDict
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_EMAIL

# This is the internal name of the integration, it should also match the directory
# name for the integration.
DOMAIN = "mycar2ha"
NAME = "MyCar2HA"
VERSION = "1.0.1"

CONF_DECIMAL_PLACES = "decial_places"

OPTIONS = [
    #(CONF_DEVICE_NAME, "", cv.string),
    (CONF_EMAIL, "", cv.string),
    (CONF_DECIMAL_PLACES, "2", vol.All(vol.Coerce(int), vol.Range(0, 5))),
]
