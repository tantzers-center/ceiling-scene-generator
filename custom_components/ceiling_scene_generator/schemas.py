"""Voluptuous schemas for the Ceiling Scene Generator services.

Kept in their own module so the other modules stay importable without
``voluptuous``/``homeassistant`` (useful for the pure engine test suite).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
    DEFAULT_FRAMES,
    DEFAULT_MIN_BRIGHTNESS_DELTA,
    DEFAULT_MIN_COLOR_DELTA,
    DEFAULT_TRANSITION,
    DEFAULT_UPDATE_INTERVAL,
    EFFECTS,
    GRID_MODES,
    PALETTES,
    PARAM_SPECS,
)

PALETTE_NAMES = sorted(PALETTES)


def cv_palette(value: Any) -> Any:
    """Palette as a preset id, a list of hex strings or a list of RGB lists."""
    if isinstance(value, str):
        if value.strip().lower() not in PALETTES:
            raise vol.Invalid(f"unknown palette '{value}', expected one of {PALETTE_NAMES}")
        return value
    if isinstance(value, (list, tuple)):
        if not value:
            raise vol.Invalid("palette must contain at least one colour")
        for item in value:
            if isinstance(item, str):
                text = item.strip().lstrip("#")
                if len(text) not in (3, 6):
                    raise vol.Invalid(f"'{item}' is not a #RGB or #RRGGBB colour")
                try:
                    int(text, 16)
                except ValueError as err:
                    raise vol.Invalid(f"'{item}' is not a valid hex colour") from err
            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                if not all(isinstance(channel, (int, float)) for channel in item[:3]):
                    raise vol.Invalid("RGB colour stops must be numeric triples")
            else:
                raise vol.Invalid("palette stops must be hex strings or RGB triples")
        return list(value)
    raise vol.Invalid("palette must be a preset name or a list of colours")


def _param_range(key: str) -> Any:
    spec = PARAM_SPECS[key]
    return vol.All(vol.Coerce(float), vol.Range(min=spec["min"], max=spec["max"]))


PARAMS_SCHEMA = vol.Schema(
    {vol.Optional(key): _param_range(key) for key in PARAM_SPECS},
    extra=vol.PREVENT_EXTRA,
)

LIGHT_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("x", default=0): vol.Coerce(float),
        vol.Optional("y", default=0): vol.Coerce(float),
        vol.Optional("row", default=0): vol.Coerce(int),
        vol.Optional("col", default=0): vol.Coerce(int),
        vol.Optional("name"): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

ROOM_SCHEMA = vol.Schema(
    {
        vol.Optional("width", default=6.0): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=100)),
        vol.Optional("height", default=4.5): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=100)),
        vol.Optional("padding", default=0.5): vol.All(vol.Coerce(float), vol.Range(min=0, max=50)),
    },
    extra=vol.ALLOW_EXTRA,
)

GRID_SCHEMA = vol.Schema(
    {
        vol.Optional("mode", default="grid"): vol.In(GRID_MODES),
        vol.Optional("rows", default=3): vol.All(vol.Coerce(int), vol.Range(min=1, max=32)),
        vol.Optional("cols", default=4): vol.All(vol.Coerce(int), vol.Range(min=1, max=32)),
    },
    extra=vol.ALLOW_EXTRA,
)

SCENE_SCHEMA = vol.Schema(
    {
        vol.Optional("name", default="Ceiling"): cv.string,
        vol.Optional("room"): ROOM_SCHEMA,
        vol.Optional("grid"): GRID_SCHEMA,
        vol.Optional("lights", default=list): vol.All(cv.ensure_list, [LIGHT_SCHEMA], vol.Length(min=1)),
    },
    extra=vol.ALLOW_EXTRA,
)

START_SCHEMA = vol.Schema(
    {
        vol.Optional("name"): cv.string,
        vol.Optional("scene"): SCENE_SCHEMA,
        vol.Optional("effect"): vol.In(EFFECTS),
        vol.Optional("params"): PARAMS_SCHEMA,
        vol.Optional("palette"): cv_palette,
        vol.Optional("update_interval", default=DEFAULT_UPDATE_INTERVAL): vol.All(
            vol.Coerce(float), vol.Range(min=0.2, max=60)
        ),
        vol.Optional("transition", default=DEFAULT_TRANSITION): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=60)
        ),
        vol.Optional("min_color_delta", default=DEFAULT_MIN_COLOR_DELTA): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        ),
        vol.Optional("min_brightness_delta", default=DEFAULT_MIN_BRIGHTNESS_DELTA): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=100)
        ),
        vol.Optional("restore_on_stop", default=False): cv.boolean,
        vol.Optional("save", default=False): cv.boolean,
    },
    extra=vol.PREVENT_EXTRA,
)

STOP_SCHEMA = vol.Schema(
    {
        vol.Optional("restore_state", default=False): cv.boolean,
        vol.Optional("clear_last_run", default=False): cv.boolean,
    },
    extra=vol.PREVENT_EXTRA,
)

SAVE_AS_SCRIPT_SCHEMA = vol.Schema(
    {
        vol.Optional("name"): cv.string,
        vol.Optional("scene"): SCENE_SCHEMA,
        vol.Optional("effect"): vol.In(EFFECTS),
        vol.Optional("params"): PARAMS_SCHEMA,
        vol.Optional("palette"): cv_palette,
        vol.Optional("frames", default=DEFAULT_FRAMES): vol.All(vol.Coerce(int), vol.Range(min=2, max=120)),
        vol.Optional("transition"): vol.All(vol.Coerce(float), vol.Range(min=0, max=60)),
        vol.Optional("script_name"): cv.string,
        vol.Optional("alias"): cv.string,
        vol.Optional("write_file", default=False): cv.boolean,
        vol.Optional("filename"): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
)

SAVE_SCENE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("scene"): SCENE_SCHEMA,
        vol.Optional("effect"): vol.In(EFFECTS),
        vol.Optional("params"): PARAMS_SCHEMA,
        vol.Optional("palette"): cv_palette,
        vol.Optional("update_interval"): vol.All(vol.Coerce(float), vol.Range(min=0.2, max=60)),
        vol.Optional("transition"): vol.All(vol.Coerce(float), vol.Range(min=0, max=60)),
    },
    extra=vol.PREVENT_EXTRA,
)

DELETE_SCENE_SCHEMA = vol.Schema(
    {vol.Required("name"): cv.string},
    extra=vol.PREVENT_EXTRA,
)

LIST_SCENES_SCHEMA = vol.Schema(
    {},
    extra=vol.PREVENT_EXTRA,
)
