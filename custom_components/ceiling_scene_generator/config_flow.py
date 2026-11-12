"""Config flow: UI setup + options for the Ceiling Scene Generator."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_AUTO_RESUME,
    CONF_TRANSITION,
    CONF_UPDATE_INTERVAL,
    DEFAULT_AUTO_RESUME,
    DEFAULT_TRANSITION,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    NAME,
)


def _options_schema(current: dict[str, Any] | None = None) -> vol.Schema:
    current = current or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_UPDATE_INTERVAL,
                default=current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): vol.All(vol.Coerce(float), vol.Range(min=0.2, max=60)),
            vol.Optional(
                CONF_TRANSITION,
                default=current.get(CONF_TRANSITION, DEFAULT_TRANSITION),
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=60)),
            vol.Optional(
                CONF_AUTO_RESUME,
                default=current.get(CONF_AUTO_RESUME, DEFAULT_AUTO_RESUME),
            ): bool,
        }
    )


class CeilingSceneGeneratorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the (single instance) configuration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(
                title=NAME,
                data={},
                options={**user_input},
            )
        return self.async_show_form(step_id="user", data_schema=_options_schema())

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CeilingSceneGeneratorOptionsFlow()


class CeilingSceneGeneratorOptionsFlow(OptionsFlow):
    """Edit the default timing and start-up behaviour."""

    def _entry(self) -> ConfigEntry | None:
        # Recent cores set `config_entry` themselves as a read-only property;
        # assigning it raises AttributeError, so we only ever read it (with a
        # fallback for very old cores that pass nothing).
        entry = getattr(self, "config_entry", None)
        if entry is not None:
            return entry
        entries = getattr(self.hass.config_entries, "async_entries", None)
        if callable(entries):
            found = entries(DOMAIN)
            if found:
                return found[0]
        return None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        entry = self._entry()
        current = dict(entry.options) if entry is not None else {}
        if user_input is not None:
            return self.async_create_entry(title="", data={**user_input})
        return self.async_show_form(step_id="init", data_schema=_options_schema(current))
