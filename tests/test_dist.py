"""``dist/ceiling-scene-card.js`` must be a faithful copy of the shipped card.

The card is authored inside the integration (Home Assistant serves that path), and
``dist/`` is the standalone copy for people who only want the Lovelace resource.
A stale or hand-edited ``dist/`` file would silently ship a different engine than
the one the Python side is parity-tested against, so it is checked here.
"""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

from _harness import CARD_JS, ROOT

DIST_JS = ROOT / "dist" / "ceiling-scene-card.js"
BUILD_SCRIPT = ROOT / "tools" / "build_dist.py"


def _load_build_module():
    spec = importlib.util.spec_from_file_location("build_dist", BUILD_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDistBundle(unittest.TestCase):
    def setUp(self) -> None:
        self.build = _load_build_module()

    def test_dist_file_exists(self) -> None:
        self.assertTrue(DIST_JS.is_file(), f"missing {DIST_JS} - run `python tools/build_dist.py`")
        self.assertGreater(DIST_JS.stat().st_size, 10000)

    def test_dist_is_the_generated_card(self) -> None:
        expected = self.build.render()
        actual = DIST_JS.read_bytes()
        self.assertEqual(
            len(actual),
            len(expected),
            "dist/ceiling-scene-card.js is stale - run `python tools/build_dist.py`",
        )
        self.assertEqual(actual, expected, "dist/ceiling-scene-card.js is stale or hand-edited")

    def test_dist_keeps_the_engine_and_card_markers(self) -> None:
        text = DIST_JS.read_text(encoding="utf-8")
        for marker in (
            "root.CeilingSceneEngine = ENGINE;",
            "custom:ceiling-scene-card",
            "customElements.define",
            "linear_wave",
            "center_burst",
        ):
            self.assertIn(marker, text)

    def test_dist_contains_the_source_card_verbatim(self) -> None:
        source = CARD_JS.read_text(encoding="utf-8")
        dist = DIST_JS.read_text(encoding="utf-8")
        self.assertTrue(
            dist.endswith(source),
            "dist/ must contain the source card bundle unmodified after its banner",
        )

    def test_check_mode_agrees_with_reality(self) -> None:
        self.assertEqual(self.build.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
