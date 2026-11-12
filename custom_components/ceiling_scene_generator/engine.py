"""Ceiling Scene Generator - pure, dependency-free effect engine.

This module is the mathematical heart of the integration. It is deliberately
free of any Home Assistant import so that it can be unit tested (and reasoned
about) in isolation, and it is mirrored 1:1 by the JavaScript engine embedded in
``www/ceiling-scene-card.js`` (``globalThis.CeilingSceneEngine``).  A parity test
(``tests/test_js_parity.py``) executes both engines over identical fixtures and
fails if they ever disagree, which is what makes the Lovelace preview an honest
preview of what the physical lights will do.

Coordinate model
----------------
Two coordinate systems are used, on purpose:

``nx, ny``  (0..1, room relative)
    ``nx = x / room_width``, ``ny = y / room_height``.  Used by the directional
    effects (linear / diagonal / crossfire), so that an ``angle`` of 45 deg is
    45 deg on the floorplan regardless of the room's aspect ratio.

``xn, yn``  (-0.5..0.5, isotropic)
    ``xn = (x - room_width / 2) / s`` with ``s = max(room_width, room_height)``,
    same for ``yn``.  Metric distances and polar angles are computed here so that
    radial rings stay circular (a square room yields a circle, a 6x4 m room does
    not stretch its pulse into an ellipse).

Every effect returns a ``(value, intensity)`` pair in the 0..1 range:

``value``
    Position inside the palette (cyclically wrapped), i.e. the *colour*.
``intensity``
    Luminance envelope, mapped onto ``brightness_min..brightness_max`` and scaled
    by the ``amplitude`` parameter, i.e. the *brightness*.
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable, Mapping, Sequence

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

VERSION = "1.0.0"

TAU = math.pi * 2.0

EFFECTS: tuple[str, ...] = (
    "linear_wave",
    "radial_pulse",
    "checkerboard_breathe",
    "diagonal_runs",
    "perimeter_chase",
    "bouncing_jumps",
    "galaxy_stars",
    "spiral_vortex",
    "crossfire_waves",
    "center_burst",
)

EFFECT_LABELS: dict[str, str] = {
    "linear_wave": "Linear Wave",
    "radial_pulse": "Radial Pulse",
    "checkerboard_breathe": "Checkerboard Breathe",
    "diagonal_runs": "Diagonal Runs",
    "perimeter_chase": "Perimeter Chase",
    "bouncing_jumps": "Bouncing Jumps",
    "galaxy_stars": "Galaxy Stars",
    "spiral_vortex": "Spiral Vortex",
    "crossfire_waves": "Crossfire Waves",
    "center_burst": "Center Burst",
}

# The exact equations, shown in the UI and in the generated script header.
EFFECT_EQUATIONS: dict[str, str] = {
    "linear_wave": "u = nx*cos(a) + ny*sin(a);  v = 0.5 + 0.5*sin(2pi*(u/lam - s*t))",
    "radial_pulse": "r = hypot(xn-cx, yn-cy);  v = 0.5 + 0.5*sin(2pi*(r/lam - s*t))",
    "checkerboard_breathe": "c = (row+col) mod 2;  v = frac(s*t + c/2);  i = 0.5+0.5*sin(2pi*(2*s*t + c/2))",
    "diagonal_runs": "u = (nx+ny)/2;  p = frac(u/lam - s*t);  v = exp(-(p-0.5)^2 / (2*sigma^2))",
    "perimeter_chase": "S = arc length of projection onto room boundary;  v = 0.5 + 0.5*sin(2pi*(S/lam - s*t))",
    "bouncing_jumps": "p = frac(u/lam + s*t);  tri = 1-|2p-1|;  v = floor(tri*steps)/(steps-1)",
    "galaxy_stars": "h = hash01(index);  v = frac(h1 + 0.1*s*t);  i = h3 + (0.5+0.5*sin(2pi*(s*rate*t + h2)))^3 * (1-h3)",
    "spiral_vortex": "ang = atan2(yn-cy, xn-cx)/2pi;  v = 0.5 + 0.5*sin(2pi*(ang*arms - r/lam + s*t))",
    "crossfire_waves": "wx = 0.5+0.5*sin(2pi*(nx/lam - s*t));  wy = 0.5+0.5*sin(2pi*(ny/lam + s*t));  v = (wx+wy)/2",
    "center_burst": "r0 = frac(s*t)*0.75;  v = exp(-(r-r0)^2 / (2*sigma^2))",
}

PALETTES: dict[str, dict[str, Any]] = {
    "sunset": {"name": "Sunset", "colors": ["#FF6B35", "#F7931E", "#FDC830", "#D62828", "#6A0572"]},
    "ocean": {"name": "Ocean", "colors": ["#012E4A", "#036280", "#378BA4", "#81BECE", "#E2F1E7"]},
    "cyberpunk": {"name": "Cyberpunk", "colors": ["#FF2A6D", "#05D9E8", "#01012B", "#D1F7FF", "#7700FF"]},
    "rainbow": {"name": "Rainbow", "colors": ["#FF0000", "#FFA500", "#FFFF00", "#00C853", "#0091EA", "#6A1B9A"]},
    "forest": {"name": "Forest", "colors": ["#0B3D0B", "#1E7A34", "#62A744", "#C7E59C", "#2F5D3A"]},
    "aurora": {"name": "Aurora", "colors": ["#00C2A8", "#3BD4AE", "#7B61FF", "#1B1464", "#00E5FF"]},
    "ember": {"name": "Ember", "colors": ["#1A0000", "#5C1010", "#C1292E", "#FF7A18", "#FFD166"]},
    "ice": {"name": "Ice", "colors": ["#061B33", "#0E4C92", "#3FA9F5", "#A8E6FF", "#FFFFFF"]},
}

DEFAULT_PALETTE = "sunset"

DEFAULT_PARAMS: dict[str, float] = {
    "speed": 0.12,       # cycles per second
    "angle": 0.0,        # degrees, direction of the directional effects
    "wavelength": 0.35,  # fraction of the room's long axis per cycle
    "center_x": 0.5,     # pulse / spiral / burst centre, room relative
    "center_y": 0.5,
    "brightness_min": 15.0,
    "brightness_max": 100.0,
    "amplitude": 1.0,    # luminance swing around the mid point (0..1)
    "arms": 3.0,         # spiral arms
    "steps": 6.0,        # quantisation steps of `bouncing_jumps`
    "sigma": 0.18,       # band width of `diagonal_runs` / `center_burst`
    "phase": 0.0,        # global phase offset in cycles
}

# Ranges + UI metadata. The Lovelace card and the web studio are generated from
# this table, so a new parameter only has to be declared once.
PARAM_SPECS: dict[str, dict[str, Any]] = {
    "speed": {"min": 0.01, "max": 1.0, "step": 0.01, "label": "Speed", "unit": "cyc/s", "group": "motion"},
    "angle": {"min": 0.0, "max": 360.0, "step": 1.0, "label": "Angle", "unit": "deg", "group": "motion"},
    "wavelength": {"min": 0.05, "max": 1.5, "step": 0.01, "label": "Wavelength", "unit": "room", "group": "motion"},
    "phase": {"min": 0.0, "max": 1.0, "step": 0.01, "label": "Phase", "unit": "cyc", "group": "motion"},
    "center_x": {"min": 0.0, "max": 1.0, "step": 0.01, "label": "Pulse Center X", "unit": "", "group": "geometry"},
    "center_y": {"min": 0.0, "max": 1.0, "step": 0.01, "label": "Pulse Center Y", "unit": "", "group": "geometry"},
    "arms": {"min": 1.0, "max": 8.0, "step": 1.0, "label": "Spiral Arms", "unit": "", "group": "geometry"},
    "sigma": {"min": 0.02, "max": 0.5, "step": 0.01, "label": "Band Width", "unit": "", "group": "geometry"},
    "steps": {"min": 2.0, "max": 12.0, "step": 1.0, "label": "Jump Steps", "unit": "", "group": "geometry"},
    "brightness_min": {"min": 1.0, "max": 100.0, "step": 1.0, "label": "Brightness Floor", "unit": "%", "group": "light"},
    "brightness_max": {"min": 1.0, "max": 100.0, "step": 1.0, "label": "Brightness Ceiling", "unit": "%", "group": "light"},
    "amplitude": {"min": 0.0, "max": 1.0, "step": 0.05, "label": "Brightness Amplitude", "unit": "", "group": "light"},
}

# Which parameters actually drive each effect (used to disable irrelevant sliders).
EFFECT_PARAMS: dict[str, tuple[str, ...]] = {
    "linear_wave": ("speed", "angle", "wavelength", "phase"),
    "radial_pulse": ("speed", "wavelength", "center_x", "center_y", "phase"),
    "checkerboard_breathe": ("speed", "phase"),
    "diagonal_runs": ("speed", "wavelength", "phase", "sigma"),
    "perimeter_chase": ("speed", "wavelength", "phase"),
    "bouncing_jumps": ("speed", "angle", "wavelength", "steps", "phase"),
    "galaxy_stars": ("speed",),
    "spiral_vortex": ("speed", "wavelength", "center_x", "center_y", "arms", "phase"),
    "crossfire_waves": ("speed", "wavelength", "phase"),
    "center_burst": ("speed", "wavelength", "center_x", "center_y", "sigma", "phase"),
}

# Rate limiting / Wi-Fi friendliness.
DEFAULT_UPDATE_INTERVAL = 1.5   # seconds between service calls
DEFAULT_TRANSITION = 1.4        # hardware fade, ~= update interval
DEFAULT_FRAMES = 8              # frames per cycle baked into an exported script
DEFAULT_MIN_COLOR_DELTA = 5     # sRGB steps before a light is re-sent
DEFAULT_MIN_BRIGHTNESS_DELTA = 4

GRID_MODES = ("grid", "brick")


# --------------------------------------------------------------------------- #
# Colour helpers (sRGB <-> linear light, gamma 2.4 piecewise)
# --------------------------------------------------------------------------- #

def _srgb_channel_to_linear(c: float) -> float:
    """sRGB 0..1 -> linear light 0..1."""
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _linear_channel_to_srgb(c: float) -> float:
    """Linear light 0..1 -> sRGB 0..1."""
    if c <= 0.0031308:
        return c * 12.92
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055


def parse_color(value: Any, default: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    """Accept ``#rgb``/``#rrggbb``, ``[r, g, b]`` or ``{color: ...}``."""
    if isinstance(value, Mapping):
        value = value.get("color", value.get("hex"))
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if len(text) == 3:
            text = "".join(ch * 2 for ch in text)
        if len(text) == 6 and re.fullmatch(r"[0-9a-fA-F]+", text):
            return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
        return default
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 3:
        try:
            return (
                max(0, min(255, int(round(float(value[0]))))),
                max(0, min(255, int(round(float(value[1]))))),
                max(0, min(255, int(round(float(value[2]))))),
            )
        except (TypeError, ValueError):
            return default
    return default


