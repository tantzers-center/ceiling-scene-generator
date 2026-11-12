"""Constants for the Ceiling Scene Generator integration.

Home Assistant facing constants live here; every mathematical definition lives in
``engine.py`` (which has no Home Assistant imports and is mirrored by the JS
engine in ``www/ceiling-scene-card.js``).
"""

from __future__ import annotations

from .engine import (  # noqa: F401  (re-exported for convenience)
    DEFAULT_FRAMES,
    DEFAULT_MIN_BRIGHTNESS_DELTA,
    DEFAULT_MIN_COLOR_DELTA,
    DEFAULT_PALETTE,
    DEFAULT_PARAMS,
    DEFAULT_TRANSITION,
    DEFAULT_UPDATE_INTERVAL,
    EFFECT_EQUATIONS,
    EFFECT_LABELS,
    EFFECT_PARAMS,
    EFFECTS,
    GRID_MODES,
    PALETTES,
    PARAM_SPECS,
    VERSION,
)

DOMAIN = "ceiling_scene_generator"
NAME = "Ceiling Scene Generator"
MANUFACTURER = "Ceiling Scene Generator"

# Storage
STORAGE_KEY = f"{DOMAIN}.store"
STORAGE_VERSION = 1
STORAGE_MINOR_VERSION = 1
SAVED_SCENES = "scenes"
SAVED_LAST_RUN = "last_run"

# Services
SERVICE_START = "start"
SERVICE_STOP = "stop"
SERVICE_SAVE_AS_SCRIPT = "save_as_script"
SERVICE_SAVE_SCENE = "save_scene"
SERVICE_DELETE_SCENE = "delete_scene"
SERVICE_LIST_SCENES = "list_scenes"

# Config entry options
CONF_UPDATE_INTERVAL = "update_interval"
CONF_TRANSITION = "transition"
CONF_AUTO_RESUME = "auto_resume"
DEFAULT_AUTO_RESUME = False

# Frontend assets: served straight out of the custom component directory
# (``custom_components/<domain>/`` is mounted at ``/<domain>/`` by HA).
CARD_FILENAME = "ceiling-scene-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"
WWW_DIRNAME = "www"

ATTR_EFFECT = "effect"
ATTR_SCENE = "scene"
ATTR_PARAMS = "params"
ATTR_PALETTE = "palette"
ATTR_NAME = "name"

SWITCH_UNIQUE_ID = f"{DOMAIN}_generator"
SWITCH_DEFAULT_NAME = "Ceiling Scene"
