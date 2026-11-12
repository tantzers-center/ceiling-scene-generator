"""YAML validation helper: parses YAML with the real `yaml` npm parser.

Home Assistant reads its configuration with PyYAML, so checking the emitted
scripts/services files with a real parser catches quoting or indentation mistakes
that a hand rolled reader could miss.  The parser lives in ``tools/node_modules``
(``npm install --prefix tools``); the tests skip themselves when Node or the
parser is unavailable instead of failing.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
VALIDATOR = ROOT / "tools" / "check_yaml.js"
SCRATCH = pathlib.Path(os.environ.get("TMPDIR") or tempfile.gettempdir())

NODE = shutil.which("node")


def available() -> bool:
    if NODE is None:
        return False
    try:
        return _run(_write_scratch("probe: 1\n")) is not None
    except AssertionError:
        return False


def _write_scratch(text: str) -> pathlib.Path:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, dir=str(SCRATCH), encoding="utf-8"
    )
    handle.write(text)
    handle.close()
    return pathlib.Path(handle.name)


def _run(path: pathlib.Path) -> dict | None:
    completed = subprocess.run(
        [NODE, str(VALIDATOR), str(path)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if completed.returncode == 3:  # parser not installed
        return None
    if completed.returncode != 0:
        raise AssertionError(f"invalid YAML ({path}): {completed.stderr.strip()}")
    return json.loads(completed.stdout or "null")


def parse_text(text: str) -> dict:
    """Parse a YAML document, skipping the test when the parser is missing."""
    if NODE is None:
        raise unittest.SkipTest("node is not installed")
    path = _write_scratch(text)
    try:
        parsed = _run(path)
    finally:
        path.unlink(missing_ok=True)
    if parsed is None:
        raise unittest.SkipTest("run `npm install --prefix tools` to enable YAML validation")
    return parsed


def parse_file(path: str | pathlib.Path) -> dict:
    return parse_text(pathlib.Path(path).read_text(encoding="utf-8"))