def normalize_palette(palette: Any) -> list[tuple[int, int, int]]:
    """Normalise any palette-ish input into a list of >=1 RGB tuples.

    A string is treated as a palette *id* ("sunset").  Unparseable stops are
    dropped; when nothing survives, the default palette is used, so an effect is
    always renderable.
    """
    if isinstance(palette, str):
        entry = PALETTES.get(palette.strip().lower())
        palette = entry["colors"] if entry else PALETTES[DEFAULT_PALETTE]["colors"]
    if not isinstance(palette, (list, tuple)) or not palette:
        palette = PALETTES[DEFAULT_PALETTE]["colors"]
    stops = [color for color in (parse_color(item, None) for item in palette) if color is not None]
    if not stops:
        stops = [parse_color(color, None) for color in PALETTES[DEFAULT_PALETTE]["colors"]]
        stops = [color for color in stops if color is not None]
    return stops


def palette_color(palette: Sequence[tuple[int, int, int]], position: float) -> tuple[int, int, int]:
    """Cyclically wrapped interpolation between palette stops in linear light."""
    stops = palette
    n = len(stops)
    if n == 1:
        return stops[0]
    pos = position - math.floor(position)          # wrap into [0, 1)
    scaled = pos * n
    index = int(math.floor(scaled)) % n
    frac = scaled - math.floor(scaled)
    c0 = stops[index]
    c1 = stops[(index + 1) % n]
    out = []
    for channel in range(3):
        a = _srgb_channel_to_linear(c0[channel] / 255.0)
        b = _srgb_channel_to_linear(c1[channel] / 255.0)
        mixed = a + (b - a) * frac
        out.append(max(0, min(255, round_half_up(_linear_channel_to_srgb(mixed) * 255.0))))
    return (out[0], out[1], out[2])


