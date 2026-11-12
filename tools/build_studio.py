#!/usr/bin/env python
"""Generate ``studio/ceiling-scene-studio.html`` from the shared card bundle.

The standalone studio is a single, fully self contained HTML file: it has to work
when it is opened straight from disk (``file://``) with no server, no CDN and no
build tooling at run time.  So instead of shipping a second copy of the effect
engine, this generator *extracts* the engine block from
``www/ceiling-scene-card.js`` (the canonical JavaScript mirror of ``engine.py``)
and inlines it verbatim.  The studio can therefore never drift from the engine
the Lovelace card uses, and ``tests/test_studio.py`` proves the embedded block is
byte identical to the one in the card bundle.

It also inlines the whole installable integration (see ``INLINE_FILES``) so the
studio can reproduce the repository for someone who has never seen it.

Run::

    python tools/build_studio.py

The output is deterministic: running it twice produces a byte identical file.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "custom_components" / "ceiling_scene_generator"
CARD = PACKAGE / "www" / "ceiling-scene-card.js"
OUTPUT = ROOT / "studio" / "ceiling-scene-studio.html"

# --------------------------------------------------------------------------- #
# Markers used to locate the engine block inside the card bundle.  The generator
# never hardcodes line numbers: it searches for these substrings, so the card
# can grow without silently breaking the studio.
# --------------------------------------------------------------------------- #

SECTION_MARKER = "Effect engine (mirror of engine.py)"
ENGINE_START_MARKER = "var ENGINE = (function () {"
ENGINE_END_MARKER = "root.CeilingSceneEngine = ENGINE;"
# The extracted text must prove it actually contains the export line.
ENGINE_SENTINEL = "root.CeilingSceneEngine = ENGINE;"

# Markers emitted into the generated HTML so tests can pull the engine block
# back out again.
ENGINE_BEGIN_BANNER = "/* ==== BEGIN ENGINE"
ENGINE_END_BANNER = "/* ==== END ENGINE"

STUDIO_SCRIPT_ID = "csg-studio"
FILESTORE_ATTR = "data-csg-file"

# --------------------------------------------------------------------------- #
# The installable integration, inlined verbatim into the studio.
#
# Table driven on purpose: adding a file is one line.  Paths are relative to the
# repository root and are used both as the download file name and as the key the
# UI reads the payload from.
# --------------------------------------------------------------------------- #

INLINE_FILES: tuple[str, ...] = (
    "custom_components/ceiling_scene_generator/manifest.json",
    "custom_components/ceiling_scene_generator/__init__.py",
    "custom_components/ceiling_scene_generator/config_flow.py",
    "custom_components/ceiling_scene_generator/const.py",
    "custom_components/ceiling_scene_generator/engine.py",
    "custom_components/ceiling_scene_generator/runner.py",
    "custom_components/ceiling_scene_generator/schemas.py",
    "custom_components/ceiling_scene_generator/script_compiler.py",
    "custom_components/ceiling_scene_generator/services.yaml",
    "custom_components/ceiling_scene_generator/storage.py",
    "custom_components/ceiling_scene_generator/strings.json",
    "custom_components/ceiling_scene_generator/switch.py",
    "custom_components/ceiling_scene_generator/translations/en.json",
    "custom_components/ceiling_scene_generator/www/ceiling-scene-card.js",
    "hacs.json",
    "README.md",
    "LICENSE",
)


class StudioBuildError(RuntimeError):
    """Raised when the studio cannot be generated safely."""


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #

def _find(lines: list[str], needle: str, start: int = 0) -> int:
    for index in range(start, len(lines)):
        if needle in lines[index]:
            return index
    return -1


def extract_engine(card_text: str) -> str:
    """Return the engine block from ``card_text`` (verbatim, no reformatting).

    The block runs from the ``var ENGINE = (function () {`` line through the
    ``root.CeilingSceneEngine = ENGINE;`` line, so the caller gets the engine
    object *and* the export that publishes it.
    """
    lines = card_text.splitlines()
    section = _find(lines, SECTION_MARKER)
    start = _find(lines, ENGINE_START_MARKER)
    end = _find(lines, ENGINE_END_MARKER, start if start >= 0 else 0)
    if section < 0:
        raise StudioBuildError(
            f"card bundle is missing the section marker {SECTION_MARKER!r}; "
            "cannot locate the engine block"
        )
    if start < 0:
        raise StudioBuildError(
            f"card bundle is missing the start marker {ENGINE_START_MARKER!r}; "
            "cannot locate the engine block"
        )
    if end < 0:
        raise StudioBuildError(
            f"card bundle is missing the end marker {ENGINE_END_MARKER!r}; "
            "cannot locate the engine block"
        )
    if not (section < start < end):
        raise StudioBuildError(
            "engine markers are out of order in the card bundle "
            f"(section={section}, start={start}, end={end})"
        )
    block = "\n".join(lines[start:end + 1])
    if ENGINE_SENTINEL not in block:
        raise StudioBuildError(
            f"extracted engine block does not contain {ENGINE_SENTINEL!r}; "
            "refusing to write a studio without the engine export"
        )
    return block


def extract_embedded_engine(html: str) -> str:
    """Pull the engine block back out of a generated studio document."""
    pattern = (
        re.escape(ENGINE_BEGIN_BANNER) + r"[^\n]*\n(.*?)\n[ \t]*" + re.escape(ENGINE_END_BANNER)
    )
    match = re.search(pattern, html, re.S)
    if not match:
        raise StudioBuildError("generated studio is missing the engine begin/end banners")
    return match.group(1)


def extract_studio_script(html: str) -> str:
    """Return the executable inline script (the one ``node --check`` validates)."""
    pattern = r'<script id="' + STUDIO_SCRIPT_ID + r'">(.*?)</script>'
    match = re.search(pattern, html, re.S)
    if not match:
        raise StudioBuildError(f"generated studio has no <script id={STUDIO_SCRIPT_ID!r}> block")
    return match.group(1)


def read_card() -> str:
    if not CARD.is_file():
        raise StudioBuildError(f"card bundle not found: {CARD}")
    return CARD.read_text(encoding="utf-8")


def collect_files() -> list[tuple[str, int, str]]:
    """Read every inline file from disk: (relative path, byte size, text)."""
    collected: list[tuple[str, int, str]] = []
    for relative in INLINE_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise StudioBuildError(f"cannot inline missing file: {relative}")
        text = path.read_text(encoding="utf-8")
        if re.search(r"</script", text, re.I):
            raise StudioBuildError(
                f"{relative} contains a literal </script sequence; "
                "it cannot be embedded in a <script type=text/plain> block verbatim"
            )
        collected.append((relative, len(text.encode("utf-8")), text))
    return collected


# --------------------------------------------------------------------------- #
# Document assembly
# --------------------------------------------------------------------------- #

def _files_store(files: list[tuple[str, int, str]]) -> str:
    chunks: list[str] = []
    for relative, size, text in files:
        chunks.append(
            f'<script type="text/plain" {FILESTORE_ATTR}="{relative}" '
            f'data-csg-size="{size}">{text}</script>'
        )
    return "\n".join(chunks)


def _files_manifest(files: list[tuple[str, int, str]]) -> str:
    entries = ",\n  ".join(
        "{path: %s, size: %d}" % (json.dumps(relative), size) for relative, size, _ in files
    )
    return "var CSG_FILES = [\n  " + entries + "\n];"


def build_document(card_text: str, files: list[tuple[str, int, str]] | None = None) -> str:
    """Assemble the whole studio document.  Deterministic given the inputs."""
    engine = extract_engine(card_text)
    if files is None:
        files = collect_files()
    html = TEMPLATE
    html = html.replace("@@ENGINE@@", engine)
    html = html.replace("@@CSG_FILES@@", _files_manifest(files))
    html = html.replace("@@FILESTORE@@", _files_store(files))
    return html


def build_studio_html() -> str:
    return build_document(read_card())


def write_studio(path: pathlib.Path | None = None) -> pathlib.Path:
    target = path or OUTPUT
    html = build_studio_html()
    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" pins the line endings so two runs are byte identical on
    # Windows and on POSIX.
    target.write_text(html, encoding="utf-8", newline="\n")
    return target


def sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# The template.  Raw string: the embedded JavaScript relies on literal ``\n``
# escapes and must not be touched by Python's own escape processing.
# --------------------------------------------------------------------------- #

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ceiling Scene Studio - Ceiling Scene Generator</title>
<style>
  :root{
    --bg:#0F172A; --panel:#1E293B; --panel-2:#0B1120; --accent:#38BDF8;
    --line:#64748B; --text:#E2E8F0; --muted:#94A3B8; --danger:#FCA5A5;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%}
  body{
    background:var(--bg); color:var(--text); font-size:13px; line-height:1.45;
    font-family:"Plus Jakarta Sans","Segoe UI",system-ui,-apple-system,"Helvetica Neue",sans-serif;
    -webkit-font-smoothing:antialiased;
  }
  .mono{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
    font-variant-numeric:tabular-nums}
  .app{max-width:1500px;margin:0 auto;padding:16px 18px 40px}
  .top{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:14px}
  .brand h1{margin:0;font-size:19px;font-weight:700;letter-spacing:.2px}
  .brand p{margin:2px 0 0}
  .sub{font-size:11.5px;color:var(--muted)}
  .topActions{margin-left:auto;display:flex;align-items:center;gap:9px}
  .chip{display:inline-flex;align-items:center;gap:6px;font-size:11px;padding:3px 10px;
    border-radius:999px;border:1px solid var(--line);color:var(--muted)}
  .chip .dot{width:7px;height:7px;border-radius:50%;background:var(--accent)}
  .grid{display:grid;grid-template-columns:minmax(360px,1fr) minmax(380px,520px);gap:16px;align-items:start}
  @media (max-width:1000px){.grid{grid-template-columns:1fr}}
  .stage{position:sticky;top:16px}
  .stageHead{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
  .hint{font-size:11px;color:var(--muted);line-height:1.5}
  canvas{width:100%;display:block;border-radius:12px;background:var(--panel-2);
    border:1px solid var(--line);touch-action:none;cursor:crosshair}
  .hud{margin-top:8px;font-size:11.5px;color:var(--muted)}
  .side{min-width:0}
  .tabs{display:flex;gap:6px;margin:0 0 10px;flex-wrap:wrap}
  .tab{font-size:12px;padding:5px 12px;border-radius:999px;border:1px solid var(--line);
    background:transparent;color:var(--muted);cursor:pointer}
  .tab.active{background:var(--panel);color:var(--text);border-color:var(--accent)}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:12px;margin-bottom:10px}
  .panel h4{margin:0 0 9px;font-size:12px;letter-spacing:.4px;text-transform:uppercase;
    color:var(--muted);font-weight:600}
  .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
  .row:last-child{margin-bottom:0}
  .field{display:flex;flex-direction:column;gap:3px;min-width:74px}
  .field label{font-size:10px;color:var(--muted);letter-spacing:.3px;text-transform:uppercase}
  input,select{font:inherit;font-size:12px;color:var(--text);background:var(--panel-2);
    border:1px solid var(--line);border-radius:8px;padding:5px 7px;min-width:0}
  input[type=range]{padding:0;background:transparent;border:0;width:100%;accent-color:var(--accent)}
  input[type=color]{width:38px;height:28px;padding:0;border-radius:7px;background:transparent}
  button{font:inherit;font-size:12px;cursor:pointer;color:var(--text);background:var(--panel-2);
    border:1px solid var(--line);border-radius:9px;padding:6px 11px;
    transition:border-color .15s,background .15s}
  button:hover{border-color:var(--accent)}
  button.primary{background:var(--accent);border-color:var(--accent);color:#06121F;font-weight:700}
  button.danger{border-color:#7F1D1D;color:var(--danger)}
  button.small{padding:4px 8px;font-size:11px}
  .range{display:flex;align-items:center;gap:9px;margin-bottom:7px}
  .range .name{font-size:11px;color:var(--muted);width:130px;flex:0 0 auto}
  .range .val{font-size:11px;width:78px;text-align:right;flex:0 0 auto}
  .grid-effects{display:grid;grid-template-columns:repeat(auto-fill,minmax(168px,1fr));gap:7px}
  .effect{text-align:left;padding:8px 9px;border-radius:10px;background:var(--panel-2);
    border:1px solid var(--line)}
  .effect.active{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}
  .effect b{display:block;font-size:12px;font-weight:600;margin-bottom:3px}
  .effect em{font-style:normal;font-size:9.5px;color:var(--muted);line-height:1.35;
    display:block;word-break:break-word}
  .swatches{display:flex;gap:7px;flex-wrap:wrap}
  .swatch{width:74px;padding:5px;border-radius:9px;background:var(--panel-2);
    border:1px solid var(--line);cursor:pointer}
  .swatch.active{border-color:var(--accent)}
  .swatch .bar{height:16px;border-radius:6px;margin-bottom:4px}
  .swatch span{font-size:10px;color:var(--muted)}
  .stop{display:flex;align-items:center;gap:7px;margin-bottom:6px}
  .stop input.hex{width:96px;text-transform:uppercase}
  .ramp{width:100%;height:26px;border-radius:8px;border:1px solid var(--line);display:block;
    background:var(--panel-2)}
  pre{background:var(--panel-2);border:1px solid var(--line);border-radius:10px;padding:10px;
    max-height:270px;overflow:auto;font-size:11px;white-space:pre;margin:0}
  .chk{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);cursor:pointer}
  .chk input{width:14px;height:14px;accent-color:var(--accent)}
  .filelist{display:flex;flex-direction:column;gap:6px}
  .filerow{display:flex;align-items:center;gap:10px;padding:7px 9px;border-radius:9px;
    background:var(--panel-2);border:1px solid var(--line)}
  .filemeta{min-width:0;flex:1 1 auto;display:flex;flex-direction:column;gap:1px}
  .fpath{font-size:11px;word-break:break-all;color:var(--text)}
  .fsize{font-size:10px;color:var(--muted)}
  .fileactions{display:flex;gap:6px;flex:0 0 auto}
  ol.steps{margin:0;padding-left:20px;font-size:12px;color:var(--text)}
  ol.steps li{margin-bottom:8px}
  code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;background:var(--panel-2);
    border:1px solid var(--line);border-radius:5px;padding:1px 5px}
  .status{font-size:11.5px;color:var(--muted);margin-top:8px;min-height:15px}
  .legend{display:flex;gap:12px;flex-wrap:wrap;font-size:10.5px;color:var(--muted);margin-top:7px}
</style>
</head>
<body>
<div class="app">
  <header class="top">
    <div class="brand">
      <h1>Ceiling Scene Studio</h1>
      <p class="sub mono" id="sceneSummary">loading...</p>
    </div>
    <div class="topActions">
      <span class="chip" id="engineChip"><span class="dot"></span><span>engine</span></span>
      <button id="playBtn">Pause</button>
    </div>
  </header>
  <main class="grid">
    <section class="stage">
      <div class="stageHead">
        <span class="hint mono">drag a fixture to move it &middot; shift = fine adjust &middot; Add light then click empty space</span>
      </div>
      <canvas id="canvas" height="320"></canvas>
      <div class="hud mono" id="hud">live preview</div>
      <div class="legend">
        <span class="mono">10 effects</span>
        <span class="mono">8 palettes</span>
        <span class="mono">offline &middot; file:// ready</span>
      </div>
    </section>
    <aside class="side">
      <nav class="tabs" id="tabs"></nav>
      <div id="panel"></div>
      <div class="status" id="status"></div>
    </aside>
  </main>
</div>

<script id="csg-studio">
var root = (typeof globalThis !== "undefined") ? globalThis : this;
/* ==== BEGIN ENGINE (generated by tools/build_studio.py from www/ceiling-scene-card.js - do not edit) ==== */
@@ENGINE@@
/* ==== END ENGINE ==== */
@@CSG_FILES@@

(function () {
  'use strict';
  var E = root.CeilingSceneEngine;
  var DOMAIN = 'ceiling_scene_generator';

  /* --------------------------------------------------------------- helpers */

  function h(tag, attrs) {
    var node = document.createElement(tag);
    if (attrs) {
      for (var key in attrs) {
        var value = attrs[key];
        if (value === null || value === undefined || value === false) continue;
        if (key === 'class') node.className = value;
        else if (key === 'text') node.textContent = value;
        else if (key === 'html') node.innerHTML = value;
        else if (key.slice(0, 2) === 'on') node.addEventListener(key.slice(2).toLowerCase(), value);
        else if (value === true) node.setAttribute(key, '');
        else node.setAttribute(key, value);
      }
    }
    for (var i = 2; i < arguments.length; i++) {
      var child = arguments[i];
      var list = Array.isArray(child) ? child : [child];
      for (var j = 0; j < list.length; j++) {
        var item = list[j];
        if (item === null || item === undefined || item === false) continue;
        node.appendChild(item instanceof Node ? item : document.createTextNode(String(item)));
      }
    }
    return node;
  }

  function fmt(value, decimals) {
    var number = Number(value);
    if (isNaN(number)) return '0';
    return number.toFixed(decimals === undefined ? 2 : decimals);
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    return (bytes / 1024).toFixed(1) + ' KB (' + bytes + ' B)';
  }

  /* ----------------------------------------------------------------- state */

  var state = {
    scene: E.buildLayout({ rows: 3, cols: 4, mode: 'grid', width: 6, height: 4.5, padding: 0.5, name: 'Ceiling' }),
    effect: 'linear_wave',
    params: Object.assign({}, E.DEFAULT_PARAMS),
    palette: E.PALETTES[E.DEFAULT_PALETTE].colors.slice(),
    title: 'Ceiling Scene',
    updateInterval: E.DEFAULT_UPDATE_INTERVAL,
    transition: E.DEFAULT_TRANSITION,
    gridForm: { rows: 3, cols: 4, mode: 'grid' },
    prefix: 'ceiling_can',
    snap: true,
    labels: true,
    selected: null,
    addMode: false,
    playing: true,
    t0: 0,
    frozenT: 0,
    tab: 'layout',
    previewKind: 'service'
  };

  /* --------------------------------------------------------- payload/export */

  function scenePayload() {
    return {
      name: (state.scene.name || 'Ceiling'),
      room: Object.assign({}, state.scene.room),
      grid: Object.assign({}, state.scene.grid),
      lights: (state.scene.lights || []).map(function (light) {
        return {
          entity_id: light.entity_id,
          x: Number(light.x), y: Number(light.y),
          row: light.row | 0, col: light.col | 0
        };
      })
    };
  }

  function paramsPayload() {
    var out = {};
    var source = E.resolveParams(state.params);
    Object.keys(source).forEach(function (key) {
      var value = source[key];
      out[key] = Math.abs(value - Math.round(value)) < 1e-9 ? Math.round(value) : Number(value.toFixed(4));
    });
    return out;
  }

  /* (a) the live-generator service call - same shape as the card's _serviceCallYaml */
  function serviceCallYaml() {
    var lines = ['service: ceiling_scene_generator.start', 'data:'];
    lines.push('  name: ' + JSON.stringify(state.scene.name || 'Ceiling'));
    lines.push('  effect: ' + state.effect);
    lines.push('  palette: [' + state.palette.join(', ') + ']');
    lines.push('  update_interval: ' + fmt(state.updateInterval, 2));
    lines.push('  transition: ' + fmt(state.transition, 2));
    lines.push('  params:');
    var params = paramsPayload();
    Object.keys(params).sort().forEach(function (key) {
      lines.push('    ' + key + ': ' + params[key]);
    });
    lines.push('  scene:');
    var scene = scenePayload();
    lines.push('    name: ' + JSON.stringify(scene.name));
    lines.push('    room: {width: ' + scene.room.width + ', height: ' + scene.room.height + ', padding: ' + scene.room.padding + '}');
    lines.push('    grid: {mode: ' + (scene.grid && scene.grid.mode) + ', rows: ' + (scene.grid && scene.grid.rows) + ', cols: ' + (scene.grid && scene.grid.cols) + '}');
    lines.push('    lights:');
    scene.lights.forEach(function (light) {
      lines.push('      - entity_id: ' + light.entity_id);
      lines.push('        x: ' + light.x + ', y: ' + light.y + ', row: ' + light.row + ', col: ' + light.col);
    });
    return lines.join('\n');
  }

  /* (b) the Lovelace card config - same shape as the card's _cardYaml */
  function cardYaml() {
    var scene = scenePayload();
    return [
      'type: custom:ceiling-scene-card',
      'title: ' + JSON.stringify(state.title || 'Ceiling Scene'),
      'effect: ' + state.effect,
      'palette: [' + state.palette.join(', ') + ']',
      'update_interval: ' + fmt(state.updateInterval, 2),
      'transition: ' + fmt(state.transition, 2),
      '# scene: paste the layout exported below (or use Save scene + start by name)',
      'scene:',
      '  name: ' + JSON.stringify(state.scene.name || 'Ceiling'),
      '  room: {width: ' + scene.room.width + ', height: ' + scene.room.height + ', padding: ' + scene.room.padding + '}',
      '  grid: {mode: ' + scene.grid.mode + ', rows: ' + scene.grid.rows + ', cols: ' + scene.grid.cols + '}',
      '  lights:',
      scene.lights.map(function (light) {
        return '    - {entity_id: ' + light.entity_id + ', x: ' + light.x + ', y: ' + light.y + ', row: ' + light.row + ', col: ' + light.col + '}';
      }).join('\n')
    ].join('\n');
  }

  /* (c) the scene JSON - exactly the dict shape the services accept under scene: */
  function sceneJson() {
    return JSON.stringify({
      name: state.scene.name || 'Ceiling',
      scene: scenePayload(),
      effect: state.effect,
      params: paramsPayload(),
      palette: state.palette.slice(),
      update_interval: Number(state.updateInterval),
      transition: Number(state.transition)
    }, null, 2);
  }

  var EXPORTS = {
    service: { name: 'service call YAML', file: 'ceiling-scene-service-call.yaml', build: serviceCallYaml },
    card: { name: 'card config YAML', file: 'ceiling-scene-card.yaml', build: cardYaml },
    scene: { name: 'scene JSON', file: 'ceiling-scene.json', build: sceneJson }
  };

  /* -------------------------------------------------------- copy / download */

  function legacyCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-1000px';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (err) { /* ignore */ }
    document.body.removeChild(ta);
  }

  function copyText(text, button) {
    var flash = function (label) {
      if (!button) return;
      var original = button.textContent;
      button.textContent = label;
      setTimeout(function () { button.textContent = original; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { flash('Copied'); },
        function () { legacyCopy(text); flash('Copied'); });
    } else {
      legacyCopy(text);
      flash('Copied');
    }
  }

  function downloadText(filename, text) {
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1500);
  }

  function setStatus(text) {
    var el2 = document.getElementById('status');
    if (el2) el2.textContent = text || '';
  }

  /* ---------------------------------------------------------------- canvas */

  var canvas = document.getElementById('canvas');
  var ctx = canvas.getContext('2d');
  var view = null;
  var drag = null;
  var lastFrame = [];

  function currentTime() {
    if (state.playing) {
      var now = performance.now();
      if (!state.t0) state.t0 = now;
      return (now - state.t0) / 1000;
    }
    return state.frozenT || 0;
  }

  function draw() {
    var room = state.scene.room || { width: 6, height: 4.5 };
    var dpr = window.devicePixelRatio || 1;
    var cssWidth = Math.max(240, canvas.clientWidth || 640);
    var cssHeight = Math.max(180, Math.round(cssWidth * (room.height / room.width)) + 24);
    if (canvas.width !== Math.round(cssWidth * dpr) || canvas.height !== Math.round(cssHeight * dpr)) {
      canvas.width = Math.round(cssWidth * dpr);
      canvas.height = Math.round(cssHeight * dpr);
      canvas.style.height = cssHeight + 'px';
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssWidth, cssHeight);
    ctx.fillStyle = '#0B1120';
    ctx.fillRect(0, 0, cssWidth, cssHeight);

    var pad = 16;
    var scale = Math.min((cssWidth - 2 * pad) / room.width, (cssHeight - 2 * pad) / room.height);
    var ox = (cssWidth - room.width * scale) / 2;
    var oy = (cssHeight - room.height * scale) / 2;
    view = { ox: ox, oy: oy, scale: scale };
    var toX = function (x) { return ox + x * scale; };
    var toY = function (y) { return oy + y * scale; };

    ctx.fillStyle = '#0F172A';
    ctx.fillRect(toX(0), toY(0), room.width * scale, room.height * scale);

    var t = currentTime();
    state.frozenT = t;
    var frame = E.computeFrame(state.scene, state.effect, state.params, state.palette, t);
    lastFrame = frame;

    var cols = (state.scene.grid && state.scene.grid.cols) || 1;
    var rows = (state.scene.grid && state.scene.grid.rows) || 1;
    var cellW = room.width / Math.max(1, cols);
    var cellH = room.height / Math.max(1, rows);
    var haloScaled = Math.max(cellW, cellH) * 0.95 * scale;
    var byId = {};
    frame.forEach(function (entry) { byId[entry.entity_id] = entry; });

    // diffuse halos (additive so pools of light blend)
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    (state.scene.lights || []).forEach(function (light) {
      var entry = byId[light.entity_id];
      if (!entry) return;
      var alpha = 0.10 + 0.42 * (entry.brightness_pct / 100);
      var gradient = ctx.createRadialGradient(toX(light.x), toY(light.y), 0, toX(light.x), toY(light.y), haloScaled);
      gradient.addColorStop(0, 'rgba(' + entry.rgb.join(',') + ',' + alpha.toFixed(3) + ')');
      gradient.addColorStop(0.45, 'rgba(' + entry.rgb.join(',') + ',' + (alpha * 0.42).toFixed(3) + ')');
      gradient.addColorStop(1, 'rgba(' + entry.rgb.join(',') + ',0)');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(toX(light.x), toY(light.y), haloScaled, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.restore();

    // fixtures
    (state.scene.lights || []).forEach(function (light, index) {
      var entry = byId[light.entity_id];
      var rgb = entry ? entry.rgb : [90, 100, 120];
      var bright = entry ? entry.brightness_pct / 100 : 0.2;
      var cx = toX(light.x);
      var cy = toY(light.y);
      var isSelected = index === state.selected;
      ctx.beginPath();
      ctx.arc(cx, cy, 11, 0, Math.PI * 2);
      ctx.fillStyle = '#0A0F1C';
      ctx.fill();
      ctx.lineWidth = isSelected ? 2.4 : 1.4;
      ctx.strokeStyle = isSelected ? '#38BDF8' : 'rgba(226,232,240,0.22)';
      ctx.stroke();
      ctx.save();
      ctx.shadowColor = 'rgba(' + rgb.join(',') + ',' + (0.25 + 0.6 * bright).toFixed(2) + ')';
      ctx.shadowBlur = 15 * bright + 5;
      ctx.beginPath();
      ctx.arc(cx, cy, 7.6, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(' + rgb.join(',') + ',' + (0.22 + 0.78 * bright).toFixed(3) + ')';
      ctx.fill();
      ctx.restore();
      ctx.beginPath();
      ctx.arc(cx, cy, 3.1, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,255,255,' + (0.18 + 0.62 * bright).toFixed(3) + ')';
      ctx.fill();
      if (state.labels) {
        ctx.font = '9px ui-monospace, monospace';
        ctx.fillStyle = 'rgba(148,163,184,0.95)';
        ctx.textAlign = 'center';
        ctx.fillText(String(light.col + 1) + '\u00b7' + String(light.row + 1), cx, cy + 22);
      }
    });

    // room bounds + padding
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#64748B';
    ctx.strokeRect(toX(0), toY(0), room.width * scale, room.height * scale);
    var wallPad = room.padding === undefined ? 0 : room.padding;
    if (wallPad > 0) {
      ctx.save();
      ctx.setLineDash([5, 5]);
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(56,189,248,0.45)';
      ctx.strokeRect(toX(wallPad), toY(wallPad), (room.width - 2 * wallPad) * scale, (room.height - 2 * wallPad) * scale);
      ctx.restore();
    }

    // snap grid
    if (state.snap) {
      ctx.fillStyle = 'rgba(100,116,139,0.5)';
      var stepX = cellW / 2;
      var stepY = cellH / 2;
      for (var gx = wallPad; gx <= room.width - wallPad + 1e-9; gx += stepX) {
        for (var gy = wallPad; gy <= room.height - wallPad + 1e-9; gy += stepY) {
          ctx.beginPath();
          ctx.arc(toX(gx), toY(gy), 1.1, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    // pulse-centre crosshair
    var ccx = toX((state.params.center_x || 0.5) * room.width);
    var ccy = toY((state.params.center_y || 0.5) * room.height);
    ctx.save();
    ctx.setLineDash([3, 4]);
    ctx.strokeStyle = 'rgba(56,189,248,0.55)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(ccx - 12, ccy); ctx.lineTo(ccx + 12, ccy);
    ctx.moveTo(ccx, ccy - 12); ctx.lineTo(ccx, ccy + 12);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(ccx, ccy, 7, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();

    updateHud(frame);
    updateSelectedInfo();
  }

  function updateHud(frame) {
    var el2 = document.getElementById('hud');
    if (!el2) return;
    var entry = frame[state.selected] || frame[0];
    el2.textContent = entry
      ? 't ' + fmt(currentTime(), 2) + 's  \u00b7  ' + entry.entity_id +
        '  rgb(' + entry.rgb.join(',') + ')  ' + entry.brightness_pct + '%'
      : 'no fixtures yet - use Generate grid or Add light';
  }

  function loop(now) {
    requestAnimationFrame(loop);
    draw();
  }

  function pointerToRoom(ev) {
    if (!view) return null;
    var rect = canvas.getBoundingClientRect();
    return {
      x: (ev.clientX - rect.left - view.ox) / view.scale,
      y: (ev.clientY - rect.top - view.oy) / view.scale
    };
  }

  function hitTest(point) {
    var threshold = 22 / (view ? view.scale : 1);
    var best = -1;
    var bestDistance = threshold;
    (state.scene.lights || []).forEach(function (light, index) {
      var distance = Math.hypot(light.x - point.x, light.y - point.y);
      if (distance <= bestDistance) { bestDistance = distance; best = index; }
    });
    return best;
  }

  function snapPoint(x, y) {
    var room = state.scene.room || { width: 6, height: 4.5 };
    var grid = state.scene.grid || { rows: 3, cols: 4 };
    if (!state.snap) return { x: Math.round(x * 100) / 100, y: Math.round(y * 100) / 100 };
    var stepX = (room.width || 6) / Math.max(1, grid.cols || 1) / 2;
    var stepY = (room.height || 4.5) / Math.max(1, grid.rows || 1) / 2;
    var pad = room.padding === undefined ? 0 : room.padding;
    var sx = pad + Math.round((x - pad) / stepX) * stepX;
    var sy = pad + Math.round((y - pad) / stepY) * stepY;
    return {
      x: Math.round(E.clamp(sx, 0, room.width) * 100) / 100,
      y: Math.round(E.clamp(sy, 0, room.height) * 100) / 100
    };
  }

  canvas.addEventListener('pointerdown', function (ev) {
    var point = pointerToRoom(ev);
    if (!point) return;
    var index = hitTest(point);
    var room = state.scene.room || { width: 6, height: 4.5 };
    if (index >= 0) {
      state.selected = index;
      drag = { index: index };
      try { canvas.setPointerCapture(ev.pointerId); } catch (err) { /* ignore */ }
    } else if (state.addMode) {
      var x = E.clamp(point.x, 0, room.width);
      var y = E.clamp(point.y, 0, room.height);
      var snapped = snapPoint(x, y);
      var nextIndex = state.scene.lights.length;
      state.scene.lights.push({
        entity_id: 'light.' + state.prefix + '_' + (nextIndex + 1),
        name: 'Can ' + (nextIndex + 1),
        x: snapped.x, y: snapped.y, row: 0, col: nextIndex
      });
      state.selected = nextIndex;
      state.addMode = false;
    } else {
      state.selected = null;
    }
    renderPanel();
    renderSummary();
  });

  canvas.addEventListener('pointermove', function (ev) {
    if (!drag) return;
    var point = pointerToRoom(ev);
    if (!point) return;
    var light = state.scene.lights[drag.index];
    if (!light) return;
    var room = state.scene.room || { width: 6, height: 4.5 };
    var x = E.clamp(point.x, 0, room.width);
    var y = E.clamp(point.y, 0, room.height);
    if (ev.shiftKey) {
      light.x = Math.round(x * 100) / 100;
      light.y = Math.round(y * 100) / 100;
    } else {
      var snapped = snapPoint(x, y);
      light.x = snapped.x;
      light.y = snapped.y;
    }
    updateSelectedInfo();
  });

  function endDrag(ev) {
    if (drag) { try { canvas.releasePointerCapture(ev.pointerId); } catch (err) { /* ignore */ } }
    drag = null;
  }
  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);

  /* ------------------------------------------------------------- summaries */

  function renderSummary() {
    var room = state.scene.room || {};
    var el2 = document.getElementById('sceneSummary');
    if (el2) {
      el2.textContent = fmt(room.width, 2) + ' \u00d7 ' + fmt(room.height, 2) + ' m  \u00b7  ' +
        (state.scene.grid ? state.scene.grid.rows + '\u00d7' + state.scene.grid.cols + ' ' + state.scene.grid.mode : '') +
        '  \u00b7  ' + (state.scene.lights || []).length + ' fixtures  \u00b7  ' +
        E.EFFECT_LABELS[state.effect];
    }
    var chip = document.getElementById('engineChip');
    if (chip) chip.innerHTML = '';
    if (chip) {
      chip.appendChild(h('span', { class: 'dot' }));
      chip.appendChild(h('span', { text: 'engine v' + E.VERSION }));
    }
  }

  function renderTabBar() {
    var tabs = document.getElementById('tabs');
    tabs.innerHTML = '';
    [['layout', 'Layout'], ['effects', 'Effects'], ['palette', 'Palette'],
     ['deploy', 'Deploy'], ['files', 'Files']].forEach(function (entry) {
      tabs.appendChild(h('button', {
        class: 'tab' + (state.tab === entry[0] ? ' active' : ''),
        text: entry[1],
        onclick: function () { state.tab = entry[0]; renderTabBar(); renderPanel(); }
      }));
    });
  }

  /* -------------------------------------------------------------- controls */

  function numberField(label, value, step, onInput) {
    var input = h('input', { type: 'number', step: step, value: value, class: 'mono' });
    input.style.width = '90px';
    input.addEventListener('input', function () {
      var v = parseFloat(input.value);
      if (!isNaN(v)) onInput(v);
    });
    return h('div', { class: 'field' }, [h('label', { text: label }), input]);
  }

  function check(label, value, onChange) {
    var input = h('input', { type: 'checkbox' });
    input.checked = !!value;
    input.addEventListener('change', function () { onChange(input.checked); });
    return h('label', { class: 'chk' }, [input, h('span', { text: label })]);
  }

  function textField(label, value, onInput, width) {
    var input = h('input', { type: 'text', value: value, class: 'mono' });
    if (width) input.style.width = width;
    input.addEventListener('input', function () { onInput(input.value); });
    return h('div', { class: 'field' }, [h('label', { text: label }), input]);
  }

  /* ------------------------------------------------------------ panels */

  function renderPanel() {
    var host = document.getElementById('panel');
    host.innerHTML = '';
    if (state.tab === 'effects') return panelEffects(host);
    if (state.tab === 'palette') return panelPalette(host);
    if (state.tab === 'deploy') return panelDeploy(host);
    if (state.tab === 'files') return panelFiles(host);
    return panelLayout(host);
  }

  function panelLayout(host) {
    var room = state.scene.room || { width: 6, height: 4.5, padding: 0.5 };
    var grid = state.gridForm;

    var roomPanel = h('div', { class: 'panel' }, h('h4', { text: 'Room & grid' }));
    roomPanel.appendChild(h('div', { class: 'row' }, [
      numberField('Width (m)', room.width, 0.05, function (v) { room.width = v; renderSummary(); }),
      numberField('Height (m)', room.height, 0.05, function (v) { room.height = v; renderSummary(); }),
      numberField('Wall padding', room.padding === undefined ? 0.5 : room.padding, 0.05, function (v) { room.padding = v; })
    ]));
    var gridRow = h('div', { class: 'row' }, [
      numberField('Rows', grid.rows, 1, function (v) { grid.rows = Math.round(v); }),
      numberField('Cols', grid.cols, 1, function (v) { grid.cols = Math.round(v); })
    ]);
    var modeSelect = h('select', {}, [
      h('option', { value: 'grid', text: 'Grid' }),
      h('option', { value: 'brick', text: 'Brick (staggered)' })
    ]);
    modeSelect.value = grid.mode;
    modeSelect.addEventListener('change', function () { grid.mode = modeSelect.value; });
    gridRow.appendChild(h('div', { class: 'field' }, [h('label', { text: 'Pattern' }), modeSelect]));
    gridRow.appendChild(textField('Prefix', state.prefix, function (v) { state.prefix = v; }, '130px'));
    gridRow.appendChild(h('button', { class: 'primary', text: 'Generate grid', onclick: applyGrid }));
    gridRow.appendChild(h('button', {
      text: 'Renumber',
      title: 'Assign light.<prefix>_1..N in row-major order',
      onclick: renumber
    }));
    roomPanel.appendChild(gridRow);

    roomPanel.appendChild(h('div', { class: 'row' }, [
      check('Snap to grid', state.snap, function (v) { state.snap = v; }),
      check('Show labels', state.labels, function (v) { state.labels = v; }),
      h('button', {
        class: state.addMode ? 'primary' : '',
        text: state.addMode ? 'Adding... (click canvas)' : 'Add light',
        onclick: function () { state.addMode = !state.addMode; renderPanel(); }
      }),
      h('button', { text: 'Clear all', onclick: clearLights })
    ]));
    host.appendChild(roomPanel);

    // selected fixture
    var selectPanel = h('div', { class: 'panel' }, h('h4', { text: 'Selected fixture' }));
    var light = state.scene.lights[state.selected];
    if (!light) {
      selectPanel.appendChild(h('div', { class: 'hint', text: 'Click a fixture on the canvas (or use Add light) to edit its entity id and position.' }));
    } else {
      var idInput = h('input', { type: 'text', class: 'mono', value: light.entity_id });
      idInput.style.width = '100%';
      idInput.addEventListener('input', function () {
        light.entity_id = idInput.value.trim();
        renderSummary();
      });
      selectPanel.appendChild(h('div', { class: 'row' }, h('div', { class: 'field', style: 'flex:1 1 260px' }, [
        h('label', { text: 'Entity id' }), idInput
      ])));
      var info = h('div', { class: 'row mono', id: 'selectedInfo' });
      selectPanel.appendChild(info);
      selectPanel.appendChild(h('div', { class: 'row' }, [
        h('button', {
          class: 'danger', text: 'Remove',
          onclick: function () {
            state.scene.lights.splice(state.selected, 1);
            state.selected = null;
            renderPanel(); renderSummary();
          }
        }),
        h('button', {
          text: 'Center',
          onclick: function () {
            var r = state.scene.room || { width: 6, height: 4.5 };
            light.x = Math.round((r.width / 2) * 100) / 100;
            light.y = Math.round((r.height / 2) * 100) / 100;
            updateSelectedInfo();
          }
        })
      ]));
    }
    host.appendChild(selectPanel);
    updateSelectedInfo();
  }

  function updateSelectedInfo() {
    var info = document.getElementById('selectedInfo');
    if (!info) return;
    var light = state.scene.lights[state.selected];
    if (!light) { info.textContent = ''; return; }
    info.textContent = 'x ' + fmt(light.x, 2) + ' m \u00b7 y ' + fmt(light.y, 2) + ' m \u00b7 row ' + (light.row | 0) + ' \u00b7 col ' + (light.col | 0);
  }

  function panelEffects(host) {
    var grid = h('div', { class: 'grid-effects' });
    E.EFFECTS.forEach(function (effect) {
      grid.appendChild(h('button', {
        class: 'effect' + (state.effect === effect ? ' active' : ''),
        onclick: function () { state.effect = effect; renderSummary(); renderPanel(); }
      }, [
        h('b', { text: E.EFFECT_LABELS[effect] }),
        h('em', { text: E.EFFECT_EQUATIONS[effect] })
      ]));
    });
    host.appendChild(h('div', { class: 'panel' }, [h('h4', { text: 'Effect (' + E.EFFECTS.length + ')' }), grid]));

    var paramsPanel = h('div', { class: 'panel' }, h('h4', { text: 'Parameters' }));
    var keys = (E.EFFECT_PARAMS[state.effect] || []).concat(['brightness_min', 'brightness_max', 'amplitude']);
    keys.forEach(function (key) {
      var spec = E.PARAM_SPECS[key];
      if (!spec) return;
      paramsPanel.appendChild(paramRow(key, spec));
    });
    host.appendChild(paramsPanel);
  }

  function paramRow(key, spec) {
    var input = h('input', {
      type: 'range', min: spec.min, max: spec.max, step: spec.step, value: state.params[key]
    });
    var readout = h('span', {
      class: 'val mono',
      text: fmt(state.params[key], spec.decimals) + (spec.unit ? ' ' + spec.unit : '')
    });
    input.addEventListener('input', function () {
      state.params[key] = parseFloat(input.value);
      readout.textContent = fmt(state.params[key], spec.decimals) + (spec.unit ? ' ' + spec.unit : '');
    });
    return h('div', { class: 'range' }, [
      h('span', { class: 'name', text: spec.label }), input, readout
    ]);
  }

  function panelPalette(host) {
    var presetsPanel = h('div', { class: 'panel' }, h('h4', { text: 'Presets (' + Object.keys(E.PALETTES).length + ')' }));
    var swatches = h('div', { class: 'swatches' });
    Object.keys(E.PALETTES).forEach(function (key) {
      var preset = E.PALETTES[key];
      var bar = h('div', { class: 'bar' });
      bar.style.background = 'linear-gradient(90deg, ' + preset.colors.join(', ') + ')';
      swatches.appendChild(h('button', {
        class: 'swatch' + (samePalette(state.palette, preset.colors) ? ' active' : ''),
        onclick: function () { state.palette = preset.colors.slice(); renderPanel(); }
      }, [bar, h('span', { text: preset.name })]));
    });
    presetsPanel.appendChild(swatches);
    host.appendChild(presetsPanel);

    var stopsPanel = h('div', { class: 'panel' }, h('h4', { text: 'Custom palette \u00b7 cyclical, interpolated in linear light' }));
    var ramp = h('canvas', { class: 'ramp', height: '26' });
    stopsPanel.appendChild(ramp);
    state.palette.forEach(function (hex, index) {
      var color = h('input', { type: 'color', value: normalizeHex(hex) });
      color.addEventListener('input', function () {
        state.palette[index] = color.value.toUpperCase();
        hexInput.value = color.value.toUpperCase();
        drawRamp(ramp);
      });
      var hexInput = h('input', { type: 'text', class: 'hex mono', value: hex });
      hexInput.addEventListener('change', function () {
        var value = hexInput.value.trim();
        if (/^#?[0-9a-fA-F]{6}$/.test(value)) {
          if (value.charAt(0) !== '#') value = '#' + value;
          state.palette[index] = value.toUpperCase();
          color.value = value;
          renderPanel();
        }
      });
      var stop = h('div', { class: 'stop' }, [
        h('span', { class: 'mono hint', text: String(index + 1).padStart(2, '0') }),
        color,
        hexInput,
        h('button', { class: 'small', text: '\u2191', title: 'Move up', onclick: function () { moveStop(index, index - 1); } }),
        h('button', { class: 'small', text: '\u2193', title: 'Move down', onclick: function () { moveStop(index, index + 1); } }),
        h('button', {
          class: 'small danger', text: 'Delete',
          onclick: function () {
            if (state.palette.length <= 1) { setStatus('A palette needs at least one stop.'); return; }
            state.palette.splice(index, 1);
            renderPanel();
          }
        })
      ]);
      stopsPanel.appendChild(stop);
    });
    stopsPanel.appendChild(h('div', { class: 'row' }, [
      h('button', {
        text: 'Add stop',
        onclick: function () { state.palette.push('#FFFFFF'); renderPanel(); }
      }),
      h('button', {
        text: 'Reverse',
        onclick: function () { state.palette = state.palette.slice().reverse(); renderPanel(); }
      }),
      h('button', {
        text: 'Use custom palette',
        onclick: function () { setStatus('Custom palette is already live - export below.'); }
      })
    ]));
    host.appendChild(stopsPanel);
    drawRamp(ramp);
  }

  function moveStop(from, to) {
    if (to < 0 || to >= state.palette.length) return;
    var copy = state.palette.slice();
    var item = copy.splice(from, 1)[0];
    copy.splice(to, 0, item);
    state.palette = copy;
    renderPanel();
  }

  function samePalette(a, b) {
    if (a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (String(a[i]).toUpperCase() !== String(b[i]).toUpperCase()) return false;
    }
    return true;
  }

  function normalizeHex(hex) {
    var text = String(hex).trim();
    if (text.charAt(0) !== '#') text = '#' + text;
    return /^#[0-9a-fA-F]{6}$/.test(text) ? text : '#FFFFFF';
  }

  function drawRamp(canvasEl) {
    if (!canvasEl) return;
    var width = canvasEl.clientWidth || 320;
    var height = 26;
    var dpr = window.devicePixelRatio || 1;
    canvasEl.width = Math.round(width * dpr);
    canvasEl.height = Math.round(height * dpr);
    canvasEl.style.height = height + 'px';
    var g = canvasEl.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    var stops = E.normalizePalette(state.palette);
    for (var x = 0; x < width; x++) {
      var rgb = E.paletteColor(stops, x / width);
      g.fillStyle = 'rgb(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ')';
      g.fillRect(x, 0, 1, height);
    }
  }

  function panelDeploy(host) {
    var panel = h('div', { class: 'panel' }, h('h4', { text: 'Scene & generator' }));
    panel.appendChild(h('div', { class: 'row' },
      textField('Scene name', state.scene.name || 'Ceiling', function (v) { state.scene.name = v; renderSummary(); }, '180px')));
    panel.appendChild(h('div', { class: 'row' }, [
      numberField('Update interval (s)', state.updateInterval, 0.1, function (v) { state.updateInterval = v; }),
      numberField('Transition (s)', state.transition, 0.1, function (v) { state.transition = v; })
    ]));
    panel.appendChild(h('div', { class: 'row' },
      textField('Card title', state.title, function (v) { state.title = v; }, '180px')));
    host.appendChild(panel);

    var exportPanel = h('div', { class: 'panel' }, h('h4', { text: 'Export' }));
    var preview = h('pre', { class: 'mono' });
    Object.keys(EXPORTS).forEach(function (key) {
      var entry = EXPORTS[key];
      exportPanel.appendChild(h('div', { class: 'row' }, [
        h('button', {
          class: 'primary', 'data-export': key, text: 'Copy ' + entry.name,
          onclick: function () { copyText(entry.build(), this); showPreview(preview, key); }
        }),
        h('button', {
          'data-export': key, text: 'Download ' + entry.name,
          onclick: function () { downloadText(entry.file, entry.build()); showPreview(preview, key); }
        }),
        h('button', {
          text: 'Preview', onclick: function () { showPreview(preview, key); }
        })
      ]));
    });
    exportPanel.appendChild(preview);
    host.appendChild(exportPanel);
    showPreview(preview, state.previewKind);
  }

  function showPreview(preview, key) {
    state.previewKind = key;
    var entry = EXPORTS[key];
    if (entry && preview) preview.textContent = entry.build();
  }

  /* --------------------------------------------------------- files tab */

  function panelFiles(host) {
    host.appendChild(h('div', { class: 'panel' }, [
      h('h4', { text: 'Integration files (' + CSG_FILES.length + ')' }),
      h('p', { class: 'hint', text: 'Every file of the Home Assistant integration, embedded verbatim at build time. Paths and byte sizes come from tools/build_studio.py. Copy one into an editor, or download it straight into your browser Downloads folder.' })
    ]));

    var list = h('div', { class: 'panel' }, h('h4', { text: 'Download / copy' }));
    var filelist = h('div', { class: 'filelist' });
    CSG_FILES.forEach(function (entry) {
      var store = document.querySelector('script[data-csg-file="' + entry.path + '"]');
      var text = store ? store.textContent : '';
      filelist.appendChild(h('div', { class: 'filerow' }, [
        h('div', { class: 'filemeta' }, [
          h('span', { class: 'fpath mono', text: entry.path }),
          h('span', { class: 'fsize mono', text: formatBytes(entry.size) })
        ]),
        h('div', { class: 'fileactions' }, [
          h('button', { class: 'small', text: 'Copy', onclick: function () { copyText(text, this); } }),
          h('button', { class: 'small', text: 'Download', onclick: function () { downloadText(entry.path, text); } })
        ])
      ]));
    });
    list.appendChild(filelist);
    host.appendChild(list);

    host.appendChild(installPanel());
  }

  function installPanel() {
    var panel = h('div', { class: 'panel' }, h('h4', { text: 'Install into Home Assistant' }));
    var steps = h('ol', { class: 'steps' });
    steps.appendChild(h('li', {}, [
      h('b', { text: 'Get the integration. ' }),
      'Either add this repository through HACS: HACS \u2192 three-dot menu \u2192 ',
      h('code', { text: 'Custom repositories' }),
      ' \u2192 paste the repo URL \u2192 category ',
      h('code', { text: 'Integration' }),
      ' \u2192 install. Or install manually: download the files above and copy the ',
      h('code', { text: 'custom_components/ceiling_scene_generator' }),
      ' folder into your Home Assistant ',
      h('code', { text: 'config/' }),
      ' directory so it sits next to your ',
      h('code', { text: 'configuration.yaml' }),
      '.'
    ]));
    steps.appendChild(h('li', {}, [
      h('b', { text: 'Restart Home Assistant. ' }),
      'A full restart is required so the integration and its services are registered.'
    ]));
    steps.appendChild(h('li', {}, [
      h('b', { text: 'Add the integration. ' }),
      'Go to Settings \u2192 Devices & services \u2192 ',
      h('code', { text: 'Add integration' }),
      ' \u2192 search for ',
      h('code', { text: 'Ceiling Scene Generator' }),
      ' \u2192 follow the config flow (update interval, transition, auto-resume).'
    ]));
    steps.appendChild(h('li', {}, [
      h('b', { text: 'Lovelace card. ' }),
      'The card is served automatically at ',
      h('code', { text: '/ceiling_scene_generator/ceiling-scene-card.js' }),
      ' (add it under Settings \u2192 Dashboards \u2192 Resources). Manual alternative: copy ',
      h('code', { text: 'dist/ceiling-scene-card.js' }),
      ' into your ',
      h('code', { text: 'config/www/' }),
      ' folder and add the resource ',
      h('code', { text: '/local/ceiling-scene-card.js' }),
      ' instead.'
    ]));
    steps.appendChild(h('li', {}, [
      h('b', { text: 'Use it. ' }),
      'Trigger the live generator with the service call above, or drop the card YAML on a dashboard and press Start Generator.'
    ]));
    panel.appendChild(steps);
    return panel;
  }

  /* ----------------------------------------------------------- operations */

  function applyGrid() {
    var room = state.scene.room || {};
    var layout = E.buildLayout({
      prefix: state.prefix,
      rows: state.gridForm.rows,
      cols: state.gridForm.cols,
      mode: state.gridForm.mode,
      width: room.width || 6,
      height: room.height || 4.5,
      padding: room.padding === undefined ? 0.5 : room.padding,
      name: state.scene.name || 'Ceiling'
    });
    state.scene.lights = layout.lights;
    state.scene.room = layout.room;
    state.scene.grid = layout.grid;
    state.selected = null;
    setStatus('Generated ' + layout.lights.length + ' fixtures (' + state.gridForm.mode + ').');
    renderPanel();
    renderSummary();
  }

  function renumber() {
    var lights = state.scene.lights.slice().sort(function (a, b) {
      return (a.row - b.row) || (a.col - b.col);
    });
    var prefix = String(state.prefix || 'ceiling_can').trim().toLowerCase().replace(/\s+/g, '_') || 'ceiling_can';
    lights.forEach(function (light, index) {
      light.entity_id = 'light.' + prefix + '_' + (index + 1);
      light.name = 'Can ' + (index + 1);
    });
    state.scene.lights = lights;
    state.selected = null;
    setStatus('Renumbered ' + lights.length + ' fixtures as light.' + prefix + '_1..' + lights.length + '.');
    renderPanel();
    renderSummary();
  }

  function clearLights() {
    state.scene.lights = [];
    state.selected = null;
    setStatus('All fixtures removed.');
    renderPanel();
    renderSummary();
  }

  /* ----------------------------------------------------------------- boot */

  var playBtn = document.getElementById('playBtn');
  playBtn.addEventListener('click', function () {
    state.playing = !state.playing;
    playBtn.textContent = state.playing ? 'Pause' : 'Play';
  });

  renderTabBar();
  renderPanel();
  renderSummary();
  setStatus('Ready. Nothing leaves this tab - open the Files tab to install the integration.');
  requestAnimationFrame(loop);
})();
</script>

<div id="csg-filestore" hidden>
@@FILESTORE@@
</div>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        card = read_card()
        engine = extract_engine(card)
        files = collect_files()
        html = build_document(card, files)
    except StudioBuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(html.encode('utf-8'))} bytes, sha256 {digest})")
    print(f"  engine block: {len(engine.encode('utf-8'))} bytes from {CARD.relative_to(ROOT)}")
    print(f"  inlined files: {len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
