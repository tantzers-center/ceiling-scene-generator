"""Switch platform: a single on/off handle for the running generator.

The switch is on while the async runner is pushing frames. It carries the
``ceiling_scene_generator`` marker in ``extra_state_attributes``, which is how
the Lovelace card finds it (by attribute, not by entity id, so renaming the
entity never breaks the card) and why the entity also has a fresh ``scenes``
list after scenes are saved or deleted.

``has_entity_name`` is on and the entity has no name of its own, so the entity
id is derived from the device name: ``switch.ceiling_scene_generator``.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MANUFACTURER, NAME, SWITCH_UNIQUE_ID
from .runner import SceneRunner, SceneConfig
from .storage import SceneStore


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CeilingSceneSwitch(data["runner"], data["store"])])


class CeilingSceneSwitch(SwitchEntity):
    """On/off handle for the ceiling scene generator."""

    _attr_should_poll = False
    _attr_icon = "mdi:ceiling-light-multiple"
    _attr_has_entity_name = True
    _attr_name = None  # name comes from the device: "Ceiling Scene Generator"
    _attr_unique_id = SWITCH_UNIQUE_ID

    def __init__(self, runner: SceneRunner, store: SceneStore) -> None:
        self._runner = runner
        self._store = store

    # ------------------------------------------------------------ properties

    @property
    def is_on(self) -> bool:
        return self._runner.active

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, SWITCH_UNIQUE_ID)},
            name=NAME,
            manufacturer=MANUFACTURER,
            model="Spatial ceiling effect generator",
            sw_version=self._runner.config.effect,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes: dict[str, Any] = {"ceiling_scene_generator": True}
        attributes.update(self._runner.snapshot())
        attributes["scenes"] = sorted(self._store.scenes)
        return attributes

    # ---------------------------------------------------------------- control

    async def async_turn_on(self, **kwargs: Any) -> None:
        record = self._store.last_run
        if not record:
            raise HomeAssistantError(
                "No ceiling scene to start yet. Call ceiling_scene_generator.start "
                "(or use the Lovelace card) first."
            )
        await self._runner.async_start(SceneConfig.from_dict(record))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._runner.async_stop(self._runner.config.restore_on_stop)

    # -------------------------------------------------------------- lifecycle

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._runner.add_listener(self._handle_runner_update))

    @callback
    def _handle_runner_update(self) -> None:
        self.async_write_ha_state()
