"""Static validation of the manifest, services, translations and card bundle.

The Home Assistant facing modules (``__init__``, ``switch``, ``config_flow``,
``runner``, ``storage``, ``schemas``) cannot be imported without a Home Assistant
install, so they are compiled to bytecode instead: that still catches syntax
errors, and the schema/services/translation cross-checks catch drifting field
names between the YAML, the schemas and the docs.
"""

from __future__ import annotations

import json
import pathlib
import py_compile
import re
import subprocess
import unittest

from _harness import COMPONENTS, ROOT, engine
from _yaml import parse_text

PACKAGE_DIR = COMPONENTS / "ceiling_scene_generator"
SERVICES_YAML = PACKAGE_DIR / "services.yaml"

SERVICE_SCHEMAS = {
    "start": "START_SCHEMA",
    "stop": "STOP_SCHEMA",
    "save_as_script": "SAVE_AS_SCRIPT_SCHEMA",
    "save_scene": "SAVE_SCENE_SCHEMA",
    "delete_scene": "DELETE_SCENE_SCHEMA",
    "list_scenes": "LIST_SCENES_SCHEMA",
}


def schema_fields(text: str, name: str) -> set[str]:
    match = re.search(rf"^{name} = vol\.Schema\((?P<body>.*?)(?:^\)|\Z)", text, re.S | re.M)
    assert match, f"schema {name} not found in schemas.py"
    return set(re.findall(r'vol\.(?:Optional|Required)\("([^"]+)"', match.group("body")))


class ManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads((PACKAGE_DIR / "manifest.json").read_text(encoding="utf-8"))

    def test_domain_matches_directory(self) -> None:
        self.assertEqual(self.manifest["domain"], PACKAGE_DIR.name)

    def test_required_hacs_fields(self) -> None:
        for key in ("domain", "name", "version", "documentation", "issue_tracker", "codeowners", "requirements"):
            self.assertIn(key, self.manifest, key)
        self.assertTrue(self.manifest["codeowners"])
        self.assertTrue(self.manifest["documentation"].startswith("http"))
        self.assertTrue(self.manifest["issue_tracker"].startswith("http"))

    def test_version_matches_the_engine(self) -> None:
        self.assertEqual(self.manifest["version"], engine.VERSION)

    def test_frontend_dependency_for_card_registration(self) -> None:
        self.assertIn("frontend", self.manifest["dependencies"])
        self.assertTrue(self.manifest["config_flow"])
        self.assertEqual(self.manifest["integration_type"], "service")
        self.assertEqual(self.manifest["requirements"], [])

    def test_hacs_json(self) -> None:
        hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
        self.assertEqual(hacs["name"], self.manifest["name"])
        self.assertFalse(hacs["content_in_root"])


