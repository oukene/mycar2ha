"""The Detailed Hello World Push integration."""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME
import homeassistant
import time

from .const import DOMAIN

from homeassistant.helpers.device_registry import (
    async_get,
    async_entries_for_config_entry
)

_LOGGER = logging.getLogger(__name__)

# List of platforms to support. There should be a matching .py file for each,
# eg <cover.py> and <sensor.py>
PLATFORMS = ["sensor", "device_tracker"]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Hello World component."""
    # Ensure our name space for storing objects is a known type. A dict is
    # common/preferred as it allows a separate instance of your class for each
    # instance that has been created in the UI.
    hass.data.setdefault(DOMAIN, {})

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hello World from a config entry."""
    # Store an instance of the "connecting" class that does the work of speaking
    # with your actual devices.
    hass.data[DOMAIN][entry.entry_id] = entry.data[CONF_NAME]

    #entity_registry = await homeassistant.helpers.entity_registry.async_get_registry(hass)
    #entities = homeassistant.helpers.entity_registry.async_entries_for_config_entry(
    #    entity_registry, entry.entry_id)

    #device_registry = await async_get_registry(hass)

    #devices = async_entries_for_config_entry(
    #    device_registry, entry.entry_id)


    #for e in entities:
    #    entity_registry.async_remove(e.entity_id)


    #for d in devices:
    #    device_registry.async_remove_device(d.id)


    # This creates each HA object for each platform your device requires.
    # It's done by calling the `async_setup_entry` function in each platform module.
    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details

    for listener in hass.data[DOMAIN]["listener"]:
        listener()

    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(
                    entry, component)
                for component in PLATFORMS
            ]
        )
    )

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
