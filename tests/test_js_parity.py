"""Python <-> JavaScript parity.

`engine.py` (what the lights actually do) and the JS engine inside
`www/ceiling-scene-card.js` (what the canvas preview shows) must agree, otherwise
the preview is a lie.  This test executes both engines over the same fixtures and
compares every frame, the palette table, the interpolation sweep and the layout
builder.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from _fixtures import PALETTES, layout_cases, parity_cases
from _harness import CARD_JS, ROOT, engine

NODE = shutil.which("node")
SCRATCH = pathlib.Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
DUMP_SCRIPT = ROOT / "tests" / "parity_dump.js"

VALUE_TOLERANCE = 1e-6
CHANNEL_TOLERANCE = 1
CHANNEL_NOISE_BUDGET = 0.02  # share of channels allowed to differ by one step


def _scratch_file(suffix: str) -> pathlib.Path:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, dir=str(SCRATCH), encoding="utf-8")
    handle.close()
    return pathlib.Path(handle.name)


@unittest.skipIf(NODE is None, "node is required for the parity test")
class EngineParityTest(unittest.TestCase):
    """One Node run, then a handful of focused comparisons."""

    maxDiff = 4000

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = parity_cases()
        payload = {
            "palettes": PALETTES,
            "layouts": layout_cases(),
            "cases": [{k: v for k, v in case.items() if k != "expected"} for case in cls.cases],
        }
        cls.payload = payload
        cls.expected_frames = [
            engine.compute_frame(case["scene"], case["effect"], case["params"], case["palette"], case["t"])
            for case in cls.cases
        ]
        fixture = _scratch_file(".json")
        fixture.write_text(json.dumps(payload), encoding="utf-8")
        try:
            completed = subprocess.run(
                [NODE, str(DUMP_SCRIPT), str(fixture)],
                capture_output=True, text=True, timeout=300,
            )
        finally:
            fixture.unlink(missing_ok=True)
        assert completed.returncode == 0, completed.stderr
        cls.js = json.loads(completed.stdout)

    def test_version_and_effect_order(self) -> None:
        self.assertEqual(self.js["version"], engine.VERSION)
        self.assertEqual(self.js["effects"], list(engine.EFFECTS))

    def test_palette_table_matches(self) -> None:
        for key, entry in engine.PALETTES.items():
            self.assertIn(key, self.js["paletteTable"], key)
            self.assertEqual(self.js["paletteTable"][key]["name"], entry["name"], key)
            self.assertEqual(self.js["paletteTable"][key]["colors"], entry["colors"], key)
        self.assertEqual(sorted(self.js["paletteTable"]), sorted(engine.PALETTES))

    def test_palette_normalisation_matches(self) -> None:
        for name in PALETTES:
            expected = [engine.color_hex(color) for color in engine.normalize_palette(PALETTES[name])]
            self.assertEqual(self.js["palettes"][name], expected, name)

    def test_palette_interpolation_sweep_matches_exactly(self) -> None:
        for name in PALETTES:
            stops = engine.normalize_palette(PALETTES[name])
            sweep = self.js["paletteSweep"][name]
            self.assertEqual(len(sweep), 65)
            for position, red, green, blue in sweep:
                expected = engine.palette_color(stops, position)
                self.assertEqual((red, green, blue), expected, f"{name} @ {position}")

    def test_layout_builder_matches(self) -> None:
        for options, js_layout in zip(layout_cases(), self.js["layouts"]):
            py_layout = engine.build_layout(**options)
            self.assertEqual(len(js_layout["lights"]), len(py_layout["lights"]), options["name"])
            self.assertEqual(js_layout["grid"], py_layout["grid"], options["name"])
            for js_entry, py_entry in zip(js_layout["lights"], py_layout["lights"]):
                self.assertEqual(js_entry["entity_id"], py_entry["entity_id"])
                self.assertEqual(js_entry["row"], py_entry["row"])
                self.assertEqual(js_entry["col"], py_entry["col"])
                self.assertAlmostEqual(js_entry["x"], py_entry["x"], delta=1e-4)
                self.assertAlmostEqual(js_entry["y"], py_entry["y"], delta=1e-4)
            for axis in ("width", "height", "padding"):
                self.assertAlmostEqual(js_layout["room"][axis], py_layout["room"][axis], delta=1e-4)

    def test_every_frame_matches(self) -> None:
        self.assertEqual(len(self.js["frames"]), len(self.expected_frames))
        channel_diffs = 0
        channel_total = 0
        worst_value = 0.0
        for case, js_frame, py_frame in zip(self.cases, self.js["frames"], self.expected_frames):
            self.assertEqual(len(js_frame), len(py_frame), case["id"])
            for js_entry, py_entry in zip(js_frame, py_frame):
                where = f"{case['id']} {py_entry['entity_id']}"
                self.assertEqual(js_entry["entity_id"], py_entry["entity_id"], where)
                self.assertAlmostEqual(js_entry["value"], py_entry["value"], delta=VALUE_TOLERANCE, msg=where)
                self.assertAlmostEqual(js_entry["intensity"], py_entry["intensity"], delta=VALUE_TOLERANCE, msg=where)
                self.assertAlmostEqual(js_entry["brightness_pct"], py_entry["brightness_pct"], delta=CHANNEL_TOLERANCE, msg=where)
                for js_channel, py_channel in zip(js_entry["rgb"], py_entry["rgb"]):
                    channel_total += 1
                    if js_channel != py_channel:
                        channel_diffs += 1
                    self.assertAlmostEqual(js_channel, py_channel, delta=CHANNEL_TOLERANCE, msg=where)
                worst_value = max(worst_value, abs(js_entry["value"] - py_entry["value"]))
        self.assertLessEqual(
            channel_diffs / max(1, channel_total), CHANNEL_NOISE_BUDGET,
            f"{channel_diffs}/{channel_total} RGB channels differ by one step",
        )
        print(
            f"\n    parity: {len(self.cases)} frames, "
            f"{channel_total} channels, {channel_diffs} one-step RGB differences, "
            f"worst value delta {worst_value:.3e}"
        )

    def test_frame_count_and_effects_covered(self) -> None:
        effects = {case["effect"] for case in self.cases}
        self.assertEqual(effects, set(engine.EFFECTS))


if __name__ == "__main__":
    unittest.main()
