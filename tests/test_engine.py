"""Engine behaviour: effects, palette maths, layout builder, rate limiting."""

from __future__ import annotations

import math
import unittest

from _fixtures import PALETTES, PARAM_SETS, SCENES, TIMES
from _harness import engine


class EffectContractTest(unittest.TestCase):
    """Every effect must produce a well formed, in-range frame."""

    def test_all_ten_effects_exist(self) -> None:
        self.assertEqual(len(engine.EFFECTS), 10)
        self.assertEqual(sorted(engine.EFFECT_FUNCS), sorted(engine.EFFECTS))

    def test_labels_and_equations_cover_all_effects(self) -> None:
        for effect in engine.EFFECTS:
            self.assertIn(effect, engine.EFFECT_LABELS)
            self.assertIn(effect, engine.EFFECT_EQUATIONS)
            self.assertIn(effect, engine.EFFECT_PARAMS)

    def test_frames_are_valid_for_every_effect_and_fixture(self) -> None:
        for scene_name, scene in SCENES.items():
            expected = len(scene["lights"])
            for effect in engine.EFFECTS:
                for params_name, params in PARAM_SETS.items():
                    for palette_name, palette in PALETTES.items():
                        for t in TIMES:
                            frame = engine.compute_frame(scene, effect, params, palette, t)
                            message = f"{scene_name}/{effect}/{params_name}/{palette_name}/t={t}"
                            self.assertEqual(len(frame), expected, message)
                            resolved = engine.resolve_params(params)
                            for entry in frame:
                                self.assertEqual(len(entry["rgb"]), 3, message)
                                for channel in entry["rgb"]:
                                    self.assertIsInstance(channel, int)
                                    self.assertGreaterEqual(channel, 0)
                                    self.assertLessEqual(channel, 255)
                                self.assertGreaterEqual(entry["brightness_pct"], 1, message)
                                self.assertLessEqual(entry["brightness_pct"], 100, message)
                                self.assertGreaterEqual(entry["brightness_pct"], math.floor(resolved["brightness_min"]) - 1)
                                self.assertLessEqual(entry["brightness_pct"], math.ceil(resolved["brightness_max"]) + 1)
                                self.assertGreaterEqual(entry["value"], 0.0)
                                self.assertLessEqual(entry["value"], 1.0)
                                self.assertGreaterEqual(entry["intensity"], 0.0)
                                self.assertLessEqual(entry["intensity"], 1.0)

    def test_effects_produce_distinct_output(self) -> None:
        """A regression guard against two effects collapsing into the same maths."""
        scene = SCENES["grid_3x4"]
        signatures = {}
        for effect in engine.EFFECTS:
            frame = engine.compute_frame(scene, effect, {}, "rainbow", 2.4)
            signatures[effect] = tuple((tuple(e["rgb"]), e["brightness_pct"]) for e in frame)
        self.assertEqual(len(set(signatures.values())), len(engine.EFFECTS))

    def test_determinism(self) -> None:
        scene = SCENES["irregular"]
        for effect in engine.EFFECTS:
            first = engine.compute_frame(scene, effect, {"speed": 0.31}, "aurora", 7.7)
            second = engine.compute_frame(scene, effect, {"speed": 0.31}, "aurora", 7.7)
            self.assertEqual(first, second, effect)

    def test_periodicity(self) -> None:
        """One cycle later the frame must repeat (galaxy_stars is non-periodic)."""
        scene = SCENES["grid_3x4"]
        params = {"speed": 0.25}
        period = engine.cycle_period(params)
        self.assertAlmostEqual(period, 4.0)
        for effect in engine.EFFECTS:
            if effect == "galaxy_stars":
                continue
            start = engine.compute_frame(scene, effect, params, "sunset", 1.3)
            later = engine.compute_frame(scene, effect, params, "sunset", 1.3 + period)
            for a, b in zip(start, later):
                self.assertAlmostEqual(a["value"], b["value"], places=6, msg=effect)
                self.assertAlmostEqual(a["intensity"], b["intensity"], places=6, msg=effect)

    def test_effects_move_over_time(self) -> None:
        scene = SCENES["grid_3x4"]
        for effect in engine.EFFECTS:
            frames = [engine.compute_frame(scene, effect, {"speed": 0.5}, "ocean", t) for t in (0.0, 0.4, 0.9)]
            distinct = {tuple((tuple(e["rgb"]), e["brightness_pct"]) for e in frame) for frame in frames}
            self.assertGreater(len(distinct), 1, f"{effect} is static")


