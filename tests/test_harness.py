"""The browser harness must actually load the card.

``tests/harness/*.html`` references the shipped card bundle by relative path.  A
wrong depth (``../`` instead of ``../../``) silently 404s the script, the page
still renders, and every check inside it dies with ``card.setConfig is not a
function`` - which is exactly how a working card gets blamed for being broken.
These tests resolve every relative reference in the harness against the file
system so the harness cannot rot unnoticed.
"""

from __future__ import annotations

import pathlib
import re
import unittest
from html.parser import HTMLParser

from _harness import ROOT

HARNESS_DIR = ROOT / "tests" / "harness"


class _RefCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        mapping = {"script": "src", "link": "href", "img": "src"}
        attribute = mapping.get(tag)
        if not attribute:
            return
        for name, value in attrs:
            if name == attribute and value:
                self.refs.append((tag, value))


def _collect(path: pathlib.Path) -> list[tuple[str, str]]:
    parser = _RefCollector()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.refs


class TestBrowserHarness(unittest.TestCase):
    def test_harness_exists(self) -> None:
        self.assertTrue((HARNESS_DIR / "card-preview.html").is_file())

    def test_every_relative_reference_resolves(self) -> None:
        for html in sorted(HARNESS_DIR.glob("*.html")):
            for tag, ref in _collect(html):
                if re.match(r"^(https?:|data:|#|/)", ref):
                    continue
                target = (html.parent / ref).resolve()
                self.assertTrue(
                    target.is_file(),
                    f"{html.name}: <{tag} {ref}> resolves to {target}, which does not exist",
                )

    def test_harness_loads_the_shipped_card_bundle(self) -> None:
        refs = dict((tag, ref) for tag, ref in _collect(HARNESS_DIR / "card-preview.html"))
        card_ref = refs.get("script")
        if card_ref is None:
            self.fail("card-preview.html does not load the card bundle")
        resolved = (HARNESS_DIR / card_ref).resolve()
        shipped = (ROOT / "custom_components" / "ceiling_scene_generator" / "www" / "ceiling-scene-card.js").resolve()
        self.assertEqual(
            resolved,
            shipped,
            "the harness must load the real bundle from the integration, not a copy",
        )

    def test_harness_stubs_hass_and_exposes_itself(self) -> None:
        text = (HARNESS_DIR / "card-preview.html").read_text(encoding="utf-8")
        for marker in ("window.__errors", "ceiling-scene-card", "callService", "window.__harness"):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
