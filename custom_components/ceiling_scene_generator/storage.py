"""Home Assistant Storage persistence for ceiling scenes.

Scenes (room + light layout + effect + parameters + palette) and the last run
configuration are kept in ``.storage/ceiling_scene_generator.store`` so the
generator survives a Home Assistant restart and can auto-resume.
"""

from __future__ import annotations

from typing import Any, Mapping

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    SAVED_LAST_RUN,
    SAVED_SCENES,
    STORAGE_KEY,
    STORAGE_MINOR_VERSION,
    STORAGE_VERSION,
)


class SceneStore:
    """Thin wrapper around ``homeassistant.helpers.storage.Store``."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            minor_version=STORAGE_MINOR_VERSION,
        )
        self._scenes: dict[str, dict[str, Any]] = {}
        self._last_run: dict[str, Any] | None = None

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        scenes = data.get(SAVED_SCENES) or {}
        self._scenes = {str(key): dict(value) for key, value in scenes.items() if isinstance(value, Mapping)}
        last_run = data.get(SAVED_LAST_RUN)
        self._last_run = dict(last_run) if isinstance(last_run, Mapping) else None

    def _snapshot(self) -> dict[str, Any]:
        return {SAVED_SCENES: self._scenes, SAVED_LAST_RUN: self._last_run}

    async def _async_write(self) -> None:
        await self._store.async_save(self._snapshot())

    # ---------------------------------------------------------------- scenes

    @property
    def scenes(self) -> dict[str, dict[str, Any]]:
        return dict(self._scenes)

    def get(self, name: str) -> dict[str, Any] | None:
        if not name:
            return None
        record = self._scenes.get(name)
        if record is not None:
            return dict(record)
        lowered = str(name).strip().lower()
        for key, value in self._scenes.items():
            if key.strip().lower() == lowered:
                return dict(value)
        return None

    async def async_save_scene(self, name: str, record: Mapping[str, Any]) -> str:
        key = str(name).strip() or "Ceiling"
        self._scenes[key] = dict(record)
        await self._async_write()
        return key

    async def async_delete_scene(self, name: str) -> bool:
        key = str(name).strip()
        removed = self._scenes.pop(key, None)
        if removed is None:
            for existing in list(self._scenes):
                if existing.strip().lower() == key.lower():
                    removed = self._scenes.pop(existing)
                    break
        if removed is None:
            return False
        await self._async_write()
        return True

    # -------------------------------------------------------------- last run

    @property
    def last_run(self) -> dict[str, Any] | None:
        return dict(self._last_run) if self._last_run else None

    async def async_set_last_run(self, record: Mapping[str, Any]) -> None:
        self._last_run = dict(record)
        await self._async_write()

    async def async_clear_last_run(self) -> None:
        if self._last_run is None:
            return
        self._last_run = None
        await self._async_write()
