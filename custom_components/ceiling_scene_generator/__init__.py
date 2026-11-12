"""The Ceiling Scene Generator integration.

Turns an array of recessed ceiling lights into an orchestrated spatial canvas:
room + fixture layout, ten mathematical effects, a palette, a rate limited async
task runner, HA Storage persistence and a static scripts.yaml compiler.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CARD_FILENAME,
    CARD_URL,
    CONF_AUTO_RESUME,
    CONF_TRANSITION,
    CONF_UPDATE_INTERVAL,
    DEFAULT_PALETTE,
    DEFAULT_TRANSITION,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    EFFECTS,
    NAME,
    SERVICE_DELETE_SCENE,
    SERVICE_LIST_SCENES,
    SERVICE_SAVE_AS_SCRIPT,
    SERVICE_SAVE_SCENE,
    SERVICE_START,
    SERVICE_STOP,
    WWW_DIRNAME,
)
from .runner import SceneConfig, SceneRunner
from .schemas import (
    DELETE_SCENE_SCHEMA,
    LIST_SCENES_SCHEMA,
    SAVE_AS_SCRIPT_SCHEMA,
    SAVE_SCENE_SCHEMA,
    START_SCHEMA,
    STOP_SCHEMA,
)
from .script_compiler import (
    compile_card_yaml,
    compile_script,
    compile_service_call,
    palette_hex_list,
)
from .storage import SceneStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH]


# --------------------------------------------------------------------------- #
# Setup / teardown
# --------------------------------------------------------------------------- #

async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Integration is configured through the UI only."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ceiling Scene Generator from a config entry."""
    store = SceneStore(hass)
    await store.async_load()
    runner = SceneRunner(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"store": store, "runner": runner}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_register_frontend(hass)
    _async_register_services(hass)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_handle_stop_event(hass))
    )

    if entry.options.get(CONF_AUTO_RESUME, False):
        try:
            if await runner.async_resume_last(store):
                _LOGGER.info("Ceiling Scene Generator auto-resumed the last scene")
        except Exception as err:  # never block startup on a bad stored scene
            _LOGGER.warning("Could not auto-resume the last ceiling scene: %s", err)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data:
        await data["runner"].async_stop()
    if not hass.data.get(DOMAIN):
        _async_remove_services(hass)
    return True


def _async_handle_stop_event(hass: HomeAssistant):
    async def _handle(event) -> None:
        data = _data(hass)
        if data:
            await data["runner"].async_stop()

    return _handle


# --------------------------------------------------------------------------- #
# Frontend (Lovelace card)
# --------------------------------------------------------------------------- #

async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve and register ``www/ceiling-scene-card.js``."""
    card_path = Path(__file__).parent / WWW_DIRNAME / CARD_FILENAME
    if not card_path.is_file():
        _LOGGER.warning("Ceiling Scene Generator card not found at %s", card_path)
        return

    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(card_path), False)]
        )
    except ImportError:  # pragma: no cover - very old core
        hass.http.register_static_path(CARD_URL, str(card_path), False)
    except (RuntimeError, ValueError) as err:
        _LOGGER.debug("Static path %s already registered: %s", CARD_URL, err)

    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, CARD_URL)
        _LOGGER.debug("Registered Lovelace resource %s", CARD_URL)
    except Exception as err:  # pragma: no cover - frontend may be unavailable
        _LOGGER.warning(
            "Could not auto-register the Lovelace resource, add it manually as %s (%s)",
            CARD_URL,
            err,
        )


# --------------------------------------------------------------------------- #
# Services
# --------------------------------------------------------------------------- #

def _data(hass: HomeAssistant) -> dict[str, Any] | None:
    """Return the store/runner bundle of the (single) configured entry."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if isinstance(entry_data, dict) and "runner" in entry_data:
            return entry_data
    return None


def _resolve_scene(payload: dict[str, Any], saved: dict[str, Any] | None) -> dict[str, Any]:
    scene = payload.get("scene") or (saved or {}).get("scene")
    if not scene or not scene.get("lights"):
        raise HomeAssistantError(
            "Ceiling Scene Generator: no scene given. Pass `scene:` with your lights, "
            "or `name:` of a scene saved with ceiling_scene_generator.save_scene."
        )
    return dict(scene)


