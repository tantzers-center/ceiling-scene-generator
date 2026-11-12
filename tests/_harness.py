"""Import the integration's pure modules without Home Assistant installed.

``engine.py``, ``const.py`` and ``script_compiler.py`` deliberately have no Home
Assistant imports, so they can be tested on a bare Python install.  Importing
``custom_components.ceiling_scene_generator.engine`` normally executes the
package's ``__init__.py`` (which does import Home Assistant), so the package
path is registered manually and ``__init__.py`` is never run.
"""

from __future__ import annotations

import importlib
import pathlib
import sys
import types

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
COMPONENTS = ROOT / "custom_components"
PACKAGE = "ceiling_scene_generator"
QUALIFIED = f"custom_components.{PACKAGE}"
CARD_JS = COMPONENTS / PACKAGE / "www" / "ceiling-scene-card.js"


def _bootstrap() -> None:
    if "custom_components" in sys.modules:
        return
    parent = types.ModuleType("custom_components")
    parent.__path__ = [str(COMPONENTS)]
    sys.modules["custom_components"] = parent
    package = types.ModuleType(QUALIFIED)
    package.__path__ = [str(COMPONENTS / PACKAGE)]
    sys.modules[QUALIFIED] = package


_bootstrap()

engine = importlib.import_module(f"{QUALIFIED}.engine")
const = importlib.import_module(f"{QUALIFIED}.const")
script_compiler = importlib.import_module(f"{QUALIFIED}.script_compiler")