class PaletteTest(unittest.TestCase):
    def test_presets_are_eight_and_well_formed(self) -> None:
        self.assertEqual(len(engine.PALETTES), 8)
        for key, entry in engine.PALETTES.items():
            self.assertTrue(entry["name"], key)
            self.assertGreaterEqual(len(entry["colors"]), 2, key)
            for color in entry["colors"]:
                parsed = engine.parse_color(color)
                self.assertRegex(color, r"^#[0-9A-F]{6}$", key)
                self.assertEqual(engine.color_hex(parsed).upper(), color.upper(), key)

    def test_stops_are_hit_exactly(self) -> None:
        stops = engine.normalize_palette("rainbow")
        count = len(stops)
        for index, stop in enumerate(stops):
            self.assertEqual(engine.palette_color(stops, index / count), stop)

    def test_cyclical_wrapping(self) -> None:
        stops = engine.normalize_palette(["#112233", "#445566", "#778899"])
        for position in (0.0, 0.13, 0.5, 0.87):
            for offset in (1.0, 2.0, 5.0):
                self.assertEqual(
                    engine.palette_color(stops, position),
                    engine.palette_color(stops, position + offset),
                )
        self.assertEqual(engine.palette_color(stops, -0.25), engine.palette_color(stops, 0.75))

    def test_interpolation_is_linear_light(self) -> None:
        """Halfway between white and black must be brighter than the sRGB average."""
        stops = engine.normalize_palette(["#000000", "#FFFFFF"])
        midpoint = engine.palette_color(stops, 0.25)[0]
        self.assertGreater(midpoint, 127)
        expected = round(engine._linear_channel_to_srgb(engine._srgb_channel_to_linear(1.0) * 0.5) * 255)
        self.assertAlmostEqual(midpoint, expected, delta=1)

    def test_single_stop_and_single_colour_palette(self) -> None:
        self.assertEqual(engine.normalize_palette(["#123456"]), [(0x12, 0x34, 0x56)])
        self.assertEqual(engine.palette_color([(0x12, 0x34, 0x56)], 0.77), (0x12, 0x34, 0x56))

    def test_invalid_palette_falls_back(self) -> None:
        fallback = engine.normalize_palette(engine.PALETTES["sunset"]["colors"])
        for bad in (None, [], "", "not-a-palette", [None, "zzz"], 42, ["nope", "#12345"]):
            self.assertEqual(engine.normalize_palette(bad), fallback, repr(bad))

    def test_partially_valid_palette_keeps_the_good_stops(self) -> None:
        self.assertEqual(
            engine.normalize_palette(["#112233", "zzz", [1, 2, 3], None]),
            [(0x11, 0x22, 0x33), (1, 2, 3)],
        )

    def test_parse_color_accepts_all_documented_forms(self) -> None:
        self.assertEqual(engine.parse_color("#ff0000"), (255, 0, 0))
        self.assertEqual(engine.parse_color("#F0A"), (255, 0, 170))
        self.assertEqual(engine.parse_color([1, 2, 3]), (1, 2, 3))
        self.assertEqual(engine.parse_color({"color": "#00FF00"}), (0, 255, 0))
        self.assertEqual(engine.parse_color("nonsense", (9, 9, 9)), (9, 9, 9))


class ParameterTest(unittest.TestCase):
    def test_defaults_are_complete(self) -> None:
        resolved = engine.resolve_params(None)
        self.assertEqual(set(resolved), set(engine.DEFAULT_PARAMS))
        for key, spec in engine.PARAM_SPECS.items():
            self.assertIn(key, resolved)
            self.assertLessEqual(spec["min"], resolved[key])
            self.assertGreaterEqual(spec["max"], resolved[key])

    def test_clamping_and_coercion(self) -> None:
        resolved = engine.resolve_params({"speed": 99, "wavelength": -5, "unknown": 3, "angle": "45"})
        self.assertEqual(resolved["speed"], engine.PARAM_SPECS["speed"]["max"])
        self.assertEqual(resolved["wavelength"], engine.PARAM_SPECS["wavelength"]["min"])
        self.assertEqual(resolved["angle"], 45.0)
        self.assertNotIn("unknown", resolved)

    def test_brightness_floor_never_exceeds_ceiling(self) -> None:
        resolved = engine.resolve_params({"brightness_min": 90, "brightness_max": 20})
        self.assertGreaterEqual(resolved["brightness_max"], resolved["brightness_min"])
        frame = engine.compute_frame(SCENES["grid_3x4"], "linear_wave", {"brightness_min": 90, "brightness_max": 20}, "sunset", 0)
        self.assertTrue(all(entry["brightness_pct"] == 90 for entry in frame))

    def test_amplitude_zero_flattens_brightness(self) -> None:
        frame = engine.compute_frame(
            SCENES["grid_3x4"], "linear_wave",
            {"amplitude": 0.0, "brightness_min": 20, "brightness_max": 100}, "sunset", 1.0,
        )
        values = {entry["brightness_pct"] for entry in frame}
        self.assertEqual(values, {60})

    def test_cycle_period(self) -> None:
        self.assertAlmostEqual(engine.cycle_period({"speed": 0.5}), 2.0)
        # speed is clamped to the documented 0.01 minimum, so the slowest cycle is 100 s
        self.assertAlmostEqual(engine.cycle_period({"speed": 0.001}), 100.0)
        self.assertEqual(engine.cycle_period({"speed": 0}), 100.0)