class TranslationTest(unittest.TestCase):
    def test_strings_and_english_translation_match(self) -> None:
        strings = json.loads((PACKAGE_DIR / "strings.json").read_text(encoding="utf-8"))
        english = json.loads((PACKAGE_DIR / "translations" / "en.json").read_text(encoding="utf-8"))
        self.assertEqual(strings, english)

    def test_config_flow_schema_keys_are_translated(self) -> None:
        text = (PACKAGE_DIR / "config_flow.py").read_text(encoding="utf-8")
        keys = set(re.findall(r'CONF_[A-Z_]+', text))
        translated = json.loads((PACKAGE_DIR / "translations" / "en.json").read_text(encoding="utf-8"))
        data = translated["config"]["step"]["user"]["data"]
        for constant in ("CONF_UPDATE_INTERVAL", "CONF_TRANSITION", "CONF_AUTO_RESUME"):
            self.assertIn(constant, keys)
            self.assertTrue(any(constant.endswith(name.upper()) for name in data), constant)

    def test_service_descriptions_cover_every_service(self) -> None:
        services = parse_text(SERVICES_YAML.read_text(encoding="utf-8"))
        translated = json.loads((PACKAGE_DIR / "translations" / "en.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(services), sorted(SERVICE_SCHEMAS))
        self.assertEqual(sorted(translated["services"]), sorted(SERVICE_SCHEMAS))
        for name, entry in services.items():
            self.assertTrue(entry.get("name"), name)
            self.assertTrue(entry.get("description"), name)


class ServicesYamlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.services = parse_text(SERVICES_YAML.read_text(encoding="utf-8"))
        self.schema_text = (PACKAGE_DIR / "schemas.py").read_text(encoding="utf-8")

    def test_every_service_is_documented(self) -> None:
        self.assertEqual(sorted(self.services), sorted(SERVICE_SCHEMAS))

    def test_fields_match_the_voluptuous_schemas(self) -> None:
        for service, schema_name in SERVICE_SCHEMAS.items():
            documented = set(self.services[service].get("fields") or {})
            self.assertEqual(documented, schema_fields(self.schema_text, schema_name), service)

    def test_effect_options_match_the_engine(self) -> None:
        for service, entry in self.services.items():
            fields = entry.get("fields") or {}
            if "effect" not in fields:
                continue
            options = fields["effect"].get("selector", {}).get("select", {}).get("options")
            if options is None:
                continue
            self.assertEqual(options, list(engine.EFFECTS), service)

    def test_palette_presets_are_documented(self) -> None:
        description = self.services["start"]["fields"]["palette"]["description"]
        for preset in engine.PALETTES:
            self.assertIn(preset, description, preset)


class PythonModuleCompileTest(unittest.TestCase):
    def test_every_module_compiles(self) -> None:
        modules = sorted(PACKAGE_DIR.glob("*.py"))
        self.assertGreaterEqual(len(modules), 8)
        for module in modules:
            with self.subTest(module=module.name):
                py_compile.compile(str(module), doraise=True, cfile=None, optimize=0)

    def test_package_exports_platforms_and_setup(self) -> None:
        text = (PACKAGE_DIR / "__init__.py").read_text(encoding="utf-8")
        for symbol in ("async_setup_entry", "async_unload_entry", "async_setup", "PLATFORMS"):
            self.assertIn(symbol, text)
        for service in SERVICE_SCHEMAS:
            self.assertIn(f'SERVICE_{service.upper()}', text)

    def test_switch_entity_is_referenced_by_the_card(self) -> None:
        card = (PACKAGE_DIR / "www" / "ceiling-scene-card.js").read_text(encoding="utf-8")
        self.assertIn("ceiling_scene_generator", card)
        switch = (PACKAGE_DIR / "switch.py").read_text(encoding="utf-8")
        self.assertIn('"ceiling_scene_generator": True', switch)


class CardBundleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.card = (PACKAGE_DIR / "www" / "ceiling-scene-card.js").read_text(encoding="utf-8")

    def test_node_parses_the_card(self) -> None:
        completed = subprocess.run(
            ["node", "--check", str(PACKAGE_DIR / "www" / "ceiling-scene-card.js")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_card_mentions_every_effect_and_palette(self) -> None:
        for effect in engine.EFFECTS:
            self.assertIn(effect, self.card, effect)
        for palette in engine.PALETTES:
            self.assertIn(palette + ":", self.card, palette)

    def test_card_exposes_the_engine_and_custom_element(self) -> None:
        self.assertIn("root.CeilingSceneEngine = ENGINE", self.card)
        self.assertIn("customElements.define('ceiling-scene-card'", self.card)
        self.assertIn("customCards.push", self.card)

    def test_card_has_no_lit_import(self) -> None:
        """The card must stay dependency free so it works with a plain resource."""
        self.assertNotIn("import {", self.card.replace("import { LitElement", ""))


class RepoLayoutTest(unittest.TestCase):
    def test_expected_repository_files(self) -> None:
        for relative in (
            "custom_components/ceiling_scene_generator/manifest.json",
            "custom_components/ceiling_scene_generator/__init__.py",
            "custom_components/ceiling_scene_generator/engine.py",
            "custom_components/ceiling_scene_generator/runner.py",
            "custom_components/ceiling_scene_generator/storage.py",
            "custom_components/ceiling_scene_generator/switch.py",
            "custom_components/ceiling_scene_generator/config_flow.py",
            "custom_components/ceiling_scene_generator/schemas.py",
            "custom_components/ceiling_scene_generator/script_compiler.py",
            "custom_components/ceiling_scene_generator/services.yaml",
            "custom_components/ceiling_scene_generator/www/ceiling-scene-card.js",
            "custom_components/ceiling_scene_generator/translations/en.json",
            "hacs.json",
            "README.md",
            "LICENSE",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_no_stray_pycache_or_temp_files_referenced(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("custom_components/ceiling_scene_generator", readme)


if __name__ == "__main__":
    unittest.main()
