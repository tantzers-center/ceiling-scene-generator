"""Async task runner: the piece that actually pushes frames to the lights.

Design goals
------------
* **Wi-Fi friendly**: one service call per *changed group of lights* every
  ``update_interval`` seconds, with the hardware ``transition`` set to roughly
  the same duration, so the fixtures interpolate smoothly between frames instead
  of receiving a packet storm.
* **Restart safe**: the runner owns a single background task; starting again
  cancels the previous one first, and ``async_stop`` is always safe to call.
* **Testable**: all the maths lives in :mod:`engine`; this module only decides
  *when* and *to whom* to send.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .engine import (
    DEFAULT_MIN_BRIGHTNESS_DELTA,
    DEFAULT_MIN_COLOR_DELTA,
    DEFAULT_PALETTE,
    DEFAULT_TRANSITION,
    DEFAULT_UPDATE_INTERVAL,
    EFFECTS,
    compute_frame,
    frame_deltas,
    index_frame,
    resolve_lights,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class SceneConfig:
    """Everything the runner needs for one continuous effect."""

    name: str = "Ceiling"
    scene: dict[str, Any] = field(default_factory=dict)
    effect: str = EFFECTS[0]
    params: dict[str, Any] = field(default_factory=dict)
    palette: Any = field(default_factory=lambda: DEFAULT_PALETTE)
    update_interval: float = DEFAULT_UPDATE_INTERVAL
    transition: float = DEFAULT_TRANSITION
    min_color_delta: int = DEFAULT_MIN_COLOR_DELTA
    min_brightness_delta: int = DEFAULT_MIN_BRIGHTNESS_DELTA
    restore_on_stop: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SceneConfig":
        data = dict(data or {})
        config = cls(
            name=str(data.get("name") or "Ceiling"),
            scene=dict(data.get("scene") or {}),
            effect=data.get("effect") if data.get("effect") in EFFECTS else EFFECTS[0],
            params=dict(data.get("params") or {}),
            palette=data.get("palette") or DEFAULT_PALETTE,
            update_interval=float(data.get("update_interval") or DEFAULT_UPDATE_INTERVAL),
            transition=float(data.get("transition") or DEFAULT_TRANSITION),
            min_color_delta=int(data.get("min_color_delta") or DEFAULT_MIN_COLOR_DELTA),
            min_brightness_delta=int(data.get("min_brightness_delta") or DEFAULT_MIN_BRIGHTNESS_DELTA),
            restore_on_stop=bool(data.get("restore_on_stop") or False),
        )
        if not config.scene.get("name"):
            config.scene["name"] = config.name
        return config

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "scene": self.scene,
            "effect": self.effect,
            "params": self.params,
            "palette": self.palette,
            "update_interval": self.update_interval,
            "transition": self.transition,
            "min_color_delta": self.min_color_delta,
            "min_brightness_delta": self.min_brightness_delta,
            "restore_on_stop": self.restore_on_stop,
        }


class SceneRunner:
    """Owns the background task that walks the effect over time."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._task: asyncio.Task[None] | None = None
        self._config = SceneConfig()
        self._last_sent: dict[str, dict[str, Any]] = {}
        self._restore: dict[str, dict[str, Any] | None] = {}
        self._listeners: list[Callable[[], None]] = []
        self._started_at: float | None = None
        self.frames = 0
        self.calls = 0
        self.last_error: str | None = None

    # ------------------------------------------------------------ book-keeping

    @property
    def active(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def config(self) -> SceneConfig:
        return self._config

    @property
    def light_count(self) -> int:
        return len(resolve_lights(self._config.scene))

    @property
    def elapsed(self) -> float:
        return 0.0 if self._started_at is None else round(time.monotonic() - self._started_at, 1)

    def snapshot(self) -> dict[str, Any]:
        """Attributes exposed by the switch entity and returned by services."""
        return {
            "active": self.active,
            "name": self._config.name,
            "effect": self._config.effect,
            "lights": self.light_count,
            "update_interval": self._config.update_interval,
            "transition": self._config.transition,
            "frames": self.frames,
            "service_calls": self.calls,
            "elapsed": self.elapsed,
            "last_error": self.last_error,
        }

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def remove() -> None:
            with suppress(ValueError):
                self._listeners.remove(listener)

        return remove

    def notify(self) -> None:
        """Public poke so entities can refresh after external store changes."""
        self._notify()

    def _notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # pragma: no cover - listener must never break the loop
                _LOGGER.exception("Ceiling Scene Generator listener failed")

    # -------------------------------------------------------------- lifecycle

    async def async_start(self, config: SceneConfig) -> None:
        """(Re)start the generator with `config`."""
        await self.async_stop()
        self._config = config
        self._last_sent = {}
        self._restore = self._capture_states()
        self.frames = 0
        self.calls = 0
        self.last_error = None
        self._started_at = time.monotonic()

        missing = [
            light["entity_id"]
            for light in resolve_lights(config.scene)
            if self.hass.states.get(light["entity_id"]) is None
        ]
        if missing:
            _LOGGER.warning(
                "Ceiling Scene Generator: %s light(s) not found in Home Assistant: %s",
                len(missing),
                ", ".join(missing[:10]),
            )

        self._task = self.hass.async_create_background_task(
            self._async_run(), f"{DOMAIN} runner {config.name}"
        )
        self._notify()
        _LOGGER.info(
            "Ceiling Scene Generator started: %s · %s · %s lights · %.2fs interval",
            config.name,
            config.effect,
            self.light_count,
            config.update_interval,
        )

    async def async_stop(self, restore_state: bool = False) -> None:
        """Stop the generator, optionally putting the lights back as they were."""
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if restore_state:
            await self._async_restore()
        self._started_at = None
        self._notify()

    async def async_resume_last(self, store) -> bool:
        """Restart the last run configuration, if one was stored."""
        last = store.last_run
        if not last or not resolve_lights(last.get("scene") or {}):
            return False
        await self.async_start(SceneConfig.from_dict(last))
        return True

    # ------------------------------------------------------------------- loop

    async def _async_run(self) -> None:
        try:
            while True:
                await self._async_push_frame()
                await asyncio.sleep(max(0.2, self._config.update_interval))
        except asyncio.CancelledError:
            raise
        except Exception as err:  # keep HA usable, surface the failure on the switch
            self.last_error = str(err)
            _LOGGER.exception("Ceiling Scene Generator runner stopped: %s", err)
        finally:
            self._notify()

    async def _async_push_frame(self) -> None:
        elapsed = self.elapsed
        frame = compute_frame(
            self._config.scene,
            self._config.effect,
            self._config.params,
            self._config.palette,
            elapsed,
        )
        self.frames += 1
        if not frame:
            return
        changed = frame_deltas(
            self._last_sent,
            frame,
            self._config.min_color_delta,
            self._config.min_brightness_delta,
        )
        if not changed:
            return

        groups: dict[tuple[int, int, int, int], list[str]] = {}
        for entry in changed:
            key = (entry["rgb"][0], entry["rgb"][1], entry["rgb"][2], int(entry["brightness_pct"]))
            groups.setdefault(key, []).append(entry["entity_id"])

        for key, entity_ids in groups.items():
            await self.hass.services.async_call(
                "light",
                "turn_on",
                {
                    "rgb_color": [key[0], key[1], key[2]],
                    "brightness_pct": key[3],
                    "transition": round(self._config.transition, 2),
                },
                target={"entity_id": entity_ids},
                blocking=False,
            )
        self.calls += len(groups)
        self._last_sent.update(index_frame(changed))

    # -------------------------------------------------------------- restoring

    def _capture_states(self) -> dict[str, dict[str, Any] | None]:
        captured: dict[str, dict[str, Any] | None] = {}
        for light in resolve_lights(self._config.scene):
            state = self.hass.states.get(light["entity_id"])
            if state is None or state.state == "off":
                captured[light["entity_id"]] = None
            else:
                captured[light["entity_id"]] = {
                    "brightness": state.attributes.get("brightness"),
                    "rgb_color": state.attributes.get("rgb_color"),
                    "hs_color": state.attributes.get("hs_color"),
                    "color_temp_kelvin": state.attributes.get("color_temp_kelvin"),
                }
        return captured

    async def _async_restore(self) -> None:
        for entity_id, saved in self._restore.items():
            if saved is None:
                await self.hass.services.async_call(
                    "light", "turn_off", {}, target={"entity_id": entity_id}, blocking=False
                )
                continue
            data: dict[str, Any] = {}
            if saved.get("rgb_color"):
                data["rgb_color"] = saved["rgb_color"]
            elif saved.get("color_temp_kelvin"):
                data["color_temp_kelvin"] = saved["color_temp_kelvin"]
            if saved.get("brightness"):
                data["brightness"] = saved["brightness"]
            await self.hass.services.async_call(
                "light",
                "turn_on",
                data,
                target={"entity_id": entity_id},
                blocking=False,
            )
        self._restore = {}
