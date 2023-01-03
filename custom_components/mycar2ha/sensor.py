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
import homeassistant

import math
import json
import asyncio

import os
from homeassistant.helpers.entity import Entity
from pkg_resources import get_provider

import re
from .const import *
from homeassistant.helpers.entity import Iterable, DEVICE_DEFAULT_NAME, slugify, ensure_unique_string, async_generate_entity_id
from homeassistant.helpers.entity_registry import async_get

from homeassistant.components.http import HomeAssistantView
#from homeassistant.components.sensor import ENTITY_ID_FORMAT
from homeassistant.const import CONF_EMAIL, CONF_NAME, DEGREE
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_state_change, track_state_change
#from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.components.sensor import RestoreSensor, SensorEntityDescription
from homeassistant.core import HomeAssistant, callback

import aiohttp
from urllib.parse import parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

_LOGGER = logging.getLogger(__name__)

# See cover.py for more details.
# Note how both entities for each roller sensor (battry and illuminance) are added at
# the same time to the same list. This way only a single async_add_devices call is
# required.


ENTITY_ID_FORMAT = "sensor." + DOMAIN + ".{}"

API_PATH = "/api/torque"
FILE_PATH = "custom_components/mycar2ha/data/"

DEFAULT_NAME = "vehicle"

SENSOR_EMAIL_FIELD = "eml"


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


