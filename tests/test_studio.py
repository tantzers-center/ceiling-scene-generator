"""The generated standalone studio and the build tool that produces it.

``tools/build_studio.py`` extracts the effect engine from the card bundle and
inlines the whole integration, so the two things worth guarding are:

* the embedded engine block is *byte identical* to the one in the card bundle
  (otherwise the studio could silently drift from what the lights do), and
* the generated document really does carry the integration files verbatim, so
  the Files tab can hand them to someone who has never seen the repository.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
TOOLS = ROOT / "tools"
STUDIO = ROOT / "studio" / "ceiling-scene-studio.html"
BUILDER = TOOLS / "build_studio.py"
CARD = ROOT / "custom_components" / "ceiling_scene_generator" / "www" / "ceiling-scene-card.js"

sys.path.insert(0, str(TOOLS))
import build_studio  # noqa: E402  (imported after the path tweak on purpose)

from _harness import engine  # noqa: E402

NODE = shutil.which("node")
SCRATCH = pathlib.Path(os.environ.get("TMPDIR") or tempfile.gettempdir())

VERBATIM_FILES = (
    "custom_components/ceiling_scene_generator/manifest.json",
    "custom_components/ceiling_scene_generator/services.yaml",
    "custom_components/ceiling_scene_generator/engine.py",
)


def _read(path: pathlib.Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


class StudioFileTest(unittest.TestCase):
    """What the committed studio file must contain."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = _read(STUDIO)

    def test_studio_exists_and_is_non_empty(self) -> None:
        self.assertTrue(STUDIO.is_file())
        self.assertGreater(STUDIO.stat().st_size, 50_000)

    def test_is_offline_and_self_contained(self) -> None:
        lowered = self.html.lower()
        # No external resource loading at all: no <script src>, no <link>, no
        # CSS @import, no CDN.  (The inlined repo files legitimately contain
        # documentation URLs, so only resource *loading* is forbidden.)
        for forbidden in ("<script src", "<link", "@import", "cdn.", "require("):
            self.assertNotIn(forbidden, lowered, forbidden)
        # the font must degrade to a system fallback, never a webfont download
        self.assertIn("Plus Jakarta Sans", self.html)
        self.assertIn("system-ui", self.html)

    def test_embedded_engine_is_byte_identical_to_the_card_bundle(self) -> None:
        expected = build_studio.extract_engine(_read(CARD))
        embedded = build_studio.extract_embedded_engine(self.html)
        self.assertEqual(embedded, expected)
        self.assertIn("root.CeilingSceneEngine = ENGINE;", embedded)

    def test_engine_version_matches_the_card_and_engine_py(self) -> None:
        card_version = re.search(r"var VERSION = '([^']+)'", _read(CARD)).group(1)
        embedded = build_studio.extract_embedded_engine(self.html)
        studio_version = re.search(r"var VERSION = '([^']+)'", embedded).group(1)
        self.assertEqual(studio_version, card_version)
        self.assertEqual(studio_version, engine.VERSION)

    def test_mentions_every_effect_and_palette(self) -> None:
        for effect in engine.EFFECTS:
            self.assertIn(effect, self.html, effect)
        for preset in engine.PALETTES.values():
            self.assertIn(preset["name"], self.html, preset["name"])

    def test_exposes_the_three_export_paths(self) -> None:
        # (a) service call  (b) card config  (c) scene JSON
        self.assertIn("service: ceiling_scene_generator.start", self.html)
        self.assertIn("type: custom:ceiling-scene-card", self.html)
        self.assertIn("function sceneJson", self.html)
        self.assertIn("var EXPORTS = {", self.html)
        for anchor in ("build: serviceCallYaml", "build: cardYaml", "build: sceneJson"):
            self.assertIn(anchor, self.html, anchor)

    def test_files_tab_is_wired_up(self) -> None:
        self.assertIn("panelFiles", self.html)
        self.assertIn("csg-filestore", self.html)
        self.assertIn("data-csg-file", self.html)
        self.assertIn("Blob", self.html)
        self.assertIn("download", self.html)

    def test_every_inlined_path_and_size_is_embedded(self) -> None:
        html = self.html
        for relative, size, _ in build_studio.collect_files():
            tag = f'data-csg-file="{relative}" data-csg-size="{size}"'
            self.assertIn(tag, html, relative)
        blocks = re.findall(r'<script type="text/plain" data-csg-file="([^"]+)"', html)
        self.assertEqual(len(blocks), len(build_studio.INLINE_FILES))
        self.assertEqual(sorted(blocks), sorted(build_studio.INLINE_FILES))

    def test_integration_files_are_inlined_verbatim(self) -> None:
        for relative in VERBATIM_FILES:
            text = _read(ROOT / relative)
            self.assertIn(text, self.html, f"{relative} is not present verbatim")
            embedded = re.search(
                r'<script type="text/plain" data-csg-file="' + re.escape(relative) + r'"[^>]*>(.*?)</script>',
                self.html, re.S,
            )
            self.assertIsNotNone(embedded, relative)
            self.assertEqual(embedded.group(1), text, relative)

    def test_install_instructions_cover_the_required_steps(self) -> None:
        # HACS / manual copy, restart, add integration, card resource + /local/.
        self.assertIn("Custom repositories", self.html)
        self.assertIn("Integration", self.html)
        self.assertIn("custom_components/ceiling_scene_generator", self.html)
        self.assertIn("Restart Home Assistant", self.html)
        self.assertIn("restart", self.html.lower())
        self.assertIn("Add integration", self.html)
        self.assertIn("Ceiling Scene Generator", self.html)
        self.assertIn("/ceiling_scene_generator/ceiling-scene-card.js", self.html)
        self.assertIn("dist/ceiling-scene-card.js", self.html)
        self.assertIn("/local/ceiling-scene-card.js", self.html)

    def test_committed_file_matches_a_fresh_build(self) -> None:
        fresh = build_studio.build_studio_html().encode("utf-8")
        self.assertEqual(STUDIO.read_bytes(), fresh)


