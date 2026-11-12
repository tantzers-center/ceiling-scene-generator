"""Compile a Ceiling Scene into native Home Assistant YAML.

Two outputs are produced for the user:

``compile_script``
    A fully static ``scripts.yaml`` entry: the wave is sampled into N frames per
    cycle and replayed with ``light.turn_on`` + ``transition``, so the lights keep
    animating even if the integration's background task is not running (perfect
    for a dashboard button, an automation, or a wall tablet).

``compile_service_call``
    The YAML for the *live* generator (``ceiling_scene_generator.start``), i.e.
    the continuous, rate limited version driven by the integration.

The YAML is emitted by a tiny hand written writer: the output is deterministic,
stable across runs and needs no third party dependency, which keeps the
integration's test suite runnable on a bare Python install.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from .engine import (
    DEFAULT_FRAMES,
    DEFAULT_TRANSITION,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_PARAMS,
    EFFECT_EQUATIONS,
    EFFECT_LABELS,
    EFFECTS,
    PALETTES,
    cycle_period,
    compute_frame,
    normalize_palette,
    resolve_lights,
    resolve_params,
    room_bounds,
)

__all__ = [
    "slugify",
    "group_frame",
    "build_frame_plan",
    "compile_script",
    "compile_service_call",
    "compile_card_yaml",
]


# --------------------------------------------------------------------------- #
# Small YAML writer
# --------------------------------------------------------------------------- #

_SIMPLE_SCALAR = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-./:%]*$")
_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "none", "~"}


def yaml_scalar(value: Any) -> str:
    """Render a scalar in a way PyYAML would read back identically."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and float(value).is_integer():
            return str(int(value))
        return repr(value) if isinstance(value, float) else str(value)
    text = str(value)
    if not text:
        return "''"
    if _SIMPLE_SCALAR.match(text) and text.lower() not in _RESERVED:
        return text
    return "'" + text.replace("'", "''") + "'"


def _emit(node: Any, indent: int, lines: list[str], key_prefix: str = "") -> None:
    pad = " " * indent
    if isinstance(node, Mapping):
        for key, value in node.items():
            rendered_key = yaml_scalar(key)
            if isinstance(value, Mapping):
                if not value:
                    lines.append(f"{pad}{rendered_key}: {{}}")
                else:
                    lines.append(f"{pad}{rendered_key}:")
                    _emit(value, indent + 2, lines)
            elif isinstance(value, (list, tuple)):
                if not value:
                    lines.append(f"{pad}{rendered_key}: []")
                    continue
                lines.append(f"{pad}{rendered_key}:")
                _emit(list(value), indent + 2, lines)
            else:
                lines.append(f"{pad}{rendered_key}: {yaml_scalar(value)}")
        return
    if isinstance(node, (list, tuple)):
        for item in node:
            if isinstance(item, Mapping):
                block: list[str] = []
                _emit(item, indent + 2, block)
                lines.append(f"{pad}- {block[0].strip()}")
                lines.extend(block[1:])
            elif isinstance(item, (list, tuple)):
                lines.append(f"{pad}-")
                _emit(list(item), indent + 2, lines)
            else:
                lines.append(f"{pad}- {yaml_scalar(item)}")
        return
    lines.append(f"{pad}{yaml_scalar(node)}")


def yaml_dump(document: Mapping[str, Any], header: Sequence[str] = ()) -> str:
    lines: list[str] = [f"# {line}" if line else "#" for line in header]
    if lines:
        lines.append("")
    _emit(document, 0, lines)
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Frames
# --------------------------------------------------------------------------- #

