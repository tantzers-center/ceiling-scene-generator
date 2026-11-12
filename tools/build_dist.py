#!/usr/bin/env python
"""Publish ``dist/ceiling-scene-card.js``.

The Lovelace card is authored once, at
``custom_components/ceiling_scene_generator/www/ceiling-scene-card.js``, because
Home Assistant serves that path directly and the integration can therefore
register itself as a Lovelace resource with no extra copying.

``dist/ceiling-scene-card.js`` is the same file published at the repository root
for people who only want the card (drop it in ``config/www/`` and add
``/local/ceiling-scene-card.js`` as a JavaScript module resource).  It is a
generated copy, never a second source of truth:

    python tools/build_dist.py            # regenerate
    python tools/build_dist.py --check    # fail if dist/ is stale (CI)

``tests/test_dist.py`` asserts the two files stay byte-identical.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "custom_components" / "ceiling_scene_generator" / "www" / "ceiling-scene-card.js"
TARGET = ROOT / "dist" / "ceiling-scene-card.js"

BANNER = """/*!
 * dist/ceiling-scene-card.js - build artefact, do not edit.
 *
 * Source of truth: custom_components/ceiling_scene_generator/www/ceiling-scene-card.js
 * Regenerate with: python tools/build_dist.py
 *
 * Standalone install: copy this file to config/www/ceiling-scene-card.js and add
 * /local/ceiling-scene-card.js as a JavaScript module under
 * Settings -> Dashboards -> Resources.
 */
"""


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render() -> bytes:
    if not SOURCE.is_file():
        raise SystemExit(f"card bundle missing: {SOURCE}")
    body = SOURCE.read_text(encoding="utf-8")
    return (BANNER + body).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail instead of writing when dist/ is stale")
    args = parser.parse_args(argv)

    payload = render()
    if args.check:
        if not TARGET.is_file():
            print(f"dist is missing: {TARGET}", file=sys.stderr)
            return 1
        if TARGET.read_bytes() != payload:
            print(
                f"dist/ceiling-scene-card.js is stale - run `python tools/build_dist.py`\n"
                f"  source sha256: {hashlib.sha256(render()).hexdigest()}\n"
                f"  dist   sha256: {digest(TARGET)}",
                file=sys.stderr,
            )
            return 1
        print(f"dist/ceiling-scene-card.js is current ({len(payload)} bytes)")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(payload)
    print(f"wrote {TARGET} ({len(payload)} bytes, sha256 {digest(TARGET)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