@unittest.skipIf(NODE is None, "node is required to check the studio's inline script")
class StudioScriptTest(unittest.TestCase):
    def test_node_check_accepts_the_inline_script(self) -> None:
        html = _read(STUDIO)
        script = build_studio.extract_studio_script(html)
        SCRATCH.mkdir(parents=True, exist_ok=True)
        target = SCRATCH / "csg-studio-inline-check.js"
        target.write_text(script, encoding="utf-8", newline="\n")
        try:
            completed = subprocess.run(
                [NODE, "--check", str(target)], capture_output=True, text=True, timeout=90,
            )
        finally:
            target.unlink(missing_ok=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)


class BuildToolTest(unittest.TestCase):
    """The generator itself: deterministic and fail-loud."""

    def _run_build(self) -> str:
        completed = subprocess.run(
            [sys.executable, str(BUILDER)], cwd=str(ROOT),
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout

    def test_build_is_idempotent(self) -> None:
        self._run_build()
        first = hashlib.sha256(STUDIO.read_bytes()).hexdigest()
        self._run_build()
        second = hashlib.sha256(STUDIO.read_bytes()).hexdigest()
        self.assertEqual(first, second, "two builds produced different bytes")

    def test_build_reports_the_output_hash(self) -> None:
        output = self._run_build()
        digest = hashlib.sha256(STUDIO.read_bytes()).hexdigest()
        self.assertIn(digest, output)

    def test_missing_markers_abort_with_a_clear_error(self) -> None:
        with self.assertRaises(build_studio.StudioBuildError):
            build_studio.extract_engine("nothing to see here\n")
        with self.assertRaises(build_studio.StudioBuildError):
            # start + end present but no export line -> must still abort
            build_studio.extract_engine(
                "Effect engine (mirror of engine.py)\n"
                "  var ENGINE = (function () {\n    return {};\n  })();\n"
            )

    def test_missing_inline_file_aborts(self) -> None:
        files = build_studio.collect_files()
        self.assertEqual(len(files), len(build_studio.INLINE_FILES))
        # a path that does not exist must raise rather than silently skip
        original = build_studio.INLINE_FILES
        try:
            build_studio.INLINE_FILES = original + ("does/not/exist.py",)
            with self.assertRaises(build_studio.StudioBuildError):
                build_studio.collect_files()
        finally:
            build_studio.INLINE_FILES = original


if __name__ == "__main__":
    unittest.main()