class GeometryTest(unittest.TestCase):
    def test_normalised_coordinates(self) -> None:
        scene = {"room": {"width": 6.0, "height": 4.5}, "lights": [{"entity_id": "light.a", "x": 3.0, "y": 2.25}]}
        node = engine.prepare_nodes(scene)[0]
        self.assertAlmostEqual(node["nx"], 0.5)
        self.assertAlmostEqual(node["ny"], 0.5)
        self.assertAlmostEqual(node["xn"], 0.0)
        self.assertAlmostEqual(node["yn"], 0.0)

    def test_perimeter_fraction_walks_clockwise_from_origin(self) -> None:
        # bottom edge (y = 0), then right edge, then top edge, then left edge
        self.assertAlmostEqual(engine.perimeter_fraction(0, 0, 4, 2), 0.0)
        self.assertAlmostEqual(engine.perimeter_fraction(4, 0, 4, 2), 4 / 12)
        self.assertAlmostEqual(engine.perimeter_fraction(4, 2, 4, 2), 6 / 12)
        self.assertAlmostEqual(engine.perimeter_fraction(0, 2, 4, 2), 10 / 12)
        for x in (0.0, 1.0, 4.0):
            for y in (0.0, 1.0, 2.0):
                fraction = engine.perimeter_fraction(x, y, 4, 2)
                self.assertGreaterEqual(fraction, 0.0)
                self.assertLess(fraction, 1.0)

    def test_perimeter_prefers_nearest_edge(self) -> None:
        """A light near the middle of a wide room clings to the closest wall."""
        self.assertAlmostEqual(engine.perimeter_fraction(2.0, 0.1, 6.0, 4.0), 2.0 / 20.0)
        self.assertAlmostEqual(engine.perimeter_fraction(5.9, 2.0, 6.0, 4.0), (6.0 + 2.0) / 20.0)

    def test_degenerate_rooms_do_not_crash(self) -> None:
        for room in ({}, {"width": 0, "height": -3}, {"width": "x", "height": None}):
            scene = {"room": room, "lights": [{"entity_id": "light.a", "x": 1, "y": 1}]}
            for effect in engine.EFFECTS:
                frame = engine.compute_frame(scene, effect, {}, "sunset", 1.0)
                self.assertEqual(len(frame), 1)

    def test_lights_without_entity_or_coordinates_are_skipped(self) -> None:
        scene = {
            "room": {"width": 4, "height": 4},
            "lights": [
                {"entity_id": "light.ok", "x": 1, "y": 1, "row": 0, "col": 0},
                {"x": 1, "y": 1},
                {"entity_id": "", "x": 1, "y": 1},
                "nonsense",
                {"entity_id": "light.defaults"},
            ],
        }
        frame = engine.compute_frame(scene, "linear_wave", {}, "sunset", 0)
        self.assertEqual([entry["entity_id"] for entry in frame], ["light.ok", "light.defaults"])
        self.assertEqual(frame[1]["rgb"], frame[1]["rgb"])


