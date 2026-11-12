"""Shared fixtures for the Python suite and the JS parity test."""

from __future__ import annotations

from _harness import engine

SCENES: dict[str, dict] = {
    "grid_3x4": engine.build_layout(
        prefix="ceiling_can", rows=3, cols=4, mode="grid",
        width=6.0, height=4.5, padding=0.5, name="Living Room",
    ),
    "square_3x3": engine.build_layout(
        prefix="can", rows=3, cols=3, mode="grid",
        width=5.0, height=5.0, padding=0.4, name="Square",
    ),
    "brick_4x5": engine.build_layout(
        prefix="l", rows=4, cols=5, mode="brick",
        width=7.2, height=5.4, padding=0.6, domain="light", name="Brick Room",
    ),
    "irregular": {
        "name": "Irregular",
        "room": {"width": 5.5, "height": 3.8, "padding": 0.3},
        "grid": {"mode": "grid", "rows": 2, "cols": 3},
        "lights": [
            {"entity_id": "light.hall_a", "x": 0.8, "y": 0.9, "row": 0, "col": 0},
            {"entity_id": "light.hall_b", "x": 2.75, "y": 0.9, "row": 0, "col": 1},
            {"entity_id": "light.hall_c", "x": 4.7, "y": 0.9, "row": 0, "col": 2},
            {"entity_id": "light.hall_d", "x": 1.2, "y": 2.9, "row": 1, "col": 0},
            {"entity_id": "light.hall_e", "x": 4.3, "y": 2.9, "row": 1, "col": 1},
        ],
    },
}

PARAM_SETS: dict[str, dict] = {
    "default": {},
    "custom": {
        "speed": 0.2, "wavelength": 0.5, "angle": 25.0, "center_x": 0.35,
        "center_y": 0.6, "amplitude": 0.8, "brightness_min": 10.0,
        "brightness_max": 90.0, "arms": 5.0, "steps": 4.0, "sigma": 0.25,
        "phase": 0.3,
    },
}

PALETTES: dict[str, object] = {
    "sunset": "sunset",
    "rainbow": "rainbow",
    "two_stop": ["#FF0044", "#00FFAA"],
    "seven_stops": ["#101820", "#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#3B1F2B", "#E8E9F3"],
    "rgb_lists": [[255, 0, 0], [0, 0, 255], [10, 200, 90]],
    "dodgy": ["#112233", "zzz", [1, 2, 3], None],
}

TIMES: tuple[float, ...] = (0.0, 0.37, 1.5, 3.25, 10.125)

# The subset used for the (heavier) JS parity sweep.
PARITY_SCENES = ("grid_3x4", "square_3x3", "irregular")
PARITY_PALETTES = ("sunset", "two_stop", "rainbow", "dodgy")
PARITY_PARAMS = ("default", "custom")
PARITY_TIMES: tuple[float, ...] = (0.0, 1.5, 3.25)


def parity_cases() -> list[dict]:
    """Every (scene, effect, params, palette, t) combination compared with JS."""
    cases: list[dict] = []
    for scene_name in PARITY_SCENES:
        for effect in engine.EFFECTS:
            for params_name in PARITY_PARAMS:
                for palette_name in PARITY_PALETTES:
                    for t in PARITY_TIMES:
                        cases.append(
                            {
                                "id": f"{scene_name}|{effect}|{params_name}|{palette_name}|{t}",
                                "scene": SCENES[scene_name],
                                "effect": effect,
                                "params": PARAM_SETS[params_name],
                                "palette": PALETTES[palette_name],
                                "t": t,
                            }
                        )
    return cases


def layout_cases() -> list[dict]:
    """Options fed to engine.build_layout on both sides."""
    return [
        {"prefix": "ceiling_can", "rows": 3, "cols": 4, "mode": "grid", "width": 6, "height": 4.5, "padding": 0.5, "name": "A"},
        {"prefix": "can", "rows": 2, "cols": 6, "mode": "brick", "width": 8, "height": 4, "padding": 0.75, "name": "B"},
        {"prefix": "spot", "rows": 5, "cols": 5, "mode": "brick", "width": 4, "height": 4, "padding": 0.2, "name": "C"},
        {"prefix": "ring", "rows": 1, "cols": 8, "mode": "grid", "width": 6, "height": 1.2, "padding": 1.5, "name": "D"},
    ]
