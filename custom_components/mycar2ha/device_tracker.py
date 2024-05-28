"""Platform for sensor integration."""
# This file shows the setup for the sensors associated with the cover.
# They are setup in the same way with the call to the async_setup_entry function
# via HA from the module __init__. Each sensor has a device_class, this tells HA how
# to display it in the UI (for know types). The unit_of_measurement property tells HA
# what the unit is, so it can display the correct range. For predefined types (such as
# battery), the unit_of_measurement should match what's expected.
import logging
from threading import Timer
from xmlrpc.client import boolean
import aiohttp
from typing import Optional

import json
import asyncio

import os
from homeassistant.helpers.entity import Entity
from pkg_resources import get_provider

from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    STATE_HOME,
    STATE_NOT_HOME,
)

import re
from .const import *
from homeassistant.components import zone
from homeassistant.helpers.entity import Iterable, DEVICE_DEFAULT_NAME, slugify, ensure_unique_string, generate_entity_id

from homeassistant.components.http import HomeAssistantView
from homeassistant.const import CONF_EMAIL, CONF_NAME, DEGREE
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import track_state_change
from homeassistant.components.device_tracker import SOURCE_TYPE_GPS, ATTR_SOURCE_TYPE
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.core import HomeAssistant, callback


_LOGGER = logging.getLogger(__name__)

# See cover.py for more details.
# Note how both entities for each roller sensor (battry and illuminance) are added at
# the same time to the same list. This way only a single async_add_devices call is
# required.

API_PATH = "/api/torque"
FILE_PATH = "custom_components/mycar2ha/data/"

DEFAULT_NAME = "vehicle"

SENSOR_EMAIL_FIELD = "eml"


ENTITY_ID_FORMAT = "device_tracker." + DOMAIN + ".{}"

#SENSOR_NAME_KEY = r"userFullName(\w+)"
#SENSOR_UNIT_KEY = r"userUnit(\w+)"
#SENSOR_VALUE_KEY = r"k(\w+)"

SENSOR_NAME_KEY = r"userFullName([가-힣a-zA-Z0-9_]+)"
SENSOR_UNIT_KEY = r"userUnit([가-힣a-zA-Z0-9_]+)"
SENSOR_VALUE_KEY = r"k([가-힣a-zA-Z0-9_]+)"

#SENSOR_NAME_KEY = r"userFullName([가-힣a-zA-Z 0-9]+)"
#SENSOR_UNIT_KEY = r"userUnit([가-힣a-zA-Z 0-9]+)"
#SENSOR_VALUE_KEY = r"k([가-힣a-zA-Z 0-9]+)"


NAME_KEY = re.compile(SENSOR_NAME_KEY)
UNIT_KEY = re.compile(SENSOR_UNIT_KEY)
VALUE_KEY = re.compile(SENSOR_VALUE_KEY)

FILE_FORMAT = FILE_PATH + "{}.txt"


def convert_pid(value):
    """Convert pid from hex string to integer."""
    return int(value, 16)


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Add sensors for passed config_entry in HA."""

    hass.data[DOMAIN]["listener"] = []

    car_name = config_entry.data.get(CONF_NAME)
    device = Device(car_name)

    tracker = TorqueTracker(hass, device, car_name)
    trackers = []
    trackers.append(tracker)

    hass.data[DOMAIN]["device_tracker"] = tracker

    if len(trackers) > 0:
        _LOGGER.debug("call async_add_entities")
        async_add_devices(trackers)


class Device:
    """Dummy roller (device for HA) for Hello World example."""

    def __init__(self, name):
        """Init dummy roller."""
        self._id = name
        self.name = name
        self._callbacks = set()
        self._loop = asyncio.get_event_loop()
        # Reports if the roller is moving up or down.
        # >0 is up, <0 is down. This very much just for demonstration.

        # Some static information about this device
        self.firmware_version = VERSION
        self.model = NAME
        self.manufacturer = NAME

    @property
    def device_id(self):
        """Return ID for roller."""
        return self._id

    def register_callback(self, callback):
        """Register callback, called when Roller changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback):
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

    # In a real implementation, this library would call it's call backs when it was
    # notified of any state changeds for the relevant device.
    async def publish_updates(self):
        """Schedule call all registered callbacks."""
        for callback in self._callbacks:
            callback()

    def publish_updates(self):
        """Schedule call all registered callbacks."""
        for callback in self._callbacks:
            callback()

# This base class shows the common properties and methods for a sensor as used in this
# example. See each sensor for further details about properties and methods that
# have been overridden.


class TrackerBase(TrackerEntity):
    """Base representation of a Hello World Sensor."""

    should_poll = False

    def __init__(self, device):
        """Initialize the sensor."""
        self._device = device

    # To link this entity to the cover device, this property must return an
    # identifiers value matching that used in the cover, but no other information such
    # as name. If name is returned, this entity will then also become a device in the
    # HA UI.
    @property
    def device_info(self):
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._device.device_id)},
            # If desired, the name for the device could be different to the entity
            "name": self._device.device_id,
            "sw_version": self._device.firmware_version,
            "model": self._device.model,
            "manufacturer": self._device.manufacturer
        }

    # This property is important to let HA know if this entity is online or not.
    # If an entity is offline (return False), the UI will refelect this.

    @property
    def available(self) -> bool:
        """Return True if roller and hub is available."""
        return True

    async def async_added_to_hass(self):
        """Run when this Entity has been added to HA."""
        # Sensors should also register callbacks to HA when their state changes
        self._device.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        self._device.remove_callback(self.async_write_ha_state)


class TorqueTracker(TrackerBase):

    def __init__(self, hass, device, vehicle):
        """Initialize the sensor."""
        super().__init__(device)

        # _LOGGER.error(
        #    f"make sensor device id : {self._device.device_id}, name : {vehicle}")
        self.entity_id = generate_entity_id(
            ENTITY_ID_FORMAT, "{}".format(vehicle + " Location"), hass=hass)

        #_LOGGER.error(f"entity id - {self.entity_id}")
        self._unique_id = self.entity_id
        self._name = "Location"
        self.hass = hass
        self._latitude = 0
        self._longitude = 0
        self._location_accuracy = 10
        self._source_type = SOURCE_TYPE_GPS

    def set_latitude(self, latitude):
        _LOGGER.debug(f"call set_latitude - {latitude}")
        self._latitude = latitude
        self._device.publish_updates()

    def set_longitude(self, longitude):
        _LOGGER.debug(f"call set_longitude - {longitude}")
        self._longitude = longitude
        self._device.publish_updates()

    # @property
    # def extra_state_attributes(self):
    #   """Return the state attributes."""
    #   return self._extra_state_attributes

    @property
    def source_type(self):
        return self._source_type

    @property
    def state(self) -> str | None:
        """Return the state of the device."""
        if self.location_name is not None:
            return self.location_name

        if self._latitude is not None and self._longitude is not None:
            zone_state = zone.async_active_zone(
                self.hass, self._latitude, self._longitude, self._location_accuracy
            )
            _LOGGER.debug(f"zone state - {zone_state}")
            if zone_state is None:
                state = STATE_NOT_HOME
            elif zone_state.entity_id == zone.ENTITY_ID_HOME:
                state = STATE_HOME
            else:
                state = zone_state.name
            return state

        return None

    @property
    def latitude(self) -> float | None:
        return self._latitude

    @property
    def longitude(self) -> float | None:
        return self._longitude

    @property
    def has_entity_name(self) -> bool:
        return True

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Return the default icon of the sensor."""
        return "mdi:car"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        if self._unique_id is not None:
            return self._unique_id