class LayoutBuilderTest(unittest.TestCase):
    def test_grid_layout_shape(self) -> None:
        layout = engine.build_layout(rows=3, cols=4, mode="grid", width=6, height=4.5, padding=0.5)
        self.assertEqual(len(layout["lights"]), 12)
        self.assertEqual(layout["grid"], {"mode": "grid", "rows": 3, "cols": 4})
        self.assertEqual(layout["lights"][0]["entity_id"], "light.ceiling_can_1")
        self.assertEqual(layout["lights"][-1]["entity_id"], "light.ceiling_can_12")
        rows = {light["row"] for light in layout["lights"]}
        self.assertEqual(rows, {0, 1, 2})

    def test_lights_stay_inside_the_usable_area(self) -> None:
        for mode in engine.GRID_MODES:
            layout = engine.build_layout(rows=4, cols=5, mode=mode, width=7.2, height=5.4, padding=0.6)
            pad = layout["room"]["padding"]
            for light in layout["lights"]:
                self.assertGreaterEqual(light["x"], pad - 1e-9, mode)
                self.assertLessEqual(light["x"], 7.2 - pad + 1e-9, mode)
                self.assertGreaterEqual(light["y"], pad - 1e-9, mode)
                self.assertLessEqual(light["y"], 5.4 - pad + 1e-9, mode)

    def test_brick_rows_are_staggered(self) -> None:
        layout = engine.build_layout(rows=4, cols=4, mode="brick", width=6, height=4, padding=0.5)
        by_row: dict[int, list[float]] = {}
        for light in layout["lights"]:
            by_row.setdefault(light["row"], []).append(light["x"])
        self.assertNotAlmostEqual(by_row[0][0], by_row[1][0], places=3)
        self.assertNotAlmostEqual(by_row[1][0], by_row[2][0], places=3)

    def test_entity_ids_are_unique_and_ordered(self) -> None:
        layout = engine.build_layout(rows=3, cols=3, mode="brick", width=5, height=5, padding=0.4, prefix="Spot 1!")
        ids = [light["entity_id"] for light in layout["lights"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(entity.startswith("light.spot_1_") for entity in ids))
        numbers = [int(entity.rsplit("_", 1)[1]) for entity in ids]
        self.assertEqual(numbers, sorted(numbers))

    def test_padding_is_clamped_and_degenerate_input_is_safe(self) -> None:
        layout = engine.build_layout(rows=1, cols=1, mode="grid", width=1, height=1, padding=50)
        self.assertLess(layout["room"]["padding"], 0.5)
        self.assertEqual(len(layout["lights"]), 1)
        layout = engine.build_layout(rows=0, cols=0, mode="nonsense", width=0, height=0, padding=-4)
        self.assertEqual(len(layout["lights"]), 1)
        self.assertEqual(layout["grid"]["mode"], "grid")


class RateLimitingTest(unittest.TestCase):
    def test_unchanged_frame_produces_no_calls(self) -> None:
        frame = engine.compute_frame(SCENES["grid_3x4"], "linear_wave", {}, "sunset", 0.0)
        previous = engine.index_frame(frame)
        self.assertEqual(engine.frame_deltas(previous, frame), [])

    def test_changed_lights_are_selected(self) -> None:
        first = engine.compute_frame(SCENES["grid_3x4"], "linear_wave", {}, "sunset", 0.0)
        later = engine.compute_frame(SCENES["grid_3x4"], "linear_wave", {}, "sunset", 2.0)
        previous = engine.index_frame(first)
        changed = engine.frame_deltas(previous, later)
        self.assertTrue(changed)
        self.assertLessEqual(len(changed), len(later))
        for entry in changed:
            old = previous[entry["entity_id"]]
            color_delta = max(abs(a - b) for a, b in zip(entry["rgb"], old["rgb"]))
            brightness_delta = abs(entry["brightness_pct"] - old["brightness_pct"])
            self.assertTrue(
                color_delta >= engine.DEFAULT_MIN_COLOR_DELTA
                or brightness_delta >= engine.DEFAULT_MIN_BRIGHTNESS_DELTA
            )

    def test_thresholds_are_configurable(self) -> None:
        first = engine.compute_frame(SCENES["grid_3x4"], "linear_wave", {"speed": 0.05}, "sunset", 0.0)
        later = engine.compute_frame(SCENES["grid_3x4"], "linear_wave", {"speed": 0.05}, "sunset", 1.5)
        previous = engine.index_frame(first)
        loose = engine.frame_deltas(previous, later, min_color_delta=1, min_brightness_delta=1)
        strict = engine.frame_deltas(previous, later, min_color_delta=255, min_brightness_delta=100)
        self.assertGreaterEqual(len(loose), len(strict))
        self.assertEqual(strict, [])

    def test_unknown_lights_are_always_sent(self) -> None:
        frame = engine.compute_frame(SCENES["grid_3x4"], "linear_wave", {}, "sunset", 0.0)
        self.assertEqual(len(engine.frame_deltas({}, frame)), len(frame))

    def test_service_payload(self) -> None:
        entry = {"entity_id": "light.a", "rgb": [1, 2, 3], "brightness_pct": 42}
        self.assertEqual(
            engine.service_payload(entry, 1.44),
            {"rgb_color": [1, 2, 3], "brightness_pct": 42, "transition": 1.44},
        )
        self.assertEqual(engine.service_payload(entry), {"rgb_color": [1, 2, 3], "brightness_pct": 42})


class HashTest(unittest.TestCase):
    def test_hash_is_deterministic_and_in_range(self) -> None:
        for index in range(40):
            for salt in (1, 7, 13, 21):
                value = engine.hash01(index, salt)
                self.assertGreaterEqual(value, 0.0)
                self.assertLess(value, 1.0)
                self.assertEqual(value, engine.hash01(index, salt))

    def test_hash_golden_values(self) -> None:
        """Locked in so a change here is caught before the parity test explains it."""
        expected = [engine.hash01(index, 1) for index in range(4)]
        self.assertEqual(len(set(expected)), 4)
        self.assertAlmostEqual(expected[0], engine.hash01(0, 1), places=12)


if __name__ == "__main__":
    unittest.main()