def isNumber(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Add sensors for passed config_entry in HA."""

    hass.data[DOMAIN]["listener"] = []

    car_name = config_entry.data.get(CONF_NAME)
    email = config_entry.data.get(CONF_EMAIL)
    decimal_places = config_entry.data.get(CONF_DECIMAL_PLACES)
    device = Device(hass, car_name)

    if config_entry.options.get(CONF_EMAIL) != None:
        email = config_entry.options.get(CONF_EMAIL)

    if config_entry.options.get(CONF_DECIMAL_PLACES) != None:
        decimal_places = config_entry.options.get(CONF_DECIMAL_PLACES)

    sensors = []
    if os.path.isdir(FILE_PATH) == False:
        os.mkdir(FILE_PATH)
    filepath = FILE_FORMAT.format(car_name)

    # 파일에 있는 내용으로 센서 생성
    if os.path.isfile(filepath) == False:
        f = open(filepath, "w")
        f.close()

    f = open(filepath, 'r+')
    lines = f.readlines()
    _LOGGER.debug(f"Device Sensors size : {len(device.sensors)}")
    for line in lines:
        if line == "":
            continue
        line = line.replace("\n", "")
        l = line.split('|')
        pid = l[0]
        sensor_name = l[1]
        unit = l[2]

        _LOGGER.debug(f"pid : {pid}, name : {sensor_name} unit : {unit}")

        if pid not in device.sensors:
            s = TorqueSensor(hass, car_name, pid, sensor_name, unit, device)
            _LOGGER.debug(f"add sensor pid : {pid}, sensor : {s}")
            device.sensors[pid] = s
            sensors.append(s)

    f.close()

    _LOGGER.debug(f"sensor size {len(sensors)}")

    _LOGGER.debug(f"decimal places: {decimal_places}")

    # 중복 데이터 제거
    f = open(filepath, "w")
    for pid in device.sensors:
        f.write(str(pid) + "|" +
                str(device.sensors[pid]._name) + "|" + str(device.sensors[pid]._unit) + "\n")
        hass.async_add_job(async_add_devices, [device.sensors[pid]])
    f.close()

    # if len(sensors) > 0:
    #    _LOGGER.debug("call async_add_entities")
    #    async_add_devices(sensors)

    hass.data[DOMAIN]["sensors"] = device.sensors
    hass.data[DOMAIN]["decimal_places"] = decimal_places

    dataView = TorqueReceiveDataView(
        device, email, car_name, filepath, async_add_devices)
    hass.http.register_view(dataView)


class TorqueReceiveDataView(HomeAssistantView):
    """Handle data from Torque requests."""

    url = API_PATH
    name = "api:torque"

    def __init__(self, device, email, car_name, filepath, add_entities):
        """Initialize a Torque view."""
        self.email = email
        self.vehicle = car_name
        self.add_entities = add_entities
        self.device = device
        self.filepath = filepath

    @callback
    def get(self, request):
        """Handle Torque data request."""
        hass = request.app["hass"]
        data = request.query
        sensors = hass.data[DOMAIN]["sensors"]
        decimal_places = hass.data[DOMAIN]["decimal_places"]
        tracker = hass.data[DOMAIN]["device_tracker"]
        tracker_state = hass.states.get(tracker.entity_id)
        """
        for pid in sensors:
            _LOGGER.debug(
                f"update sensor entity id : {sensors[pid].entity_id}, pid : {pid}")
            if sensors[pid]._name == "GPS Longitude":
                if tracker_state != None:
                    tracker.set_longitude(128.58273)
                    #modify_attributes["longitude"] = "128.58273"
                    #hass.states.async_set(
                    #    tracker_entity_id, tracker_state.state, modify_attributes)
                    # hass.data[DOMAIN]["device_tracker"]._device.publish_updates()
                    #hass.data[DOMAIN]["device_tracker"].lanti("128.58273")

            elif sensors[pid]._name == "GPS Latitude":
                if tracker_state != None:
                    tracker.set_latitude(35.85475)
                    #modify_attributes["latitude"] = "35.85475"
                    #hass.states.async_set(
                    #    tracker_entity_id, tracker_state.state, modify_attributes)
                    #hass.data[DOMAIN]["device_tracker"]._device.publish_updates()
                    #hass.data[DOMAIN]["device_tracker"].set_latitude("35.85475")


            sensors[pid].update(
                round(float(str("123.123")), decimal_places) if isNumber("123.123") else "123.123")
            #state = hass.states.get(sensors[pid].entity_id)
            #hass.states.async_set(sensors[pid].entity_id, round(float(
            #    str("123.123")), decimal_places) if isNumber(str("123.123")) else "123.123", state.attributes)
        return
        """

        if self.email is not None and self.email != data[SENSOR_EMAIL_FIELD]:
            return

        names = {}
        units = {}
        _LOGGER.debug(f"data : {data}")
        for key in data:
            is_name = NAME_KEY.match(key)
            is_unit = UNIT_KEY.match(key)
            is_value = VALUE_KEY.match(key)

            if is_name:
                pid = is_name.group(1)
                names[pid] = data[key]
            elif is_unit:
                pid = is_unit.group(1)

                temp_unit = data[key]
                if "\\xC2\\xB0" in temp_unit:
                    temp_unit = temp_unit.replace("\\xC2\\xB0", DEGREE)

                units[pid] = temp_unit
            elif is_value:
                pid = is_value.group(1)
                if pid in sensors:
                    _LOGGER.debug(
                        f"update sensor entity id : {sensors[pid].entity_id}, pid : {pid}")
                    state = hass.states.get(sensors[pid].entity_id)
                    sensors[pid].update(round(float(
                        str(data[key])), decimal_places) if (isNumber(str(data[key])) and sensors[pid]._name != "GPS Longitude" and sensors[pid]._name != "GPS Latitude") else data[key])
                    hass.states.async_set(sensors[pid].entity_id, round(float(
                        str(data[key])), decimal_places) if (isNumber(str(data[key])) and sensors[pid]._name != "GPS Longitude" and sensors[pid]._name != "GPS Latitude") else data[key], state.attributes)

                    if sensors[pid]._name == "GPS Longitude":
                        if tracker_state != None:
                            tracker.set_longitude(float(data[key]))
                    if sensors[pid]._name == "GPS Latitude":
                        if tracker_state != None:
                            tracker.set_latitude(float(data[key]))

                    # sensors[pid].update(
                    #    round(float(str(data[key])), decimal_places) if isNumber(str(data[key])) else data[key])

        for pid, name in names.items():
            if pid not in sensors:
                f = open(self.filepath, "a")
                f.write(str(pid) + "|" + str(name) +
                        "|" + str(units.get(pid)) + "\n")
                f.close()
                sensors[pid] = TorqueSensor(hass,
                                            self.vehicle, pid, name, units.get(
                                                pid), self.device
                                            )
                _LOGGER.debug("create entity callback method")
                hass.async_add_job(self.add_entities, [sensors[pid]])

        return "OK!"


class Device:
    """Dummy roller (device for HA) for Hello World example."""

    def __init__(self, hass, name):
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
        self.sensors: dict[int, TorqueSensor] = {}
        self.hass = hass

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


class SensorBase(RestoreSensor):
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


class TorqueSensor(SensorBase):

    def __init__(self, hass, vehicle, pid, name, unit, device):
        """Initialize the sensor."""
        super().__init__(device)

        _LOGGER.debug(
            f"make sensor device id : {self._device.device_id}, name : {name}")
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, "{}_{}".format(self._device.name, name), hass=hass)

        _LOGGER.debug(f"entity id - {self.entity_id}")
        self._unique_id = self.entity_id
        self._name = name
        self._unit = unit
        self._value = None
        self._pid = pid

        # self.async_get_last_state()

    async def async_added_to_hass(self):
        old_state = await self.async_get_last_sensor_data()
        self._value = old_state.native_value
        _LOGGER.debug(f"old_state.state - {old_state.native_value}")

        self._device.register_callback(self.async_write_ha_state)

    @property
    def has_entity_name(self) -> bool:
        return True

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    # @property
    # def state(self):
    #    return self._state

    @property
    def native_value(self):
        return self._value

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def icon(self):
        """Return the default icon of the sensor."""
        return "mdi:car"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        if self._unique_id is not None:
            return self._unique_id

    def update(self, value):
        """Receive an update."""
        self._value = value
        _LOGGER.debug("call update")
        self._device.publish_updates()