def color_hex(rgb: Sequence[int]) -> str:
    return "#%02X%02X%02X" % (rgb[0], rgb[1], rgb[2])


def wrap01(value: float) -> float:
    return value - math.floor(value)


def sin01(cycles: float) -> float:
    """sin() mapped to 0..1 with `cycles` measured in whole periods."""
    return 0.5 + 0.5 * math.sin(TAU * cycles)


def hash01(index: int, salt: int = 0) -> float:
    """Deterministic 32-bit integer hash -> 0..1 (bit-identical in Python/JS)."""
    h = (int(index) * 2654435761 + int(salt) * 40503 + 0x9E3779B9) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 2246822519) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 3266489917) & 0xFFFFFFFF
    h ^= h >> 16
    return h / 4294967296.0


# --------------------------------------------------------------------------- #
# Parameters / geometry
# --------------------------------------------------------------------------- #

def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


def round_half_up(value: float) -> int:
    """Round half away from -inf, exactly like JavaScript's ``Math.round``.

    Python's built-in ``round`` is banker's rounding, which would make the Python
    engine and the JS preview disagree by one unit on exact .5 values.
    """
    return int(math.floor(value + 0.5))


def resolve_params(params: Mapping[str, Any] | None) -> dict[str, float]:
    """Merge user params over the defaults, coerced to float and range-clamped."""
    resolved = dict(DEFAULT_PARAMS)
    if params:
        for key, value in params.items():
            if key not in DEFAULT_PARAMS:
                continue
            try:
                resolved[key] = float(value)
            except (TypeError, ValueError):
                continue
    for key, value in resolved.items():
        spec = PARAM_SPECS.get(key)
        if spec:
            resolved[key] = clamp(value, float(spec["min"]), float(spec["max"]))
    if resolved["brightness_max"] < resolved["brightness_min"]:
        resolved["brightness_max"] = resolved["brightness_min"]
    return resolved