def group_frame(frame: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Collapse a frame into one service call per distinct (colour, brightness).

    Symmetric effects (checkerboard, bouncing jumps, sharp bands) put many lights
    on exactly the same colour: grouping shrinks the generated script a lot and
    the number of packets Home Assistant has to send.
    """
    groups: dict[tuple[int, int, int, int], dict[str, Any]] = {}
    for entry in frame:
        key = (entry["rgb"][0], entry["rgb"][1], entry["rgb"][2], int(entry["brightness_pct"]))
        group = groups.get(key)
        if group is None:
            groups[key] = {
                "entity_ids": [entry["entity_id"]],
                "rgb_color": list(entry["rgb"]),
                "brightness_pct": int(entry["brightness_pct"]),
            }
        else:
            group["entity_ids"].append(entry["entity_id"])
    return list(groups.values())


def build_frame_plan(
    scene: Mapping[str, Any] | None,
    effect: str = "linear_wave",
    params: Mapping[str, Any] | None = None,
    palette: Any = None,
    frames: int = DEFAULT_FRAMES,
) -> tuple[list[list[dict[str, Any]]], float]:
    """Sample one full cycle into `frames` grouped frames.

    Returns the frames and the per-frame delay in seconds.  Frame `k` is rendered
    at ``t = k / (speed * frames)`` so that the plan covers exactly one period.
    """
    frames = max(2, min(120, int(frames or DEFAULT_FRAMES)))
    period = cycle_period(params)
    # Sample at the delay that is actually written into the YAML, so the compiled
    # script replays the exact frames the engine produced.
    step = round(period / frames, 3)
    plan = []
    for index in range(frames):
        frame = compute_frame(scene, effect, params, palette, index * step)
        plan.append(group_frame(frame))
    return plan, step


# --------------------------------------------------------------------------- #
# YAML outputs
# --------------------------------------------------------------------------- #

def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")
    return slug or "ceiling_scene"


def compile_script(
    scene: Mapping[str, Any] | None,
    effect: str = "linear_wave",
    params: Mapping[str, Any] | None = None,
    palette: Any = None,
    frames: int = DEFAULT_FRAMES,
    script_name: str | None = None,
    alias: str | None = None,
    transition: float | None = None,
    icon: str = "mdi:ceiling-light-multiple",
) -> dict[str, Any]:
    """Return the ``scripts.yaml`` entry for a static, self-contained wave."""
    effect = effect if effect in EFFECTS else EFFECTS[0]
    resolved = resolve_params(params)
    scene = scene or {}
    lights = resolve_lights(scene)
    scene_name = str(scene.get("name") or "Ceiling")
    script_id = slugify(script_name or f"{scene_name}_{EFFECT_LABELS[effect]}")
    plan, step = build_frame_plan(scene, effect, resolved, palette, frames)
    fade = float(transition) if transition is not None else round(step * 0.95, 2)

    repeats = []
    for groups in plan:
        calls = [
            {
                "service": "light.turn_on",
                "target": {"entity_id": list(group["entity_ids"])},
                "data": {
                    "rgb_color": list(group["rgb_color"]),
                    "brightness_pct": group["brightness_pct"],
                    "transition": round(fade, 2),
                },
            }
            for group in groups
        ]
        repeats.append(
            {
                "parallel": calls,
                "delay": {"seconds": round(step, 3)},
            }
        )

    width, height = room_bounds(scene)
    header = [
        "Ceiling Scene Generator - compiled script",
        f"scene: {scene_name} ({width:g} x {height:g} m, {len(lights)} lights)",
        f"effect: {effect} - {EFFECT_LABELS[effect]}",
        f"equation: {EFFECT_EQUATIONS[effect]}",
        f"cycle: {round(cycle_period(resolved), 3)} s over {len(plan)} frames "
        f"(delay {round(step, 3)} s, transition {round(fade, 2)} s)",
        "regenerate: service ceiling_scene_generator.save_as_script",
        "",
        "Paste into scripts.yaml (or Settings > Automations & scenes > Scripts > Edit in YAML).",
    ]

    document = {
        script_id: {
            "alias": alias or f"Ceiling Scene - {scene_name} - {EFFECT_LABELS[effect]}",
            "icon": icon,
            "mode": "restart",
            "sequence": [{"repeat": {"count": len(plan), "sequence": repeats}}],
        }
    }
    # The empty line in the header renders as a bare '#' comment.
    return {
        "script_id": script_id,
        "yaml": yaml_dump(document, header),
        "frames": len(plan),
        "delay": round(step, 3),
        "transition": round(fade, 2),
        "cycle": round(cycle_period(resolved), 3),
        "lights": len(lights),
        "service_calls": sum(len(groups) for groups in plan),
    }


def compile_service_call(
    scene: Mapping[str, Any] | None,
    effect: str = "linear_wave",
    params: Mapping[str, Any] | None = None,
    palette: Any = None,
    update_interval: float = DEFAULT_UPDATE_INTERVAL,
    transition: float = DEFAULT_TRANSITION,
) -> str:
    """YAML front end for the live generator service."""
    effect = effect if effect in EFFECTS else EFFECTS[0]
    resolved = resolve_params(params)
    if isinstance(palette, str) and palette.strip().lower() in PALETTES:
        palette_value: Any = palette.strip().lower()
    else:
        palette_value = palette_hex_list(palette)
    entry: dict[str, Any] = {
        "service": "ceiling_scene_generator.start",
        "data": {
            "name": str((scene or {}).get("name") or "Ceiling"),
            "effect": effect,
            "params": {key: (int(value) if float(value).is_integer() else value) for key, value in sorted(resolved.items())},
            "palette": palette_value,
            "update_interval": update_interval,
            "transition": transition,
            "scene": dict(scene or {}),
        },
    }
    line = "# live generator - the integration pushes rate limited updates"
    return line + "\n" + yaml_dump(entry)


def compile_card_yaml(
    scene: Mapping[str, Any] | None,
    effect: str = "linear_wave",
    palette: Any = None,
    title: str | None = None,
) -> str:
    """Lovelace card config snippet for the compiled scene."""
    stops = normalize_palette(palette)
    config = {
        "type": "custom:ceiling-scene-card",
        "title": title or f"Ceiling Scene - {str((scene or {}).get('name') or 'Ceiling')}",
        "effect": effect if effect in EFFECTS else EFFECTS[0],
        "palette": [c if isinstance(c, str) else "#%02X%02X%02X" % tuple(c) for c in stops],
        "scene": dict(scene or {}),
    }
    return yaml_dump(config, ["Lovelace card (paste as a manual card)"])


def palette_hex_list(palette: Any) -> list[str]:
    """Palette as ``#RRGGBB`` strings (handy for the frontend and the services)."""
    return ["#%02X%02X%02X" % color for color in normalize_palette(palette)]


def palette_presets() -> dict[str, list[str]]:
    """The eight curated palettes, as hex lists."""
    return {key: list(entry["colors"]) for key, entry in PALETTES.items()}


def default_params() -> dict[str, float]:
    return dict(DEFAULT_PARAMS)