def _build_config(payload: dict[str, Any], saved: dict[str, Any] | None, scene: dict[str, Any]) -> SceneConfig:
    def pick(key: str, default: Any) -> Any:
        for source in (payload, saved or {}, scene):
            value = source.get(key) if isinstance(source, dict) else None
            if value not in (None, "", []):
                return value
        return default

    return SceneConfig.from_dict(
        {
            "name": pick("name", scene.get("name") or "Ceiling"),
            "scene": scene,
            "effect": pick("effect", EFFECTS[0]),
            "params": pick("params", {}),
            "palette": pick("palette", DEFAULT_PALETTE),
            "update_interval": pick("update_interval", DEFAULT_UPDATE_INTERVAL),
            "transition": pick("transition", DEFAULT_TRANSITION),
            "min_color_delta": payload.get("min_color_delta"),
            "min_brightness_delta": payload.get("min_brightness_delta"),
            "restore_on_stop": payload.get("restore_on_stop", False),
        }
    )


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_START):
        return

    async def handle_start(call: ServiceCall) -> dict[str, Any]:
        data = _data(hass)
        if data is None:
            raise HomeAssistantError("Ceiling Scene Generator is not configured yet")
        payload = dict(call.data)
        saved = data["store"].get(payload.get("name") or "")
        scene = _resolve_scene(payload, saved)
        config = _build_config(payload, saved, scene)
        if payload.get("save"):
            await data["store"].async_save_scene(config.name, config.as_dict())
        await data["runner"].async_start(config)
        return data["runner"].snapshot()

    async def handle_stop(call: ServiceCall) -> dict[str, Any]:
        data = _data(hass)
        if data is None:
            raise HomeAssistantError("Ceiling Scene Generator is not configured yet")
        await data["runner"].async_stop(bool(call.data.get("restore_state", False)))
        if call.data.get("clear_last_run"):
            await data["store"].async_clear_last_run()
        return data["runner"].snapshot()

    async def handle_save_as_script(call: ServiceCall) -> dict[str, Any]:
        data = _data(hass)
        if data is None:
            raise HomeAssistantError("Ceiling Scene Generator is not configured yet")
        payload = dict(call.data)
        saved = data["store"].get(payload.get("name") or "")
        scene = _resolve_scene(payload, saved)
        config = _build_config(payload, saved, scene)
        frames = int(payload.get("frames") or 8)
        transition = payload.get("transition")
        result = compile_script(
            scene=scene,
            effect=config.effect,
            params=config.params,
            palette=config.palette,
            frames=frames,
            script_name=payload.get("script_name"),
            alias=payload.get("alias"),
            transition=transition,
        )
        result["service_call_yaml"] = compile_service_call(
            scene=scene,
            effect=config.effect,
            params=config.params,
            palette=config.palette,
            update_interval=config.update_interval,
            transition=config.transition,
        )
        result["card_yaml"] = compile_card_yaml(
            scene=scene, effect=config.effect, palette=config.palette, title=f"Ceiling Scene - {config.name}"
        )
        result["palette"] = palette_hex_list(config.palette)
        result["effect"] = config.effect
        if payload.get("write_file"):
            filename = payload.get("filename") or f"{result['script_id']}.yaml"
            path = Path(hass.config.path("ceiling_scenes")) / filename
            await hass.async_add_executor_job(_write_script, path, result["yaml"])
            result["path"] = str(path)
        return result

    async def handle_save_scene(call: ServiceCall) -> dict[str, Any]:
        data = _data(hass)
        if data is None:
            raise HomeAssistantError("Ceiling Scene Generator is not configured yet")
        payload = dict(call.data)
        name = str(payload["name"]).strip() or "Ceiling"
        saved = data["store"].get(name)
        scene = payload.get("scene") or (saved or {}).get("scene")
        if not scene or not scene.get("lights"):
            raise HomeAssistantError(
                "Ceiling Scene Generator: a scene needs at least one light; pass `scene:` to save a layout."
            )
        config = _build_config({"name": name}, saved, dict(scene))
        record = config.as_dict()
        key = await data["store"].async_save_scene(name, record)
        return {"name": key, "saved": True, "count": len(data["store"].scenes)}

    async def handle_delete_scene(call: ServiceCall) -> dict[str, Any]:
        data = _data(hass)
        if data is None:
            raise HomeAssistantError("Ceiling Scene Generator is not configured yet")
        name = str(call.data["name"])
        deleted = await data["store"].async_delete_scene(name)
        return {"name": name, "deleted": deleted, "count": len(data["store"].scenes)}

    async def handle_list_scenes(call: ServiceCall) -> dict[str, Any]:
        data = _data(hass)
        if data is None:
            raise HomeAssistantError("Ceiling Scene Generator is not configured yet")
        scenes = data["store"].scenes
        return {
            "scenes": scenes,
            "count": len(scenes),
            "running": data["runner"].snapshot(),
            "effects": list(EFFECTS),
        }

    hass.services.async_register(
        DOMAIN, SERVICE_START, handle_start, schema=START_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_STOP, handle_stop, schema=STOP_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_SAVE_AS_SCRIPT, handle_save_as_script, schema=SAVE_AS_SCRIPT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SAVE_SCENE, handle_save_scene, schema=SAVE_SCENE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_SCENE, handle_delete_scene, schema=DELETE_SCENE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LIST_SCENES, handle_list_scenes, schema=LIST_SCENES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


def _async_remove_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_START,
        SERVICE_STOP,
        SERVICE_SAVE_AS_SCRIPT,
        SERVICE_SAVE_SCENE,
        SERVICE_DELETE_SCENE,
        SERVICE_LIST_SCENES,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)


def _write_script(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _default_options() -> dict[str, Any]:
    return {
        CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
        CONF_TRANSITION: DEFAULT_TRANSITION,
        CONF_AUTO_RESUME: False,
    }


__all__ = [
    "DOMAIN",
    "NAME",
    "PLATFORMS",
    "async_setup",
    "async_setup_entry",
    "async_unload_entry",
    "_default_options",
]