def room_bounds(scene: Mapping[str, Any] | None) -> tuple[float, float]:
    room = (scene or {}).get("room") or {}
    try:
        width = float(room.get("width", 6.0))
    except (TypeError, ValueError):
        width = 6.0
    try:
        height = float(room.get("height", 4.5))
    except (TypeError, ValueError):
        height = 4.5
    width = width if width > 0.01 else 0.01
    height = height if height > 0.01 else 0.01
    return width, height


def resolve_lights(scene: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Pull the light list out of a scene, tolerating partial entries."""
    raw = (scene or {}).get("lights") or []
    lights: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            continue
        entity_id = str(item.get("entity_id") or item.get("entity") or "").strip()
        if not entity_id:
            continue
        try:
            x = float(item.get("x", 0.0))
            y = float(item.get("y", 0.0))
        except (TypeError, ValueError):
            x, y = 0.0, 0.0
        try:
            row = int(item.get("row", 0))
        except (TypeError, ValueError):
            row = 0
        try:
            col = int(item.get("col", 0))
        except (TypeError, ValueError):
            col = 0
        lights.append(
            {
                "entity_id": entity_id,
                "x": x,
                "y": y,
                "row": row,
                "col": col,
                "index": index,
                "name": str(item.get("name") or entity_id),
            }
        )
    return lights


def prepare_nodes(scene: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Attach the normalised coordinate systems used by the effects."""
    width, height = room_bounds(scene)
    scale = max(width, height)
    nodes: list[dict[str, Any]] = []
    for light in resolve_lights(scene):
        nodes.append(
            {
                **light,
                "nx": light["x"] / width,
                "ny": light["y"] / height,
                "xn": (light["x"] - width / 2.0) / scale,
                "yn": (light["y"] - height / 2.0) / scale,
                "rw": width,
                "rh": height,
            }
        )
    return nodes


def perimeter_fraction(x: float, y: float, width: float, height: float) -> float:
    """Normalised arc length (0..1) of the projection onto the room perimeter.

    The walk starts at the (0, 0) corner and runs clockwise in screen space:
    bottom edge -> right edge -> top edge -> left edge.
    """
    perimeter = 2.0 * (width + height)
    if perimeter <= 0:
        return 0.0
    px = clamp(x, 0.0, width)
    py = clamp(y, 0.0, height)
    candidates = (
        (py, px),                        # y = 0 edge, left -> right
        (width - px, width + py),        # x = width edge, top -> bottom
        (height - py, width + height + (width - px)),   # y = height edge, right -> left
        (px, 2.0 * width + height + (height - py)),     # x = 0 edge, bottom -> top
    )
    best_distance, best_arc = candidates[0]
    for distance, arc in candidates[1:]:
        if distance < best_distance:
            best_distance, best_arc = distance, arc
    return (best_arc % perimeter) / perimeter


# --------------------------------------------------------------------------- #
# The ten effects.  Each returns (value, intensity) in 0..1 for one node.
# --------------------------------------------------------------------------- #

def _direction(node: Mapping[str, Any], params: Mapping[str, float]) -> float:
    """Projection of a node onto the wave direction (room relative, 0..1 scale)."""
    angle = math.radians(params["angle"])
    return node["nx"] * math.cos(angle) + node["ny"] * math.sin(angle)


def effect_linear_wave(node, params, t):
    u = _direction(node, params)
    v = sin01(u / params["wavelength"] - params["speed"] * t + params["phase"])
    return v, v


def effect_radial_pulse(node, params, t):
    dx = node["xn"] - (params["center_x"] - 0.5)
    dy = node["yn"] - (params["center_y"] - 0.5)
    r = math.hypot(dx, dy)
    v = sin01(r / params["wavelength"] - params["speed"] * t + params["phase"])
    return v, v


def effect_checkerboard_breathe(node, params, t):
    parity = (node["row"] + node["col"]) % 2
    v = wrap01(params["speed"] * t + (0.5 if parity else 0.0) + params["phase"])
    intensity = sin01(2.0 * params["speed"] * t + (0.5 if parity else 0.0) + params["phase"])
    return v, intensity


def effect_diagonal_runs(node, params, t):
    u = (node["nx"] + node["ny"]) / 2.0
    p = wrap01(u / params["wavelength"] - params["speed"] * t + params["phase"])
    d = p - 0.5
    v = math.exp(-(d * d) / (2.0 * params["sigma"] * params["sigma"]))
    return v, v


def effect_perimeter_chase(node, params, t):
    s = perimeter_fraction(node["x"], node["y"], node["rw"], node["rh"])
    v = sin01(s / params["wavelength"] - params["speed"] * t + params["phase"])
    return v, v


def effect_bouncing_jumps(node, params, t):
    u = _direction(node, params)
    p = wrap01(u / params["wavelength"] + params["speed"] * t + params["phase"])
    tri = 1.0 - abs(2.0 * p - 1.0)
    steps = max(2.0, params["steps"])
    v = math.floor(tri * steps) / (steps - 1.0)
    v = clamp(v, 0.0, 1.0)
    return v, 0.35 + 0.65 * v


def effect_galaxy_stars(node, params, t):
    index = node["index"]
    h1 = hash01(index, 1)
    h2 = hash01(index, 7)
    h3 = hash01(index, 13)
    rate = 0.5 + 1.5 * hash01(index, 21)
    twinkle = sin01(params["speed"] * rate * t + h2)
    twinkle = twinkle * twinkle * twinkle
    v = wrap01(h1 + 0.1 * params["speed"] * t + params["phase"])
    intensity = 0.15 + 0.25 * h3 + twinkle * (0.85 - 0.25 * h3)
    return v, clamp(intensity, 0.0, 1.0)


def effect_spiral_vortex(node, params, t):
    dx = node["xn"] - (params["center_x"] - 0.5)
    dy = node["yn"] - (params["center_y"] - 0.5)
    radius = math.hypot(dx, dy)
    angle = math.atan2(dy, dx) / TAU
    v = sin01(angle * params["arms"] - radius / params["wavelength"] + params["speed"] * t + params["phase"])
    return v, v


def effect_crossfire_waves(node, params, t):
    wave_x = sin01(node["nx"] / params["wavelength"] - params["speed"] * t + params["phase"])
    wave_y = sin01(node["ny"] / params["wavelength"] + params["speed"] * t + params["phase"])
    v = (wave_x + wave_y) / 2.0
    return v, v


def effect_center_burst(node, params, t):
    dx = node["xn"] - (params["center_x"] - 0.5)
    dy = node["yn"] - (params["center_y"] - 0.5)
    r = math.hypot(dx, dy)
    radius = wrap01(params["speed"] * t + params["phase"]) * 0.75
    d = r - radius
    v = math.exp(-(d * d) / (2.0 * params["sigma"] * params["sigma"]))
    return v, 0.25 + 0.75 * v


EFFECT_FUNCS = {
    "linear_wave": effect_linear_wave,
    "radial_pulse": effect_radial_pulse,
    "checkerboard_breathe": effect_checkerboard_breathe,
    "diagonal_runs": effect_diagonal_runs,
    "perimeter_chase": effect_perimeter_chase,
    "bouncing_jumps": effect_bouncing_jumps,
    "galaxy_stars": effect_galaxy_stars,
    "spiral_vortex": effect_spiral_vortex,
    "crossfire_waves": effect_crossfire_waves,
    "center_burst": effect_center_burst,
}


# --------------------------------------------------------------------------- #
# Frame computation
# --------------------------------------------------------------------------- #

def compute_frame(
    scene: Mapping[str, Any] | None,
    effect: str = "linear_wave",
    params: Mapping[str, Any] | None = None,
    palette: Any = None,
    t: float = 0.0,
) -> list[dict[str, Any]]:
    """Full frame for one instant in time.

    Returns one entry per light: ``entity_id``, ``rgb`` (0..255 ints),
    ``brightness_pct``, plus the raw ``value``/``intensity`` used by the canvas
    preview (rounded to 6 decimals so Python and JS stay comparable).
    """
    resolved = resolve_params(params)
    stops = normalize_palette(palette)
    func = EFFECT_FUNCS.get(effect) or EFFECT_FUNCS["linear_wave"]
    frame: list[dict[str, Any]] = []
    for node in prepare_nodes(scene):
        value, intensity = func(node, resolved, float(t))
        value = clamp(value, 0.0, 1.0)
        intensity = clamp(intensity, 0.0, 1.0)
        rgb = palette_color(stops, value)
        mixed = clamp(0.5 + resolved["amplitude"] * (intensity - 0.5), 0.0, 1.0)
        brightness = resolved["brightness_min"] + (
            resolved["brightness_max"] - resolved["brightness_min"]
        ) * mixed
        frame.append(
            {
                "entity_id": node["entity_id"],
                "rgb": [rgb[0], rgb[1], rgb[2]],
                "brightness_pct": round_half_up(clamp(brightness, 1.0, 100.0)),
                "value": round(value, 6),
                "intensity": round(intensity, 6),
                "row": node["row"],
                "col": node["col"],
            }
        )
    return frame


def cycle_period(params: Mapping[str, Any] | None) -> float:
    """Seconds for one full cycle of the effect."""
    speed = resolve_params(params)["speed"]
    if speed <= 0:
        return 60.0
    return 1.0 / speed


# --------------------------------------------------------------------------- #
# Rate limiting (keeps the Wi-Fi quiet while the visible motion stays smooth)
# --------------------------------------------------------------------------- #

def frame_deltas(
    previous: Mapping[str, Mapping[str, Any]],
    frame: Iterable[Mapping[str, Any]],
    min_color_delta: int = DEFAULT_MIN_COLOR_DELTA,
    min_brightness_delta: int = DEFAULT_MIN_BRIGHTNESS_DELTA,
) -> list[dict[str, Any]]:
    """Subset of `frame` that differs enough from `previous` to be worth sending."""
    changed: list[dict[str, Any]] = []
    for entry in frame:
        old = previous.get(entry["entity_id"])
        if old is None:
            changed.append(dict(entry))
            continue
        color_delta = max(abs(entry["rgb"][i] - old["rgb"][i]) for i in range(3))
        brightness_delta = abs(entry["brightness_pct"] - old["brightness_pct"])
        if color_delta >= min_color_delta or brightness_delta >= min_brightness_delta:
            changed.append(dict(entry))
    return changed


def index_frame(frame: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {entry["entity_id"]: dict(entry) for entry in frame}


def service_payload(entry: Mapping[str, Any], transition: float | None = None) -> dict[str, Any]:
    """`light.turn_on` data for one engine entry."""
    payload: dict[str, Any] = {
        "rgb_color": list(entry["rgb"]),
        "brightness_pct": int(entry["brightness_pct"]),
    }
    if transition is not None:
        payload["transition"] = round(float(transition), 2)
    return payload


# --------------------------------------------------------------------------- #
# Layout builder (shared by the integration services, the card and the studio)
# --------------------------------------------------------------------------- #

def build_layout(
    prefix: str = "ceiling_can",
    rows: int = 3,
    cols: int = 4,
    mode: str = "grid",
    width: float = 6.0,
    height: float = 4.5,
    padding: float = 0.5,
    name: str = "Ceiling",
    domain: str = "light",
    sequential_cols: bool = False,
) -> dict[str, Any]:
    """Generate a rows x cols ceiling layout (grid or brick/staggered rows).

    Entity ids are ``<domain>.<prefix>_<n>`` numbered row-major from 1.  A brick
    row is offset by half a cell; the trailing light is dropped when it would
    leave the usable area, so rows can hold ``cols`` or ``cols - 1`` lights.
    """
    rows = max(1, int(rows))
    cols = max(1, int(cols))
    width = float(width) if float(width) > 0.01 else 0.01
    height = float(height) if float(height) > 0.01 else 0.01
    pad = clamp(float(padding), 0.0, min(width, height) / 2.0 - 0.01 if min(width, height) > 0.02 else 0.0)
    usable_w = max(0.01, width - 2 * pad)
    usable_h = max(0.01, height - 2 * pad)
    cell_w = usable_w / cols
    cell_h = usable_h / rows
    prefix = re.sub(r"[^a-z0-9_]+", "_", (prefix or "ceiling_can").strip().lower()).strip("_") or "ceiling_can"
    domain = re.sub(r"[^a-z0-9_]+", "_", (domain or "light").strip().lower()).strip("_") or "light"
    mode = mode if mode in GRID_MODES else "grid"

    lights: list[dict[str, Any]] = []
    counter = 1
    for row in range(rows):
        offset = cell_w / 2.0 if (mode == "brick" and row % 2 == 1) else 0.0
        col = 0
        while col < cols:
            x = pad + (col + 0.5) * cell_w + offset
            y = pad + (row + 0.5) * cell_h
            if x > width - pad + 1e-9:
                break
            lights.append(
                {
                    "entity_id": f"{domain}.{prefix}_{counter}",
                    "name": f"Can {counter}",
                    "x": round(x, 4),
                    "y": round(y, 4),
                    "row": row,
                    "col": counter - 1 if sequential_cols else col,
                }
            )
            counter += 1
            col += 1
    return {
        "name": name,
        "room": {"width": round(width, 4), "height": round(height, 4), "padding": round(pad, 4)},
        "grid": {"mode": mode, "rows": rows, "cols": cols},
        "lights": lights,
    }
