"""The static scripts.yaml compiler and the YAML writer underneath it."""

from __future__ import annotations

import unittest

from _fixtures import PARAM_SETS, SCENES
from _harness import engine, script_compiler
from _yaml import parse_text


class YamlWriterTest(unittest.TestCase):
    def test_scalar_quoting(self) -> None:
        cases = {
            "plain": "plain",
            "Ceiling Scene - Living Room": "'Ceiling Scene - Living Room'",
            "light.can_1": "light.can_1",
            "on": "'on'",
            "": "''",
            "1.5": "1.5",
            "12": "12",
            "true": "'true'",
            "false": "'false'",
            "yes": "'yes'",
            "null": "'null'",
            "True": "'True'",
            "no: yes": "'no: yes'",
            "it's": "'it''s'",
        }
        for value, expected in cases.items():
            self.assertEqual(script_compiler.yaml_scalar(value), expected, repr(value))

    def test_dump_round_trips_through_a_real_parser(self) -> None:
        document = {
            "script_one": {
                "alias": "Ceiling Scene - Kitchen: 3x2 (main)",
                "mode": "restart",
                "sequence": [
                    {
                        "parallel": [
                            {
                                "service": "light.turn_on",
                                "target": {"entity_id": ["light.can_1", "light.can_2"]},
                                "data": {"rgb_color": [1, 2, 3], "brightness_pct": 55, "transition": 1.44},
                            }
                        ],
                        "delay": {"seconds": 0.5},
                    }
                ],
            }
        }
        parsed = parse_text(script_compiler.yaml_dump(document, ["header line", ""]))
        self.assertEqual(parsed, document)

    def test_empty_mapping_and_list_render_as_flow(self) -> None:
        text = script_compiler.yaml_dump({"a": {}, "b": [], "c": [1, 2]})
        parsed = parse_text(text)
        self.assertEqual(parsed, {"a": {}, "b": [], "c": [1, 2]})


class SlugifyTest(unittest.TestCase):
    def test_slugify(self) -> None:
        self.assertEqual(script_compiler.slugify("Living Room"), "living_room")
        self.assertEqual(script_compiler.slugify("Ceiling · 5x4!"), "ceiling_5x4")
        self.assertEqual(script_compiler.slugify(""), "ceiling_scene")
        self.assertEqual(script_compiler.slugify("###"), "ceiling_scene")


class GroupFrameTest(unittest.TestCase):
    def test_identical_colours_are_grouped(self) -> None:
        frame = [
            {"entity_id": "light.a", "rgb": [10, 20, 30], "brightness_pct": 60},
            {"entity_id": "light.b", "rgb": [10, 20, 30], "brightness_pct": 60},
            {"entity_id": "light.c", "rgb": [10, 20, 31], "brightness_pct": 60},
            {"entity_id": "light.d", "rgb": [10, 20, 30], "brightness_pct": 61},
        ]
        groups = script_compiler.group_frame(frame)
        self.assertEqual(len(groups), 3)
        sizes = sorted(len(group["entity_ids"]) for group in groups)
        self.assertEqual(sizes, [1, 1, 2])
        self.assertEqual(groups[0]["entity_ids"], ["light.a", "light.b"])

    def test_grouping_keeps_every_light(self) -> None:
        scene = SCENES["brick_4x5"]
        frame = engine.compute_frame(scene, "checkerboard_breathe", {}, "sunset", 0.4)
        groups = script_compiler.group_frame(frame)
        collected = [entity for group in groups for entity in group["entity_ids"]]
        self.assertEqual(sorted(collected), sorted(light["entity_id"] for light in scene["lights"]))


class CompileScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scene = SCENES["grid_3x4"]
        self.result = script_compiler.compile_script(
            self.scene, "linear_wave", {"speed": 0.5}, "sunset", frames=6
        )
        self.document = parse_text(self.result["yaml"])
        self.script = self.document[self.result["script_id"]]
        self.repeat = self.script["sequence"][0]["repeat"]

    def test_document_shape(self) -> None:
        self.assertEqual(list(self.document), [self.result["script_id"]])
        self.assertEqual(self.script["mode"], "restart")
        self.assertEqual(self.script["icon"], "mdi:ceiling-light-multiple")
        self.assertIn("Living Room", self.script["alias"])
        self.assertEqual(self.repeat["count"], 6)
        self.assertEqual(len(self.repeat["sequence"]), 6)

    def test_timing_maths(self) -> None:
        # speed 0.5 -> 2 s cycle, 6 frames -> 0.333 s delay, transition 95%
        self.assertAlmostEqual(self.result["cycle"], 2.0, places=3)
        self.assertAlmostEqual(self.result["delay"], round(2.0 / 6, 3), places=3)
        self.assertAlmostEqual(self.result["transition"], round(self.result["delay"] * 0.95, 2), places=2)
        for frame in self.repeat["sequence"]:
            self.assertAlmostEqual(frame["delay"]["seconds"], self.result["delay"], places=3)

    def test_every_light_is_driven_in_every_frame(self) -> None:
        expected = {light["entity_id"] for light in self.scene["lights"]}
        for frame in self.repeat["sequence"]:
            seen: set[str] = set()
            for call in frame["parallel"]:
                self.assertEqual(call["service"], "light.turn_on")
                self.assertLessEqual(set(call["data"]), {"rgb_color", "brightness_pct", "transition"})
                for channel in call["data"]["rgb_color"]:
                    self.assertGreaterEqual(channel, 0)
                    self.assertLessEqual(channel, 255)
                self.assertGreaterEqual(call["data"]["brightness_pct"], 1)
                self.assertLessEqual(call["data"]["brightness_pct"], 100)
                seen.update(call["target"]["entity_id"])
            self.assertEqual(seen, expected)

    def test_colours_match_the_engine_exactly(self) -> None:
        """The compiled script must reproduce engine frames sample for sample."""
        step = self.result["delay"]
        for index, frame in enumerate(self.repeat["sequence"]):
            expected = engine.compute_frame(self.scene, "linear_wave", {"speed": 0.5}, "sunset", index * step)
            expected_by_color: dict[tuple, set[str]] = {}
            for entry in expected:
                key = (tuple(entry["rgb"]), entry["brightness_pct"])
                expected_by_color.setdefault(key, set()).add(entry["entity_id"])
            actual = {
                (tuple(call["data"]["rgb_color"]), call["data"]["brightness_pct"]): set(call["target"]["entity_id"])
                for call in frame["parallel"]
            }
            self.assertEqual(actual, expected_by_color, f"frame {index}")

    def test_symmetric_effects_collapse_into_few_calls(self) -> None:
        result = script_compiler.compile_script(
            self.scene, "checkerboard_breathe", {}, "sunset", frames=4
        )
        document = parse_text(result["yaml"])
        frames = document[result["script_id"]]["sequence"][0]["repeat"]["sequence"]
        self.assertTrue(all(len(frame["parallel"]) <= 2 for frame in frames))
        self.assertLessEqual(result["service_calls"], 8)

    def test_script_id_and_alias_can_be_overridden(self) -> None:
        result = script_compiler.compile_script(
            self.scene, "spiral_vortex", {}, "aurora",
            script_name="My Fancy Script", alias="Fancy", frames=4,
        )
        self.assertEqual(result["script_id"], "my_fancy_script")
        document = parse_text(result["yaml"])
        self.assertEqual(document["my_fancy_script"]["alias"], "Fancy")

    def test_transition_override(self) -> None:
        result = script_compiler.compile_script(
            self.scene, "radial_pulse", {}, "ice", frames=4, transition=2.5
        )
        document = parse_text(result["yaml"])
        calls = document[result["script_id"]]["sequence"][0]["repeat"]["sequence"][0]["parallel"]
        self.assertTrue(all(call["data"]["transition"] == 2.5 for call in calls))

    def test_frame_count_is_clamped(self) -> None:
        self.assertEqual(script_compiler.compile_script(self.scene, frames=1)["frames"], 2)
        self.assertEqual(script_compiler.compile_script(self.scene, frames=5000)["frames"], 120)

    def test_header_documents_the_equation(self) -> None:
        text = script_compiler.compile_script(self.scene, "spiral_vortex", {}, "sunset", frames=3)["yaml"]
        self.assertIn("spiral_vortex", text)
        self.assertIn("equation:", text)
        self.assertIn("ceiling_scene_generator.save_as_script", text)

    def test_all_effects_compile(self) -> None:
        for effect in engine.EFFECTS:
            result = script_compiler.compile_script(self.scene, effect, PARAM_SETS["custom"], "rainbow", frames=3)
            document = parse_text(result["yaml"])
            self.assertIn(result["script_id"], document, effect)


class CompileServiceCallTest(unittest.TestCase):
    def test_service_call_names_the_live_generator(self) -> None:
        text = script_compiler.compile_service_call(
            SCENES["irregular"], "galaxy_stars", PARAM_SETS["custom"], "cyberpunk",
            update_interval=1.5, transition=1.4,
        )
        document = parse_text(text)
        self.assertEqual(document["service"], "ceiling_scene_generator.start")
        data = document["data"]
        self.assertEqual(data["effect"], "galaxy_stars")
        self.assertEqual(data["update_interval"], 1.5)
        self.assertEqual(data["transition"], 1.4)
        self.assertEqual(len(data["scene"]["lights"]), 5)
        self.assertEqual(data["params"]["speed"], 0.2)
        self.assertIsInstance(data["params"]["arms"], int)

    def test_palette_preset_is_kept_readable(self) -> None:
        """A preset name stays a preset name; only custom stops are expanded."""
        document = parse_text(
            script_compiler.compile_service_call(SCENES["grid_3x4"], "linear_wave", {}, "aurora")
        )
        self.assertEqual(document["data"]["palette"], "aurora")

    def test_custom_palette_is_expanded_to_hex(self) -> None:
        document = parse_text(
            script_compiler.compile_service_call(
                SCENES["grid_3x4"], "linear_wave", {}, ["#010203", "#AABBCC"]
            )
        )
        self.assertEqual(document["data"]["palette"], ["#010203", "#AABBCC"])


class CompileCardYamlTest(unittest.TestCase):
    def test_card_config_snippet(self) -> None:
        document = parse_text(
            script_compiler.compile_card_yaml(SCENES["grid_3x4"], "crossfire_waves", "sunset")
        )
        self.assertEqual(document["type"], "custom:ceiling-scene-card")
        self.assertEqual(document["effect"], "crossfire_waves")
        self.assertEqual(document["palette"][0], "#FF6B35")
        self.assertEqual(len(document["scene"]["lights"]), 12)


class PaletteHelperTest(unittest.TestCase):
    def test_palette_hex_list_and_presets(self) -> None:
        self.assertEqual(script_compiler.palette_hex_list("sunset")[0], "#FF6B35")
        presets = script_compiler.palette_presets()
        self.assertEqual(len(presets), 8)
        self.assertEqual(presets["ice"][-1], "#FFFFFF")

    def test_default_params_copy(self) -> None:
        params = script_compiler.default_params()
        params["speed"] = 0.99
        self.assertNotEqual(engine.DEFAULT_PARAMS["speed"], 0.99)


if __name__ == "__main__":
    unittest.main()
