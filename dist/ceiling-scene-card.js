/*!
 * dist/ceiling-scene-card.js - build artefact, do not edit.
 *
 * Source of truth: custom_components/ceiling_scene_generator/www/ceiling-scene-card.js
 * Regenerate with: python tools/build_dist.py
 *
 * Standalone install: copy this file to config/www/ceiling-scene-card.js and add
 * /local/ceiling-scene-card.js as a JavaScript module under
 * Settings -> Dashboards -> Resources.
 */
/*!
 * ceiling-scene-card.js
 *
 * Ceiling Scene Generator - Lovelace card and the shared spatial effect engine.
 *
 * The engine below (`globalThis.CeilingSceneEngine`) is a line by line mirror of
 * `custom_components/ceiling_scene_generator/engine.py`; `tests/test_js_parity.py`
 * runs both over identical fixtures, so the canvas preview is provably what the
 * physical lights will do.
 *
 * Loading this file in a non browser context (Node, for the parity test) is
 * supported: the engine is exported and the custom element is only defined when
 * `customElements` exists.
 *
 * Install as a Lovelace resource: /ceiling_scene_generator/ceiling-scene-card.js
 */
(function (root) {
  'use strict';

  var TAU = Math.PI * 2;

  /* ====================================================================== *
   *  Effect engine (mirror of engine.py)                                   *
   * ====================================================================== */

  var ENGINE = (function () {
    var VERSION = '1.0.0';

    var EFFECTS = [
      'linear_wave', 'radial_pulse', 'checkerboard_breathe', 'diagonal_runs',
      'perimeter_chase', 'bouncing_jumps', 'galaxy_stars', 'spiral_vortex',
      'crossfire_waves', 'center_burst'
    ];

    var EFFECT_LABELS = {
      linear_wave: 'Linear Wave',
      radial_pulse: 'Radial Pulse',
      checkerboard_breathe: 'Checkerboard Breathe',
      diagonal_runs: 'Diagonal Runs',
      perimeter_chase: 'Perimeter Chase',
      bouncing_jumps: 'Bouncing Jumps',
      galaxy_stars: 'Galaxy Stars',
      spiral_vortex: 'Spiral Vortex',
      crossfire_waves: 'Crossfire Waves',
      center_burst: 'Center Burst'
    };

    var EFFECT_EQUATIONS = {
      linear_wave: 'u = nx*cos(a) + ny*sin(a);  v = 0.5 + 0.5*sin(2π(u/λ - s*t))',
      radial_pulse: 'r = hypot(xn-cx, yn-cy);  v = 0.5 + 0.5*sin(2π(r/λ - s*t))',
      checkerboard_breathe: 'c = (row+col) mod 2;  v = frac(s*t + c/2);  i = 0.5+0.5*sin(2π(2*s*t + c/2))',
      diagonal_runs: 'u = (nx+ny)/2;  p = frac(u/λ - s*t);  v = exp(-(p-0.5)² / (2σ²))',
      perimeter_chase: 'S = arc length of projection onto room boundary;  v = 0.5 + 0.5*sin(2π(S/λ - s*t))',
      bouncing_jumps: 'p = frac(u/λ + s*t);  tri = 1-|2p-1|;  v = floor(tri*steps)/(steps-1)',
      galaxy_stars: 'h = hash01(index);  v = frac(h₁ + 0.1*s*t);  i = h₃ + (0.5+0.5*sin(2π(s*rate*t + h₂)))³ (1-h₃)',
      spiral_vortex: 'ang = atan2(yn-cy, xn-cx)/2π;  v = 0.5 + 0.5*sin(2π(ang*arms - r/λ + s*t))',
      crossfire_waves: 'wx = 0.5+0.5*sin(2π(nx/λ - s*t));  wy = 0.5+0.5*sin(2π(ny/λ + s*t));  v = (wx+wy)/2',
      center_burst: 'r₀ = frac(s*t)*0.75;  v = exp(-(r-r₀)² / (2σ²))'
    };

    var PALETTES = {
      sunset: { name: 'Sunset', colors: ['#FF6B35', '#F7931E', '#FDC830', '#D62828', '#6A0572'] },
      ocean: { name: 'Ocean', colors: ['#012E4A', '#036280', '#378BA4', '#81BECE', '#E2F1E7'] },
      cyberpunk: { name: 'Cyberpunk', colors: ['#FF2A6D', '#05D9E8', '#01012B', '#D1F7FF', '#7700FF'] },
      rainbow: { name: 'Rainbow', colors: ['#FF0000', '#FFA500', '#FFFF00', '#00C853', '#0091EA', '#6A1B9A'] },
      forest: { name: 'Forest', colors: ['#0B3D0B', '#1E7A34', '#62A744', '#C7E59C', '#2F5D3A'] },
      aurora: { name: 'Aurora', colors: ['#00C2A8', '#3BD4AE', '#7B61FF', '#1B1464', '#00E5FF'] },
      ember: { name: 'Ember', colors: ['#1A0000', '#5C1010', '#C1292E', '#FF7A18', '#FFD166'] },
      ice: { name: 'Ice', colors: ['#061B33', '#0E4C92', '#3FA9F5', '#A8E6FF', '#FFFFFF'] }
    };

    var DEFAULT_PALETTE = 'sunset';

    var DEFAULT_PARAMS = {
      speed: 0.12, angle: 0, wavelength: 0.35, center_x: 0.5, center_y: 0.5,
      brightness_min: 15, brightness_max: 100, amplitude: 1.0, arms: 3,
      steps: 6, sigma: 0.18, phase: 0
    };

    var PARAM_SPECS = {
      speed: { min: 0.01, max: 1.0, step: 0.01, label: 'Speed', unit: 'cyc/s', group: 'motion', decimals: 2 },
      angle: { min: 0, max: 360, step: 1, label: 'Angle', unit: 'deg', group: 'motion', decimals: 0 },
      wavelength: { min: 0.05, max: 1.5, step: 0.01, label: 'Wavelength', unit: 'room', group: 'motion', decimals: 2 },
      phase: { min: 0, max: 1, step: 0.01, label: 'Phase', unit: 'cyc', group: 'motion', decimals: 2 },
      center_x: { min: 0, max: 1, step: 0.01, label: 'Pulse Center X', unit: '', group: 'geometry', decimals: 2 },
      center_y: { min: 0, max: 1, step: 0.01, label: 'Pulse Center Y', unit: '', group: 'geometry', decimals: 2 },
      arms: { min: 1, max: 8, step: 1, label: 'Spiral Arms', unit: '', group: 'geometry', decimals: 0 },
      sigma: { min: 0.02, max: 0.5, step: 0.01, label: 'Band Width', unit: '', group: 'geometry', decimals: 2 },
      steps: { min: 2, max: 12, step: 1, label: 'Jump Steps', unit: '', group: 'geometry', decimals: 0 },
      brightness_min: { min: 1, max: 100, step: 1, label: 'Brightness Floor', unit: '%', group: 'light', decimals: 0 },
      brightness_max: { min: 1, max: 100, step: 1, label: 'Brightness Ceiling', unit: '%', group: 'light', decimals: 0 },
      amplitude: { min: 0, max: 1, step: 0.05, label: 'Brightness Amplitude', unit: '', group: 'light', decimals: 2 }
    };

    var EFFECT_PARAMS = {
      linear_wave: ['speed', 'angle', 'wavelength', 'phase'],
      radial_pulse: ['speed', 'wavelength', 'center_x', 'center_y', 'phase'],
      checkerboard_breathe: ['speed', 'phase'],
      diagonal_runs: ['speed', 'wavelength', 'phase', 'sigma'],
      perimeter_chase: ['speed', 'wavelength', 'phase'],
      bouncing_jumps: ['speed', 'angle', 'wavelength', 'steps', 'phase'],
      galaxy_stars: ['speed'],
      spiral_vortex: ['speed', 'wavelength', 'center_x', 'center_y', 'arms', 'phase'],
      crossfire_waves: ['speed', 'wavelength', 'phase'],
      center_burst: ['speed', 'wavelength', 'center_x', 'center_y', 'sigma', 'phase']
    };

    var GRID_MODES = ['grid', 'brick'];
    var DEFAULT_UPDATE_INTERVAL = 1.5;
    var DEFAULT_TRANSITION = 1.4;
    var DEFAULT_FRAMES = 8;
    var DEFAULT_MIN_COLOR_DELTA = 5;
    var DEFAULT_MIN_BRIGHTNESS_DELTA = 4;

    function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }
    function wrap01(v) { return v - Math.floor(v); }
    function sin01(c) { return 0.5 + 0.5 * Math.sin(TAU * c); }
    function roundHalfUp(v) { return Math.floor(v + 0.5); }

    function srgbChannelToLinear(c) {
      return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    }

    function linearChannelToSrgb(c) {
      return c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
    }

    function parseColor(value, fallback) {
      var def = fallback === undefined ? [255, 255, 255] : fallback;
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        value = value.color || value.hex;
      }
      if (typeof value === 'string') {
        var text = value.trim().replace('#', '');
        if (text.length === 3) text = text[0] + text[0] + text[1] + text[1] + text[2] + text[2];
        if (text.length === 6) {
          var r = parseInt(text.slice(0, 2), 16);
          var g = parseInt(text.slice(2, 4), 16);
          var b = parseInt(text.slice(4, 6), 16);
          if (!isNaN(r) && !isNaN(g) && !isNaN(b) && /^[0-9a-f]+$/i.test(text)) return [r, g, b];
        }
        return def;
      }
      if (Array.isArray(value) && value.length >= 3) {
        var out = [];
        for (var i = 0; i < 3; i++) {
          var n = Math.round(Number(value[i]));
          if (isNaN(n)) return def;
          out.push(clamp(n, 0, 255));
        }
        return out;
      }
      return def;
    }

    function normalizePalette(palette) {
      var list = palette;
      if (typeof list === 'string') {
        var preset = PALETTES[list.trim().toLowerCase()];
        list = preset ? preset.colors.slice() : PALETTES[DEFAULT_PALETTE].colors.slice();
      }
      if (!list || !list.length) list = PALETTES[DEFAULT_PALETTE].colors.slice();
      var stops = [];
      for (var i = 0; i < list.length; i++) {
        var parsed = parseColor(list[i], null);
        if (parsed) stops.push(parsed);
      }
      if (!stops.length) {
        var fallback = PALETTES[DEFAULT_PALETTE].colors;
        for (var j = 0; j < fallback.length; j++) stops.push(parseColor(fallback[j]));
      }
      return stops;
    }

    function paletteColor(stops, position) {
      var n = stops.length;
      if (n === 1) return stops[0].slice();
      var pos = position - Math.floor(position);
      var scaled = pos * n;
      var index = Math.floor(scaled) % n;
      var frac = scaled - Math.floor(scaled);
      var c0 = stops[index];
      var c1 = stops[(index + 1) % n];
      var out = [];
      for (var ch = 0; ch < 3; ch++) {
        var a = srgbChannelToLinear(c0[ch] / 255);
        var b = srgbChannelToLinear(c1[ch] / 255);
        var mixed = a + (b - a) * frac;
        out.push(clamp(roundHalfUp(linearChannelToSrgb(mixed) * 255), 0, 255));
      }
      return out;
    }

    function colorHex(rgb) {
      return '#' + rgb.map(function (c) {
        var t = clamp(Math.round(c), 0, 255).toString(16).toUpperCase();
        return t.length < 2 ? '0' + t : t;
      }).join('');
    }

    function hash01(index, salt) {
      var h = (Math.imul(index | 0, 2654435761) + Math.imul(salt | 0, 40503) + 0x9E3779B9) >>> 0;
      h = (h ^ (h >>> 15)) >>> 0;
      h = Math.imul(h, 2246822519) >>> 0;
      h = (h ^ (h >>> 13)) >>> 0;
      h = Math.imul(h, 3266489917) >>> 0;
      h = (h ^ (h >>> 16)) >>> 0;
      return h / 4294967296;
    }

    function resolveParams(params) {
      var resolved = {};
      var key;
      for (key in DEFAULT_PARAMS) resolved[key] = DEFAULT_PARAMS[key];
      if (params) {
        for (key in params) {
          if (!Object.prototype.hasOwnProperty.call(DEFAULT_PARAMS, key)) continue;
          var value = parseFloat(params[key]);
          if (!isNaN(value)) resolved[key] = value;
        }
      }
      for (key in resolved) {
        var spec = PARAM_SPECS[key];
        if (spec) resolved[key] = clamp(resolved[key], spec.min, spec.max);
      }
      if (resolved.brightness_max < resolved.brightness_min) {
        resolved.brightness_max = resolved.brightness_min;
      }
      return resolved;
    }

    function roomBounds(scene) {
      var room = (scene && scene.room) || {};
      var width = parseFloat(room.width);
      var height = parseFloat(room.height);
      if (isNaN(width)) width = 6.0;
      if (isNaN(height)) height = 4.5;
      return [width > 0.01 ? width : 0.01, height > 0.01 ? height : 0.01];
    }

    function resolveLights(scene) {
      var raw = (scene && scene.lights) || [];
      var lights = [];
      for (var i = 0; i < raw.length; i++) {
        var item = raw[i];
        if (!item || typeof item !== 'object') continue;
        var entityId = String(item.entity_id || item.entity || '').trim();
        if (!entityId) continue;
        var x = parseFloat(item.x);
        var y = parseFloat(item.y);
        lights.push({
          entity_id: entityId,
          x: isNaN(x) ? 0 : x,
          y: isNaN(y) ? 0 : y,
          row: parseInt(item.row, 10) || 0,
          col: parseInt(item.col, 10) || 0,
          index: i,
          name: String(item.name || entityId)
        });
      }
      return lights;
    }

    function prepareNodes(scene) {
      var bounds = roomBounds(scene);
      var width = bounds[0], height = bounds[1];
      var scale = Math.max(width, height);
      return resolveLights(scene).map(function (light) {
        return Object.assign({}, light, {
          nx: light.x / width,
          ny: light.y / height,
          xn: (light.x - width / 2) / scale,
          yn: (light.y - height / 2) / scale,
          rw: width,
          rh: height
        });
      });
    }

    function perimeterFraction(x, y, width, height) {
      var perimeter = 2 * (width + height);
      if (perimeter <= 0) return 0;
      var px = clamp(x, 0, width);
      var py = clamp(y, 0, height);
      var candidates = [
        [py, px],
        [width - px, width + py],
        [height - py, width + height + (width - px)],
        [px, 2 * width + height + (height - py)]
      ];
      var bestDistance = candidates[0][0];
      var bestArc = candidates[0][1];
      for (var i = 1; i < candidates.length; i++) {
        if (candidates[i][0] < bestDistance) {
          bestDistance = candidates[i][0];
          bestArc = candidates[i][1];
        }
      }
      return wrap01(bestArc / perimeter);
    }

    function direction(node, params) {
      var angle = (params.angle * Math.PI) / 180;
      return node.nx * Math.cos(angle) + node.ny * Math.sin(angle);
    }

    var EFFECT_FUNCS = {
      linear_wave: function (node, params, t) {
        var u = direction(node, params);
        var v = sin01(u / params.wavelength - params.speed * t + params.phase);
        return [v, v];
      },
      radial_pulse: function (node, params, t) {
        var dx = node.xn - (params.center_x - 0.5);
        var dy = node.yn - (params.center_y - 0.5);
        var r = Math.hypot(dx, dy);
        var v = sin01(r / params.wavelength - params.speed * t + params.phase);
        return [v, v];
      },
      checkerboard_breathe: function (node, params, t) {
        var parity = ((node.row + node.col) % 2 + 2) % 2;
        var offset = parity ? 0.5 : 0;
        var v = wrap01(params.speed * t + offset + params.phase);
        var intensity = sin01(2 * params.speed * t + offset + params.phase);
        return [v, intensity];
      },
      diagonal_runs: function (node, params, t) {
        var u = (node.nx + node.ny) / 2;
        var p = wrap01(u / params.wavelength - params.speed * t + params.phase);
        var d = p - 0.5;
        var v = Math.exp(-(d * d) / (2 * params.sigma * params.sigma));
        return [v, v];
      },
      perimeter_chase: function (node, params, t) {
        var s = perimeterFraction(node.x, node.y, node.rw, node.rh);
        var v = sin01(s / params.wavelength - params.speed * t + params.phase);
        return [v, v];
      },
      bouncing_jumps: function (node, params, t) {
        var u = direction(node, params);
        var p = wrap01(u / params.wavelength + params.speed * t + params.phase);
        var tri = 1 - Math.abs(2 * p - 1);
        var steps = Math.max(2, params.steps);
        var v = clamp(Math.floor(tri * steps) / (steps - 1), 0, 1);
        return [v, 0.35 + 0.65 * v];
      },
      galaxy_stars: function (node, params, t) {
        var index = node.index;
        var h1 = hash01(index, 1);
        var h2 = hash01(index, 7);
        var h3 = hash01(index, 13);
        var rate = 0.5 + 1.5 * hash01(index, 21);
        var twinkle = sin01(params.speed * rate * t + h2);
        twinkle = twinkle * twinkle * twinkle;
        var v = wrap01(h1 + 0.1 * params.speed * t + params.phase);
        var intensity = 0.15 + 0.25 * h3 + twinkle * (0.85 - 0.25 * h3);
        return [v, clamp(intensity, 0, 1)];
      },
      spiral_vortex: function (node, params, t) {
        var dx = node.xn - (params.center_x - 0.5);
        var dy = node.yn - (params.center_y - 0.5);
        var radius = Math.hypot(dx, dy);
        var angle = Math.atan2(dy, dx) / TAU;
        var v = sin01(angle * params.arms - radius / params.wavelength + params.speed * t + params.phase);
        return [v, v];
      },
      crossfire_waves: function (node, params, t) {
        var wx = sin01(node.nx / params.wavelength - params.speed * t + params.phase);
        var wy = sin01(node.ny / params.wavelength + params.speed * t + params.phase);
        var v = (wx + wy) / 2;
        return [v, v];
      },
      center_burst: function (node, params, t) {
        var dx = node.xn - (params.center_x - 0.5);
        var dy = node.yn - (params.center_y - 0.5);
        var r = Math.hypot(dx, dy);
        var radius = wrap01(params.speed * t + params.phase) * 0.75;
        var d = r - radius;
        var v = Math.exp(-(d * d) / (2 * params.sigma * params.sigma));
        return [v, 0.25 + 0.75 * v];
      }
    };

    function computeFrame(scene, effect, params, palette, t) {
      var resolved = resolveParams(params);
      var stops = normalizePalette(palette);
      var func = EFFECT_FUNCS[effect] || EFFECT_FUNCS.linear_wave;
      var nodes = prepareNodes(scene);
      var frame = [];
      for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        var pair = func(node, resolved, parseFloat(t) || 0);
        var value = clamp(pair[0], 0, 1);
        var intensity = clamp(pair[1], 0, 1);
        var rgb = paletteColor(stops, value);
        var mixed = clamp(0.5 + resolved.amplitude * (intensity - 0.5), 0, 1);
        var brightness = resolved.brightness_min +
          (resolved.brightness_max - resolved.brightness_min) * mixed;
        frame.push({
          entity_id: node.entity_id,
          rgb: rgb,
          brightness_pct: clamp(roundHalfUp(brightness), 1, 100),
          value: Number(value.toFixed(6)),
          intensity: Number(intensity.toFixed(6)),
          row: node.row,
          col: node.col
        });
      }
      return frame;
    }

    function cyclePeriod(params) {
      var speed = resolveParams(params).speed;
      return speed <= 0 ? 60 : 1 / speed;
    }

    function indexFrame(frame) {
      var map = {};
      for (var i = 0; i < frame.length; i++) map[frame[i].entity_id] = frame[i];
      return map;
    }

    function frameDeltas(previous, frame, minColorDelta, minBrightnessDelta) {
      var colorThreshold = minColorDelta === undefined ? DEFAULT_MIN_COLOR_DELTA : minColorDelta;
      var brightnessThreshold = minBrightnessDelta === undefined ? DEFAULT_MIN_BRIGHTNESS_DELTA : minBrightnessDelta;
      var changed = [];
      for (var i = 0; i < frame.length; i++) {
        var entry = frame[i];
        var old = previous ? previous[entry.entity_id] : null;
        if (!old) { changed.push(entry); continue; }
        var colorDelta = Math.max(
          Math.abs(entry.rgb[0] - old.rgb[0]),
          Math.abs(entry.rgb[1] - old.rgb[1]),
          Math.abs(entry.rgb[2] - old.rgb[2])
        );
        var brightnessDelta = Math.abs(entry.brightness_pct - old.brightness_pct);
        if (colorDelta >= colorThreshold || brightnessDelta >= brightnessThreshold) {
          changed.push(entry);
        }
      }
      return changed;
    }

    function servicePayload(entry, transition) {
      var payload = {
        rgb_color: entry.rgb.slice(),
        brightness_pct: entry.brightness_pct
      };
      if (transition !== undefined && transition !== null) {
        payload.transition = Math.round(transition * 100) / 100;
      }
      return payload;
    }

    function slugify(text) {
      var slug = String(text === undefined || text === null ? '' : text)
        .trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
      return slug || 'ceiling_scene';
    }

    function buildLayout(options) {
      var opts = options || {};
      var prefix = String(opts.prefix || 'ceiling_can').trim().toLowerCase()
        .replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || 'ceiling_can';
      var rows = Math.max(1, parseInt(opts.rows, 10) || 3);
      var cols = Math.max(1, parseInt(opts.cols, 10) || 4);
      var mode = GRID_MODES.indexOf(opts.mode) >= 0 ? opts.mode : 'grid';
      var width = parseFloat(opts.width);
      var height = parseFloat(opts.height);
      width = isNaN(width) || width <= 0.01 ? 0.01 : width;
      height = isNaN(height) || height <= 0.01 ? 0.01 : height;
      var padWanted = parseFloat(opts.padding);
      if (isNaN(padWanted)) padWanted = 0.5;
      var maxPad = Math.min(width, height) > 0.02 ? Math.min(width, height) / 2 - 0.01 : 0;
      var pad = clamp(padWanted, 0, maxPad);
      var usableW = Math.max(0.01, width - 2 * pad);
      var usableH = Math.max(0.01, height - 2 * pad);
      var cellW = usableW / cols;
      var cellH = usableH / rows;
      var domain = String(opts.domain || 'light').trim().toLowerCase()
        .replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || 'light';
      var sequential = !!opts.sequentialCols;
      var lights = [];
      var counter = 1;
      for (var row = 0; row < rows; row++) {
        var offset = (mode === 'brick' && row % 2 === 1) ? cellW / 2 : 0;
        for (var col = 0; col < cols; col++) {
          var x = pad + (col + 0.5) * cellW + offset;
          var y = pad + (row + 0.5) * cellH;
          if (x > width - pad + 1e-9) break;
          lights.push({
            entity_id: domain + '.' + prefix + '_' + counter,
            name: 'Can ' + counter,
            x: Math.round(x * 10000) / 10000,
            y: Math.round(y * 10000) / 10000,
            row: row,
            col: sequential ? counter - 1 : col
          });
          counter++;
        }
      }
      return {
        name: opts.name || 'Ceiling',
        room: {
          width: Math.round(width * 10000) / 10000,
          height: Math.round(height * 10000) / 10000,
          padding: Math.round(pad * 10000) / 10000
        },
        grid: { mode: mode, rows: rows, cols: cols },
        lights: lights
      };
    }

    return {
      VERSION: VERSION,
      EFFECTS: EFFECTS,
      EFFECT_LABELS: EFFECT_LABELS,
      EFFECT_EQUATIONS: EFFECT_EQUATIONS,
      EFFECT_PARAMS: EFFECT_PARAMS,
      PALETTES: PALETTES,
      DEFAULT_PALETTE: DEFAULT_PALETTE,
      DEFAULT_PARAMS: DEFAULT_PARAMS,
      PARAM_SPECS: PARAM_SPECS,
      GRID_MODES: GRID_MODES,
      DEFAULT_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
      DEFAULT_TRANSITION: DEFAULT_TRANSITION,
      DEFAULT_FRAMES: DEFAULT_FRAMES,
      DEFAULT_MIN_COLOR_DELTA: DEFAULT_MIN_COLOR_DELTA,
      DEFAULT_MIN_BRIGHTNESS_DELTA: DEFAULT_MIN_BRIGHTNESS_DELTA,
      clamp: clamp,
      wrap01: wrap01,
      sin01: sin01,
      roundHalfUp: roundHalfUp,
      parseColor: parseColor,
      normalizePalette: normalizePalette,
      paletteColor: paletteColor,
      colorHex: colorHex,
      hash01: hash01,
      resolveParams: resolveParams,
      roomBounds: roomBounds,
      resolveLights: resolveLights,
      prepareNodes: prepareNodes,
      perimeterFraction: perimeterFraction,
      computeFrame: computeFrame,
      cyclePeriod: cyclePeriod,
      indexFrame: indexFrame,
      frameDeltas: frameDeltas,
      servicePayload: servicePayload,
      slugify: slugify,
      buildLayout: buildLayout
    };
  })();

  root.CeilingSceneEngine = ENGINE;

  if (typeof HTMLElement === 'undefined' || typeof customElements === 'undefined') {
    return; // non browser context (Node parity test / tooling)
  }

  /* ====================================================================== *
   *  Lovelace card                                                         *
   * ====================================================================== */

  var DOMAIN = 'ceiling_scene_generator';

  var CSS = [
    ':host{display:block;font-family:"Plus Jakarta Sans",var(--ha-font-family-body,"Segoe UI",system-ui,sans-serif);',
    '--cse-bg:#0F172A;--cse-panel:#1E293B;--cse-accent:#38BDF8;--cse-line:#64748B;',
    '--cse-text:var(--primary-text-color,#E2E8F0);--cse-muted:var(--secondary-text-color,#94A3B8);}',
    'ha-card{background:var(--ha-card-background,var(--card-background-color,#0F172A));border-radius:var(--ha-card-border-radius,14px);overflow:hidden}',
    '.wrap{padding:14px 14px 16px}',
    '.head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}',
    '.title{font-size:16px;font-weight:700;letter-spacing:.2px;color:var(--cse-text);margin:0}',
    '.sub{font-size:11px;color:var(--cse-muted)}',
    '.spacer{flex:1 1 auto}',
    '.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}',
    '.chip{display:inline-flex;align-items:center;gap:6px;font-size:11px;padding:3px 9px;border-radius:999px;border:1px solid var(--cse-line);color:var(--cse-muted)}',
    '.chip.on{color:#0B1120;background:var(--cse-accent);border-color:var(--cse-accent);font-weight:700}',
    '.dot{width:7px;height:7px;border-radius:50%;background:var(--cse-line)}',
    '.chip.on .dot{background:#0B1120}',
    'button{font:inherit;font-size:12px;cursor:pointer;color:var(--cse-text);background:var(--cse-panel);border:1px solid var(--cse-line);border-radius:9px;padding:6px 11px;transition:border-color .15s,background .15s}',
    'button:hover{border-color:var(--cse-accent)}',
    'button:disabled{opacity:.45;cursor:not-allowed}',
    'button.primary{background:var(--cse-accent);border-color:var(--cse-accent);color:#06121F;font-weight:700}',
    'button.danger{border-color:#7F1D1D;color:#FCA5A5}',
    'button.icon{padding:5px 8px}',
    'canvas{width:100%;display:block;border-radius:12px;background:#0B1120;border:1px solid var(--cse-line);touch-action:none;cursor:crosshair}',
    '.tabs{display:flex;gap:6px;margin:12px 0 10px;flex-wrap:wrap}',
    '.tab{font-size:12px;padding:5px 11px;border-radius:999px;border:1px solid var(--cse-line);background:transparent;color:var(--cse-muted)}',
    '.tab.active{background:var(--cse-panel);color:var(--cse-text);border-color:var(--cse-accent)}',
    '.panel{background:var(--cse-panel);border:1px solid var(--cse-line);border-radius:12px;padding:12px;margin-bottom:10px}',
    '.panel h4{margin:0 0 9px;font-size:12px;letter-spacing:.4px;text-transform:uppercase;color:var(--cse-muted);font-weight:600}',
    '.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}',
    '.row:last-child{margin-bottom:0}',
    '.field{display:flex;flex-direction:column;gap:3px;min-width:74px}',
    '.field label{font-size:10px;color:var(--cse-muted);letter-spacing:.3px;text-transform:uppercase}',
    'input,select{font:inherit;font-size:12px;color:var(--cse-text);background:#0B1120;border:1px solid var(--cse-line);border-radius:8px;padding:5px 7px;min-width:0}',
    'input[type=range]{padding:0;background:transparent;border:0;width:100%;accent-color:var(--cse-accent)}',
    '.range{display:flex;align-items:center;gap:9px;margin-bottom:7px}',
    '.range .name{font-size:11px;color:var(--cse-muted);width:118px;flex:0 0 auto}',
    '.range .val{font-size:11px;color:var(--cse-text);width:66px;text-align:right;flex:0 0 auto}',
    '.grid-effects{display:grid;grid-template-columns:repeat(auto-fill,minmax(158px,1fr));gap:7px}',
    '.effect{text-align:left;padding:8px 9px;border-radius:10px;background:#0B1120;border:1px solid var(--cse-line)}',
    '.effect.active{border-color:var(--cse-accent);box-shadow:inset 0 0 0 1px var(--cse-accent)}',
    '.effect b{display:block;font-size:12px;font-weight:600;margin-bottom:3px}',
    '.effect em{font-style:normal;font-size:9.5px;color:var(--cse-muted);line-height:1.35;display:block;word-break:break-word}',
    '.swatches{display:flex;gap:7px;flex-wrap:wrap}',
    '.swatch{width:70px;padding:5px;border-radius:9px;background:#0B1120;border:1px solid var(--cse-line);cursor:pointer}',
    '.swatch.active{border-color:var(--cse-accent)}',
    '.swatch .bar{height:16px;border-radius:6px;margin-bottom:4px}',
    '.swatch span{font-size:10px;color:var(--cse-muted)}',
    '.stop{display:flex;align-items:center;gap:7px;margin-bottom:6px}',
    '.stop input[type=color]{width:34px;height:26px;padding:0;border-radius:7px;background:transparent}',
    '.stop input.hex{width:92px;text-transform:uppercase}',
    'pre{background:#0B1120;border:1px solid var(--cse-line);border-radius:10px;padding:10px;max-height:250px;overflow:auto;font-size:11px;color:var(--cse-text);white-space:pre;margin:0}',
    '.hint{font-size:11px;color:var(--cse-muted);line-height:1.5}',
    '.status{font-size:11.5px;color:var(--cse-muted);margin-top:9px;min-height:15px}',
    '.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:10.5px;color:var(--cse-muted);margin-top:7px}',
    '.kv{font-size:11px;color:var(--cse-muted)}',
    '.chk{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--cse-muted);cursor:pointer}',
    '.chk input{width:14px;height:14px;accent-color:var(--cse-accent)}'
  ].join('');

  function el(tag, props) {
    var node = document.createElement(tag);
    if (props) {
      for (var key in props) {
        var value = props[key];
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

  class CeilingSceneCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._hass = null;
      this._config = {};
      this._refs = {};
      this._view = null;
      this._drag = null;
      this._status = '';
      this._yaml = '';
      this._switchId = null;
      this._switchState = null;
      this._loaded = false;
      this._raf = null;
      this._scene = ENGINE.buildLayout({ rows: 3, cols: 4, mode: 'grid', width: 6, height: 4.5, padding: 0.5, name: 'Ceiling' });
      this._effect = 'linear_wave';
      this._params = Object.assign({}, ENGINE.DEFAULT_PARAMS);
      this._palette = ENGINE.PALETTES[ENGINE.DEFAULT_PALETTE].colors.slice();
      this._tab = 'layout';
      this._snap = true;
      this._labels = true;
      this._selected = null;
      this._addMode = false;
      this._playing = true;
      this._updateInterval = ENGINE.DEFAULT_UPDATE_INTERVAL;
      this._transition = ENGINE.DEFAULT_TRANSITION;
      this._prefix = 'ceiling_can';
      this._gridForm = { rows: 3, cols: 4, mode: 'grid' };
    }

    static getStubConfig() {
      return {
        type: 'custom:ceiling-scene-card',
        title: 'Ceiling Scene',
        effect: 'linear_wave',
        palette: 'sunset'
      };
    }

    getCardSize() { return 14; }

    setConfig(config) {
      this._config = config || {};
      if (this._config.scene && this._config.scene.lights) {
        this._scene = JSON.parse(JSON.stringify(this._config.scene));
        if (this._scene.grid) this._gridForm = Object.assign(this._gridForm, this._scene.grid);
      }
      if (this._config.effect && ENGINE.EFFECTS.indexOf(this._config.effect) >= 0) {
        this._effect = this._config.effect;
      }
      if (this._config.params) this._params = ENGINE.resolveParams(Object.assign({}, this._params, this._config.params));
      if (this._config.palette) this._palette = ENGINE.normalizePalette(this._config.palette).map(ENGINE.colorHex);
      if (this._config.update_interval) this._updateInterval = Number(this._config.update_interval) || this._updateInterval;
      if (this._config.transition) this._transition = Number(this._config.transition) || this._transition;
      this._previewOnly = !!this._config.preview_only;
      if (this._loaded) this._render();
    }

    set hass(hass) {
      var first = !this._hass;
      this._hass = hass;
      if (this._loaded && first) this._render();
      else this._updateStatus();
    }

    get hass() { return this._hass; }

    connectedCallback() {
      this._render();
      this._loaded = true;
      this._startLoop();
    }

    disconnectedCallback() {
      if (this._raf) cancelAnimationFrame(this._raf);
      this._raf = null;
    }

    /* ---------------------------------------------------------------- shell */

    _render() {
      var root = this.shadowRoot;
      if (!root) return;
      var self = this;
      root.innerHTML = '';
      var style = document.createElement('style');
      style.textContent = CSS;
      root.appendChild(style);

      this._refs.canvas = el('canvas', { class: 'js-canvas', height: '300' });
      this._refs.canvas.addEventListener('pointerdown', function (ev) { self._onPointerDown(ev); });
      this._refs.canvas.addEventListener('pointermove', function (ev) { self._onPointerMove(ev); });
      this._refs.canvas.addEventListener('pointerup', function (ev) { self._onPointerUp(ev); });

      this._refs.head = el('div', { class: 'head' });
      this._refs.status = el('div', { class: 'status' });

      var wrap = el('div', { class: 'wrap' });
      wrap.appendChild(this._refs.head);
      wrap.appendChild(el('div', { class: 'legend' }, [
        el('span', { class: 'mono', text: 'drag a light to move it' }),
        el('span', { class: 'mono', text: 'shift = fine adjust' }),
        el('span', { class: 'mono', text: 'click empty space in Add mode' })
      ]));
      wrap.appendChild(this._refs.canvas);
      this._refs.hud = el('div', { class: 'hint mono', text: 'live preview' });
      wrap.appendChild(this._refs.hud);

      this._refs.tabs = el('div', { class: 'tabs' });
      this._refs.panelHost = el('div');
      if (!this._previewOnly) {
        wrap.appendChild(this._refs.tabs);
        wrap.appendChild(this._refs.panelHost);
      }
      wrap.appendChild(this._refs.status);

      var card = document.createElement('ha-card');
      card.appendChild(wrap);
      root.appendChild(card);

      this._renderHead();
      if (!this._previewOnly) {
        this._renderTabs();
        this._renderPanel();
      }
      this._updateStatus();
      this._startLoop();
    }

    _renderHead() {
      var head = this._refs.head;
      if (!head) return;
      var self = this;
      head.innerHTML = '';
      head.appendChild(el('div', {}, [
        el('h3', { class: 'title', text: this._config.title || 'Ceiling Scene Generator' }),
        el('div', { class: 'sub mono', text: this._sceneSummary() })
      ]));
      head.appendChild(el('div', { class: 'spacer' }));
      var chip = el('span', { class: 'chip' }, [el('span', { class: 'dot' }), el('span', { text: 'idle' })]);
      this._refs.chip = chip;
      head.appendChild(chip);
      this._refs.playButton = el('button', {
        class: 'icon', text: this._playing ? '❚❚' : '▶', title: 'Pause / resume the canvas preview',
        onclick: function () { self._playing = !self._playing; self._renderHead(); }
      });
      head.appendChild(this._refs.playButton);
      this._renderTransport(head);
    }

    _renderTransport(host) {
      var self = this;
      var start = el('button', {
        class: 'primary', text: 'Start Generator', title: 'ceiling_scene_generator.start',
        onclick: function () { self._startGenerator(); }
      });
      var stop = el('button', { text: 'Stop', onclick: function () { self._stopGenerator(); } });
      host.appendChild(start);
      host.appendChild(stop);
      this._refs.startButton = start;
      this._refs.stopButton = stop;
    }

    _sceneSummary() {
      var room = this._scene.room || { width: 6, height: 4.5 };
      return fmt(room.width, 1) + ' x ' + fmt(room.height, 1) + ' m  ·  ' +
        (this._scene.lights || []).length + ' lights  ·  ' +
        ENGINE.EFFECT_LABELS[this._effect];
    }

    _renderTabs() {
      var self = this;
      var tabs = [
        ['layout', 'Room & Lights'],
        ['effects', 'Effects'],
        ['palette', 'Palette'],
        ['deploy', 'Deploy']
      ];
      this._refs.tabs.innerHTML = '';
      tabs.forEach(function (entry) {
        self._refs.tabs.appendChild(el('button', {
          class: 'tab' + (self._tab === entry[0] ? ' active' : ''),
          text: entry[1],
          onclick: function () { self._tab = entry[0]; self._renderTabs(); self._renderPanel(); }
        }));
      });
    }

    _renderPanel() {
      var host = this._refs.panelHost;
      if (!host) return;
      host.innerHTML = '';
      var renderer = {
        layout: this._panelLayout.bind(this),
        effects: this._panelEffects.bind(this),
        palette: this._panelPalette.bind(this),
        deploy: this._panelDeploy.bind(this)
      }[this._tab] || this._panelLayout.bind(this);
      renderer(host);
      this._emitChange();
    }

    /* --------------------------------------------------------------- layout */

    _panelLayout(host) {
      var self = this;
      var room = this._scene.room || { width: 6, height: 4.5, padding: 0.5 };
      var grid = this._gridForm;

      var roomPanel = el('div', { class: 'panel' }, el('h4', { text: 'Room & grid' }));
      var roomRow = el('div', { class: 'row' });
      roomRow.appendChild(this._numberField('Width (m)', room.width, 0.05, function (v) {
        room.width = v; self._scene.room = room; self._renderPanel(); self._renderHead();
      }));
      roomRow.appendChild(this._numberField('Height (m)', room.height, 0.05, function (v) {
        room.height = v; self._scene.room = room; self._renderPanel(); self._renderHead();
      }));
      roomRow.appendChild(this._numberField('Wall padding', room.padding === undefined ? 0.5 : room.padding, 0.05, function (v) {
        room.padding = v; self._scene.room = room;
      }));
      roomPanel.appendChild(roomRow);

      var gridRow = el('div', { class: 'row' });
      gridRow.appendChild(this._numberField('Rows', grid.rows, 1, function (v) { grid.rows = Math.round(v); }));
      gridRow.appendChild(this._numberField('Cols', grid.cols, 1, function (v) { grid.cols = Math.round(v); }));
      var modeSelect = el('select', {}, [
        el('option', { value: 'grid', text: 'Grid' }),
        el('option', { value: 'brick', text: 'Brick (staggered)' })
      ]);
      modeSelect.value = grid.mode;
      modeSelect.addEventListener('change', function () { grid.mode = modeSelect.value; });
      gridRow.appendChild(el('div', { class: 'field' }, [el('label', { text: 'Pattern' }), modeSelect]));
      gridRow.appendChild(el('div', { class: 'field' }, [
        el('label', { text: 'Prefix' }),
        (function () {
          var input = el('input', { type: 'text', value: self._prefix, class: 'mono' });
          input.addEventListener('input', function () { self._prefix = input.value; });
          return input;
        })()
      ]));
      gridRow.appendChild(el('button', {
        class: 'primary', text: 'Generate grid',
        onclick: function () { self._applyGrid(); }
      }));
      gridRow.appendChild(el('button', {
        text: 'Renumber',
        title: 'Assign light.<prefix>_1..N in row-major order',
        onclick: function () { self._renumber(); }
      }));
      roomPanel.appendChild(gridRow);

      var optionsRow = el('div', { class: 'row' });
      optionsRow.appendChild(this._check('Snap to grid', this._snap, function (v) { self._snap = v; }));
      optionsRow.appendChild(this._check('Show labels', this._labels, function (v) { self._labels = v; }));
      optionsRow.appendChild(el('button', {
        class: this._addMode ? 'primary' : '', text: this._addMode ? 'Adding… (click canvas)' : 'Add light',
        onclick: function () { self._addMode = !self._addMode; self._renderPanel(); }
      }));
      optionsRow.appendChild(el('button', { text: 'Clear all', onclick: function () { self._clearLights(); } }));
      roomPanel.appendChild(optionsRow);
      host.appendChild(roomPanel);

      var selectPanel = el('div', { class: 'panel' }, el('h4', { text: 'Selected light' }));
      var light = this._scene.lights[this._selected];
      if (!light) {
        selectPanel.appendChild(el('div', { class: 'hint', text: 'Click a fixture on the canvas (or use Add light) to edit its entity id and position.' }));
      } else {
        var idInput = el('input', { type: 'text', class: 'mono', value: light.entity_id, style: 'width:100%' });
        idInput.addEventListener('input', function () {
          light.entity_id = idInput.value.trim();
          self._renderHead();
        });
        selectPanel.appendChild(el('div', { class: 'row' }, el('div', { class: 'field', style: 'flex:1 1 240px' }, [
          el('label', { text: 'Entity id' }), idInput
        ])));
        var info = el('div', { class: 'row kv mono' });
        this._refs.selectedInfo = info;
        selectPanel.appendChild(info);
        selectPanel.appendChild(el('div', { class: 'row' }, [
          el('button', {
            text: 'Remove', class: 'danger',
            onclick: function () {
              self._scene.lights.splice(self._selected, 1);
              self._selected = null;
              self._renderPanel(); self._renderHead();
            }
          }),
          el('button', { text: 'Center', onclick: function () { self._centerLight(light); } })
        ]));
      }
      host.appendChild(selectPanel);
      this._updateSelectedInfo();
    }

    _numberField(label, value, step, onChange) {
      var input = el('input', { type: 'number', step: step, value: value, style: 'width:88px' });
      input.addEventListener('change', function () {
        var v = parseFloat(input.value);
        if (!isNaN(v)) onChange(v);
      });
      input.addEventListener('input', function () {
        var v = parseFloat(input.value);
        if (!isNaN(v)) onChange(v);
      });
      return el('div', { class: 'field' }, [el('label', { text: label }), input]);
    }

    _check(label, value, onChange) {
      var input = el('input', { type: 'checkbox' });
      input.checked = !!value;
      input.addEventListener('change', function () { onChange(input.checked); });
      return el('label', { class: 'chk' }, [input, el('span', { text: label })]);
    }

    _applyGrid() {
      var room = this._scene.room || {};
      var layout = ENGINE.buildLayout({
        prefix: this._prefix,
        rows: this._gridForm.rows,
        cols: this._gridForm.cols,
        mode: this._gridForm.mode,
        width: room.width || 6,
        height: room.height || 4.5,
        padding: room.padding === undefined ? 0.5 : room.padding,
        name: this._scene.name || 'Ceiling'
      });
      this._scene.lights = layout.lights;
      this._scene.room = layout.room;
      this._scene.grid = layout.grid;
      this._selected = null;
      this._status = 'Generated ' + layout.lights.length + ' fixtures (' + this._gridForm.mode + ').';
      this._renderPanel();
      this._renderHead();
    }

    _renumber() {
      var lights = this._scene.lights.slice().sort(function (a, b) {
        return (a.row - b.row) || (a.col - b.col);
      });
      var prefix = String(this._prefix || 'ceiling_can').trim().toLowerCase().replace(/ /g, '_') || 'ceiling_can';
      lights.forEach(function (light, index) {
        light.entity_id = 'light.' + prefix + '_' + (index + 1);
        light.name = 'Can ' + (index + 1);
      });
      this._scene.lights = lights;
      this._selected = null;
      this._status = 'Renumbered ' + lights.length + ' lights as light.' + prefix + '_1..' + lights.length + '.';
      this._renderPanel();
      this._renderHead();
    }

    _clearLights() {
      this._scene.lights = [];
      this._selected = null;
      this._status = 'All fixtures removed.';
      this._renderPanel();
      this._renderHead();
    }

    _centerLight(light) {
      var room = this._scene.room || { width: 6, height: 4.5 };
      light.x = Math.round((room.width / 2) * 100) / 100;
      light.y = Math.round((room.height / 2) * 100) / 100;
      this._updateSelectedInfo();
    }

    _updateSelectedInfo() {
      var info = this._refs.selectedInfo;
      if (!info) return;
      var light = this._scene.lights[this._selected];
      if (!light) { info.textContent = ''; return; }
      info.innerHTML = '';
      info.appendChild(el('span', { text: 'x ' + fmt(light.x, 2) + ' m' }));
      info.appendChild(el('span', { text: 'y ' + fmt(light.y, 2) + ' m' }));
      info.appendChild(el('span', { text: 'row ' + light.row }));
      info.appendChild(el('span', { text: 'col ' + light.col }));
      info.appendChild(el('span', { text: 'palette ' + fmt(this._params.wavelength * 100, 0) + '% λ' }));
    }

    /* -------------------------------------------------------------- effects */

    _panelEffects(host) {
      var self = this;
      var grid = el('div', { class: 'grid-effects' });
      ENGINE.EFFECTS.forEach(function (effect) {
        grid.appendChild(el('button', {
          class: 'effect' + (self._effect === effect ? ' active' : ''),
          onclick: function () { self._effect = effect; self._renderPanel(); self._renderHead(); }
        }, [
          el('b', { text: ENGINE.EFFECT_LABELS[effect] }),
          el('em', { class: 'mono', text: ENGINE.EFFECT_EQUATIONS[effect] })
        ]));
      });
      host.appendChild(el('div', { class: 'panel' }, [el('h4', { text: 'Effect mode (10)' }), grid]));

      var paramsPanel = el('div', { class: 'panel' }, el('h4', { text: 'Parameters' }));
      var keys = (ENGINE.EFFECT_PARAMS[this._effect] || []).concat(['brightness_min', 'brightness_max', 'amplitude']);
      keys.forEach(function (key) { paramsPanel.appendChild(self._slider(key)); });
      paramsPanel.appendChild(el('div', { class: 'row', style: 'margin-top:8px' }, [
        el('button', {
          text: 'Reset parameters',
          onclick: function () {
            self._params = Object.assign({}, ENGINE.DEFAULT_PARAMS);
            self._renderPanel();
          }
        }),
        el('span', { class: 'kv mono', text: 'cycle ' + fmt(ENGINE.cyclePeriod(self._params), 2) + ' s' })
      ]));
      host.appendChild(paramsPanel);
    }

    _slider(key) {
      var self = this;
      var spec = ENGINE.PARAM_SPECS[key];
      var input = el('input', { type: 'range', min: spec.min, max: spec.max, step: spec.step, value: this._params[key] });
      var value = el('span', { class: 'val mono', text: fmt(this._params[key], spec.decimals) + (spec.unit ? ' ' + spec.unit : '') });
      input.addEventListener('input', function () {
        self._params[key] = parseFloat(input.value);
        value.textContent = fmt(self._params[key], spec.decimals) + (spec.unit ? ' ' + spec.unit : '');
        self._updateSelectedInfo();
      });
      return el('div', { class: 'range' }, [
        el('span', { class: 'name', text: spec.label }),
        input,
        value
      ]);
    }

    /* -------------------------------------------------------------- palette */

    _panelPalette(host) {
      var self = this;
      var swatchHost = el('div', { class: 'swatches' });
      Object.keys(ENGINE.PALETTES).forEach(function (key) {
        var preset = ENGINE.PALETTES[key];
        swatchHost.appendChild(el('div', {
          class: 'swatch', onclick: function () {
            self._palette = preset.colors.slice();
            self._renderPanel();
          }
        }, [
          el('div', { class: 'bar', style: 'background:linear-gradient(90deg,' + preset.colors.join(',') + ')' }),
          el('span', { text: preset.name })
        ]));
      });
      host.appendChild(el('div', { class: 'panel' }, [el('h4', { text: 'Curated palettes (8)' }), swatchHost]));

      var stopsPanel = el('div', { class: 'panel' }, el('h4', { text: 'Palette stops · cyclical, interpolated in linear light' }));
      var stopHost = el('div');
      this._palette.forEach(function (hex, index) {
        var colorInput = el('input', { type: 'color', value: hex });
        var hexInput = el('input', { type: 'text', class: 'hex mono', value: hex.toUpperCase() });
        function setColor(value) {
          var parsed = ENGINE.parseColor(value, null);
          if (!parsed) return;
          self._palette[index] = ENGINE.colorHex(parsed);
          self._renderPanel();
        }
        colorInput.addEventListener('input', function () { setColor(colorInput.value); });
        hexInput.addEventListener('change', function () { setColor(hexInput.value); });
        stopHost.appendChild(el('div', { class: 'stop' }, [
          colorInput, hexInput,
          el('span', { class: 'kv mono', text: 'stop ' + (index + 1) + '/' + self._palette.length }),
          el('button', { class: 'icon', text: '↑', title: 'Move up', onclick: function () { self._moveStop(index, -1); } }),
          el('button', { class: 'icon', text: '↓', title: 'Move down', onclick: function () { self._moveStop(index, 1); } }),
          el('button', {
            class: 'icon danger', text: '✕', title: 'Delete stop', disabled: self._palette.length <= 2,
            onclick: function () {
              if (self._palette.length <= 2) return;
              self._palette.splice(index, 1);
              self._renderPanel();
            }
          })
        ]));
      });
      stopsPanel.appendChild(stopHost);
      stopsPanel.appendChild(el('div', { class: 'row', style: 'margin-top:8px' }, [
        el('button', {
          class: 'primary', text: '+ Add stop',
          onclick: function () {
            var rgb = ENGINE.parseColor(self._palette[self._palette.length - 1]);
            var shifted = rgb.map(function (c) { return Math.round((c + 128) % 256); });
            self._palette.push(ENGINE.colorHex(shifted));
            self._renderPanel();
          }
        }),
        el('button', {
          text: 'Reverse',
          onclick: function () { self._palette = self._palette.slice().reverse(); self._renderPanel(); }
        }),
        el('span', { class: 'kv mono', text: self._palette.length + ' stops' })
      ]));
      host.appendChild(stopsPanel);
    }

    _moveStop(index, delta) {
      var target = index + delta;
      if (target < 0 || target >= this._palette.length) return;
      var copy = this._palette.slice();
      var tmp = copy[index];
      copy[index] = copy[target];
      copy[target] = tmp;
      this._palette = copy;
      this._renderPanel();
    }

    /* --------------------------------------------------------------- deploy */

    _panelDeploy(host) {
      var self = this;
      var panel = el('div', { class: 'panel' }, el('h4', { text: 'Live generator' }));
      var nameInput = el('input', { type: 'text', value: this._scene.name || 'Ceiling', style: 'width:100%' });
      nameInput.addEventListener('input', function () { self._scene.name = nameInput.value; });
      panel.appendChild(el('div', { class: 'row' }, el('div', { class: 'field', style: 'flex:1 1 220px' }, [
        el('label', { text: 'Scene name' }), nameInput
      ])));
      panel.appendChild(el('div', { class: 'row' }, [
        this._numberField('Update interval (s)', this._updateInterval, 0.1, function (v) {
          self._updateInterval = Math.max(0.2, v); self._updateDeployInfo();
        }),
        this._numberField('Transition (s)', this._transition, 0.1, function (v) {
          self._transition = Math.max(0, v); self._updateDeployInfo();
        })
      ]));
      this._refs.deployInfo = el('div', { class: 'hint mono' });
      panel.appendChild(this._refs.deployInfo);
      panel.appendChild(el('div', { class: 'row', style: 'margin-top:8px' }, [
        el('button', { class: 'primary', text: 'Start Generator', onclick: function () { self._startGenerator(); } }),
        el('button', { text: 'Stop', onclick: function () { self._stopGenerator(); } }),
        el('button', { text: 'Compile to HA Script', onclick: function () { self._saveAsScript(); } }),
        el('button', { text: 'Save scene', onclick: function () { self._saveScene(); } }),
        el('button', { text: 'Load scenes', onclick: function () { self._loadScenes(); } })
      ]));
      this._refs.sceneList = el('select', { style: 'width:100%;margin-top:6px' }, el('option', { value: '', text: 'No saved scene selected' }));
      this._refs.sceneList.addEventListener('change', function () {
        var key = self._refs.sceneList.value;
        if (key && self._savedScenes && self._savedScenes[key]) self._applySaved(self._savedScenes[key]);
      });
      panel.appendChild(this._refs.sceneList);
      host.appendChild(panel);

      var exportPanel = el('div', { class: 'panel' }, el('h4', { text: 'Exported YAML' }));
      this._refs.yamlOut = el('pre', { text: this._yaml || '# Start the generator, compile a script, or copy the live service call below.' });
      exportPanel.appendChild(this._refs.yamlOut);
      exportPanel.appendChild(el('div', { class: 'row', style: 'margin-top:8px' }, [
        el('button', {
          text: 'Copy',
          onclick: function () {
            var text = self._refs.yamlOut.textContent || '';
            if (navigator.clipboard) navigator.clipboard.writeText(text).then(function () {
              self._setStatus('Copied to clipboard.');
            }, function () { self._setStatus('Copy failed - select the text manually.'); });
            else self._setStatus('Clipboard unavailable in this context.');
          }
        }),
        el('button', {
          text: 'Show live service call',
          onclick: function () { self._yaml = self._serviceCallYaml(); self._renderPanel(); }
        }),
        el('button', {
          text: 'Show card config',
          onclick: function () { self._yaml = self._cardYaml(); self._renderPanel(); }
        })
      ]));
      exportPanel.appendChild(el('div', {
        class: 'hint',
        text: 'Compile to HA Script calls ceiling_scene_generator.save_as_script and shows the generated scripts.yaml entry - paste it into scripts.yaml or import it under Settings → Automations & scenes → Scripts.'
      }));
      host.appendChild(exportPanel);

      var helpPanel = el('div', { class: 'panel' }, el('h4', { text: 'Install the card' }));
      helpPanel.appendChild(el('div', { html: '<div class="hint">The card resource is served by the integration:<br><span class="mono">' +
        '/ceiling_scene_generator/ceiling-scene-card.js</span><br>Add it under <b>Settings → Dashboards → Resources</b> (JavaScript module) if it is not registered automatically, then add a manual card <span class="mono">type: custom:ceiling-scene-card</span>.</div>' }));
      host.appendChild(helpPanel);

      this._updateDeployInfo();
    }

    _updateDeployInfo() {
      var host = this._refs.deployInfo;
      if (!host) return;
      var changed = this._estimateChanges();
      var perSecond = (changed / Math.max(0.2, this._updateInterval)).toFixed(2);
      host.textContent = 'up to ' + changed + ' of ' + (this._scene.lights || []).length +
        ' lights per step · ' + perSecond + ' packets/s · transition ' + fmt(this._transition, 2) + ' s';
    }

    _estimateChanges() {
      try {
        var now = ENGINE.indexFrame(ENGINE.computeFrame(this._scene, this._effect, this._params, this._palette, 0));
        var later = ENGINE.computeFrame(this._scene, this._effect, this._params, this._palette, this._updateInterval);
        return ENGINE.frameDeltas(now, later).length;
      } catch (err) {
        return 0;
      }
    }

    _applySaved(record) {
      if (!record) return;
      if (record.scene && record.scene.lights) this._scene = JSON.parse(JSON.stringify(record.scene));
      if (record.effect && ENGINE.EFFECTS.indexOf(record.effect) >= 0) this._effect = record.effect;
      if (record.params) this._params = ENGINE.resolveParams(record.params);
      if (record.palette) this._palette = ENGINE.normalizePalette(record.palette).map(ENGINE.colorHex);
      if (this._scene.grid) this._gridForm = Object.assign(this._gridForm, this._scene.grid);
      this._selected = null;
      this._setStatus('Loaded saved scene "' + (record.name || this._scene.name) + '".');
      this._renderPanel();
      this._renderHead();
    }

    /* ------------------------------------------------------------- services */

    _scenePayload() {
      return {
        name: (this._scene.name || 'Ceiling'),
        room: Object.assign({}, this._scene.room),
        grid: Object.assign({}, this._scene.grid),
        lights: (this._scene.lights || []).map(function (light) {
          return {
            entity_id: light.entity_id,
            x: Number(light.x), y: Number(light.y),
            row: light.row | 0, col: light.col | 0
          };
        })
      };
    }

    _paramsPayload() {
      var out = {};
      var source = ENGINE.resolveParams(this._params);
      Object.keys(source).forEach(function (key) {
        var value = source[key];
        out[key] = Math.abs(value - Math.round(value)) < 1e-9 ? Math.round(value) : Number(value.toFixed(4));
      });
      return out;
    }

    async _callService(service, data, wantResponse) {
      var hass = this._hass;
      if (!hass || typeof hass.callService !== 'function') {
        throw new Error('Home Assistant connection unavailable');
      }
      if (wantResponse) {
        try {
          var result = await hass.callService(DOMAIN, service, data, undefined, false, true);
          return result && result.response !== undefined ? result.response : result;
        } catch (firstError) {
          var fallback = await hass.callService(DOMAIN, service, Object.assign({ return_response: true }, data));
          return fallback && fallback.response !== undefined ? fallback.response : fallback;
        }
      }
      return hass.callService(DOMAIN, service, data);
    }

    async _startGenerator() {
      var self = this;
      this._setStatus('Starting generator…');
      try {
        await this._callService('start', {
          name: this._scene.name || 'Ceiling',
          scene: this._scenePayload(),
          effect: this._effect,
          params: this._paramsPayload(),
          palette: this._palette.slice(),
          update_interval: Number(this._updateInterval),
          transition: Number(this._transition)
        });
        this._setStatus('Generator running on ' + (this._scene.lights || []).length + ' lights.');
      } catch (err) {
        this._setStatus('Failed: ' + (err && err.message ? err.message : String(err)));
      }
      this._updateStatus();
      return self;
    }

    async _stopGenerator() {
      this._setStatus('Stopping…');
      try {
        await this._callService('stop', {});
        this._setStatus('Generator stopped.');
      } catch (err) {
        this._setStatus('Failed: ' + (err && err.message ? err.message : String(err)));
      }
      this._updateStatus();
    }

    async _saveAsScript() {
      this._setStatus('Compiling script…');
      try {
        var response = await this._callService('save_as_script', {
          name: this._scene.name || 'Ceiling',
          scene: this._scenePayload(),
          effect: this._effect,
          params: this._paramsPayload(),
          palette: this._palette.slice(),
          frames: ENGINE.DEFAULT_FRAMES,
          transition: Number(this._transition)
        }, true);
        var yaml = typeof response === 'string' ? response : (response && response.yaml) || '';
        this._yaml = yaml || '# the service did not return any YAML';
        this._setStatus(yaml ? 'Compiled ' + (response.script_id || 'script') + ' - copy it into scripts.yaml.' : 'No YAML returned.');
      } catch (err) {
        this._setStatus('Compile failed: ' + (err && err.message ? err.message : String(err)));
      }
      this._renderPanel();
    }

    async _saveScene() {
      try {
        var response = await this._callService('save_scene', {
          name: this._scene.name || 'Ceiling',
          scene: this._scenePayload(),
          effect: this._effect,
          params: this._paramsPayload(),
          palette: this._palette.slice(),
          update_interval: Number(this._updateInterval),
          transition: Number(this._transition)
        }, true);
        this._setStatus('Scene saved' + (response && response.name ? ' as "' + response.name + '".' : '.'));
      } catch (err) {
        this._setStatus('Save failed: ' + (err && err.message ? err.message : String(err)));
      }
    }

    async _loadScenes() {
      try {
        var response = await this._callService('list_scenes', {}, true);
        this._savedScenes = (response && response.scenes) || (response || {});
        var select = this._refs.sceneList;
        if (select) {
          select.innerHTML = '';
          var names = Object.keys(this._savedScenes);
          if (!names.length) {
            select.appendChild(el('option', { value: '', text: 'No saved scenes' }));
          } else {
            select.appendChild(el('option', { value: '', text: 'Select a saved scene…' }));
            names.forEach(function (key) {
              select.appendChild(el('option', { value: key, text: key }));
            });
          }
        }
        this._setStatus(names.length + ' saved scene(s).');
      } catch (err) {
        this._setStatus('Could not list scenes: ' + (err && err.message ? err.message : String(err)));
      }
    }

    _serviceCallYaml() {
      var lines = ['service: ' + DOMAIN + '.start', 'data:'];
      lines.push('  name: ' + JSON.stringify(this._scene.name || 'Ceiling'));
      lines.push('  effect: ' + this._effect);
      lines.push('  palette: [' + this._palette.join(', ') + ']');
      lines.push('  update_interval: ' + fmt(this._updateInterval, 2));
      lines.push('  transition: ' + fmt(this._transition, 2));
      lines.push('  params:');
      var params = this._paramsPayload();
      Object.keys(params).sort().forEach(function (key) {
        lines.push('    ' + key + ': ' + params[key]);
      });
      lines.push('  scene:');
      var scene = this._scenePayload();
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

    _cardYaml() {
      return [
        'type: custom:ceiling-scene-card',
        'title: ' + JSON.stringify(this._config.title || 'Ceiling Scene'),
        'effect: ' + this._effect,
        'palette: [' + this._palette.join(', ') + ']',
        'update_interval: ' + fmt(this._updateInterval, 2),
        'transition: ' + fmt(this._transition, 2),
        '# scene: paste the layout exported below (or use Save scene + start by name)',
        'scene:',
        '  name: ' + JSON.stringify(this._scene.name || 'Ceiling'),
        '  room: {width: ' + this._scene.room.width + ', height: ' + this._scene.room.height + ', padding: ' + this._scene.room.padding + '}',
        '  grid: {mode: ' + this._scene.grid.mode + ', rows: ' + this._scene.grid.rows + ', cols: ' + this._scene.grid.cols + '}',
        '  lights:',
        this._scene.lights.map(function (light) {
          return '    - {entity_id: ' + light.entity_id + ', x: ' + light.x + ', y: ' + light.y + ', row: ' + light.row + ', col: ' + light.col + '}';
        }).join('\n')
      ].join('\n');
    }

    /* ---------------------------------------------------------- public API */
    /* Used by the standalone studio (studio/ceiling-scene-studio.html) and by
     * any other card that wants to drive this one; everything is derived from
     * the live editor state, so nothing is duplicated. */

    get sceneLayout() { return this._scenePayload(); }

    get effectMode() { return this._effect; }

    get paletteStops() { return this._palette.slice(); }

    get paramsState() { return this._paramsPayload(); }

    get isGenerating() {
      var state = this._findGeneratorState();
      return !!(state && state.state === 'on');
    }

    exportServiceCallYaml() { return this._serviceCallYaml(); }

    exportCardYaml() { return this._cardYaml(); }

    exportSceneJson() {
      return JSON.stringify({
        name: this._scene.name || 'Ceiling',
        scene: this._scenePayload(),
        effect: this._effect,
        params: this._paramsPayload(),
        palette: this._palette.slice(),
        update_interval: Number(this._updateInterval),
        transition: Number(this._transition)
      }, null, 2);
    }

    applyScene(record) { this._applySaved(record); }

    _emitChange() {
      try {
        this.dispatchEvent(new CustomEvent('ceiling-scene-change', { bubbles: true, composed: true }));
      } catch (err) { /* non browser context */ }
    }

    /* --------------------------------------------------------------- status */

    _setStatus(text) {
      this._status = text;
      this._updateStatus();
    }

    _updateStatus() {
      if (this._refs.status && this._status) this._refs.status.textContent = this._status;
      var chip = this._refs.chip;
      if (!chip) return;
      var state = this._findGeneratorState();
      var on = !!(state && state.state === 'on');
      chip.className = 'chip' + (on ? ' on' : '');
      chip.innerHTML = '';
      chip.appendChild(el('span', { class: 'dot' }));
      chip.appendChild(el('span', {
        text: on ? ('generator on · ' + (state.attributes && state.attributes.effect ? state.attributes.effect : '')) : 'generator idle'
      }));
      if (this._refs.startButton) this._refs.startButton.disabled = !this._hass;
      if (this._refs.stopButton) this._refs.stopButton.disabled = !this._hass;
    }

    _findGeneratorState() {
      var hass = this._hass;
      if (!hass || !hass.states) return null;
      if (this._switchId && hass.states[this._switchId]) return hass.states[this._switchId];
      var ids = Object.keys(hass.states);
      for (var i = 0; i < ids.length; i++) {
        var state = hass.states[ids[i]];
        if (ids[i].slice(0, 7) === 'switch.' && state.attributes && state.attributes.ceiling_scene_generator) {
          this._switchId = ids[i];
          return state;
        }
      }
      return null;
    }

    /* --------------------------------------------------------------- canvas */

    _startLoop() {
      var self = this;
      if (this._raf) return;
      var tick = function () {
        self._raf = requestAnimationFrame(tick);
        self._draw();
      };
      this._raf = requestAnimationFrame(tick);
    }

    _draw() {
      var canvas = this._refs.canvas;
      if (!canvas || !canvas.isConnected) return;
      var room = this._scene.room || { width: 6, height: 4.5 };
      var dpr = root.devicePixelRatio || 1;
      var cssWidth = Math.max(220, canvas.clientWidth || 600);
      var cssHeight = Math.max(160, Math.round(cssWidth * (room.height / room.width)) + 24);
      if (canvas.width !== Math.round(cssWidth * dpr) || canvas.height !== Math.round(cssHeight * dpr)) {
        canvas.width = Math.round(cssWidth * dpr);
        canvas.height = Math.round(cssHeight * dpr);
        canvas.style.height = cssHeight + 'px';
      }
      var ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssWidth, cssHeight);
      ctx.fillStyle = '#0B1120';
      ctx.fillRect(0, 0, cssWidth, cssHeight);

      var pad = 16;
      var scale = Math.min((cssWidth - 2 * pad) / room.width, (cssHeight - 2 * pad) / room.height);
      var ox = (cssWidth - room.width * scale) / 2;
      var oy = (cssHeight - room.height * scale) / 2;
      this._view = { ox: ox, oy: oy, scale: scale, cssWidth: cssWidth, cssHeight: cssHeight };
      var toX = function (x) { return ox + x * scale; };
      var toY = function (y) { return oy + y * scale; };

      // ceiling slab
      ctx.fillStyle = '#0F172A';
      ctx.fillRect(toX(0), toY(0), room.width * scale, room.height * scale);

      var t = this._playing ? (performance.now() - (this._t0 || performance.now())) / 1000 : (this._frozenT || 0);
      if (!this._t0) this._t0 = performance.now();
      this._frozenT = t;
      var frame = ENGINE.computeFrame(this._scene, this._effect, this._params, this._palette, t);
      this._lastFrame = frame;

      var cellW = room.width / Math.max(1, (this._scene.grid && this._scene.grid.cols) || 1);
      var cellH = room.height / Math.max(1, (this._scene.grid && this._scene.grid.rows) || 1);
      var haloScaled = Math.max(cellW, cellH) * 0.95 * scale;

      // diffuse halos (additive so overlapping pools of light blend)
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      frame.forEach(function (entry) {
        var light = (this._scene.lights || []).find(function (item) { return item.entity_id === entry.entity_id; });
        if (!light) return;
        var alpha = 0.10 + 0.42 * (entry.brightness_pct / 100);
        var gradient = ctx.createRadialGradient(toX(light.x), toY(light.y), 0, toX(light.x), toY(light.y), haloScaled);
        gradient.addColorStop(0, 'rgba(' + entry.rgb.join(',') + ',' + alpha.toFixed(3) + ')');
        gradient.addColorStop(0.45, 'rgba(' + entry.rgb.join(',') + ',' + (alpha * 0.42).toFixed(3) + ')');
        gradient.addColorStop(1, 'rgba(' + entry.rgb.join(',') + ',0)');
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(toX(light.x), toY(light.y), haloScaled, 0, TAU);
        ctx.fill();
      }, this);
      ctx.restore();

      // fixtures
      var self = this;
      (this._scene.lights || []).forEach(function (light) {
        var entry = frame.find(function (item) { return item.entity_id === light.entity_id; });
        var rgb = entry ? entry.rgb : [90, 100, 120];
        var bright = entry ? entry.brightness_pct / 100 : 0.2;
        var cx = toX(light.x);
        var cy = toY(light.y);
        var isSelected = self._scene.lights[self._selected] === light;
        ctx.beginPath();
        ctx.arc(cx, cy, 11, 0, TAU);
        ctx.fillStyle = '#0A0F1C';
        ctx.fill();
        ctx.lineWidth = isSelected ? 2.4 : 1.4;
        ctx.strokeStyle = isSelected ? '#38BDF8' : 'rgba(226,232,240,0.22)';
        ctx.stroke();
        ctx.save();
        ctx.shadowColor = 'rgba(' + rgb.join(',') + ',' + (0.25 + 0.6 * bright).toFixed(2) + ')';
        ctx.shadowBlur = 15 * bright + 5;
        ctx.beginPath();
        ctx.arc(cx, cy, 7.6, 0, TAU);
        ctx.fillStyle = 'rgba(' + rgb.join(',') + ',' + (0.22 + 0.78 * bright).toFixed(3) + ')';
        ctx.fill();
        ctx.restore();
        ctx.beginPath();
        ctx.arc(cx, cy, 3.1, 0, TAU);
        ctx.fillStyle = 'rgba(255,255,255,' + (0.18 + 0.62 * bright).toFixed(3) + ')';
        ctx.fill();
        if (self._labels) {
          ctx.font = '9px ui-monospace, monospace';
          ctx.fillStyle = 'rgba(148,163,184,0.95)';
          ctx.textAlign = 'center';
          ctx.fillText(String(light.col + 1) + '·' + String(light.row + 1), cx, cy + 22);
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
      if (this._snap) {
        ctx.fillStyle = 'rgba(100,116,139,0.5)';
        var stepX = cellW / 2;
        var stepY = cellH / 2;
        for (var gx = wallPad; gx <= room.width - wallPad + 1e-9; gx += stepX) {
          for (var gy = wallPad; gy <= room.height - wallPad + 1e-9; gy += stepY) {
            ctx.beginPath();
            ctx.arc(toX(gx), toY(gy), 1.1, 0, TAU);
            ctx.fill();
          }
        }
      }

      // pulse centre crosshair
      var cx = toX(this._params.center_x * room.width);
      var cy = toY(this._params.center_y * room.height);
      ctx.save();
      ctx.setLineDash([3, 4]);
      ctx.strokeStyle = 'rgba(56,189,248,0.55)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(cx - 12, cy); ctx.lineTo(cx + 12, cy);
      ctx.moveTo(cx, cy - 12); ctx.lineTo(cx, cy + 12);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx, cy, 7, 0, TAU);
      ctx.stroke();
      ctx.restore();

      this._updateHud(frame);
    }

    _updateHud(frame) {
      if (this._refs.hud && this._refs.hud.isConnected) {
        var entry = frame[this._selected] || frame[0];
        this._refs.hud.textContent = entry
          ? 't ' + fmt((this._playing ? (performance.now() - (this._t0 || 0)) / 1000 : this._frozenT), 2) + 's  ·  ' +
            entry.entity_id + '  rgb(' + entry.rgb.join(',') + ')  ' + entry.brightness_pct + '%'
          : 'no lights in the scene';
      }
    }

    _pointerToRoom(ev) {
      var view = this._view;
      if (!view) return null;
      var rect = this._refs.canvas.getBoundingClientRect();
      return {
        x: (ev.clientX - rect.left - view.ox) / view.scale,
        y: (ev.clientY - rect.top - view.oy) / view.scale
      };
    }

    _hitTest(point) {
      var room = this._scene.room || { width: 6, height: 4.5 };
      var threshold = 22 / (this._view ? this._view.scale : 1);
      var best = -1;
      var bestDistance = threshold;
      (this._scene.lights || []).forEach(function (light, index) {
        var distance = Math.hypot(light.x - point.x, light.y - point.y);
        if (distance <= bestDistance) {
          bestDistance = distance;
          best = index;
        }
      });
      return best;
    }

    _onPointerDown(ev) {
      var point = this._pointerToRoom(ev);
      if (!point) return;
      var index = this._hitTest(point);
      if (index >= 0) {
        this._selected = index;
        this._drag = { index: index };
        this._refs.canvas.setPointerCapture(ev.pointerId);
      } else if (this._addMode) {
        var room = this._scene.room || { width: 6, height: 4.5 };
        var x = ENGINE.clamp(point.x, 0, room.width);
        var y = ENGINE.clamp(point.y, 0, room.height);
        var snapped = this._snapPoint(x, y);
        var nextIndex = this._scene.lights.length;
        this._scene.lights.push({
          entity_id: 'light.' + this._prefix + '_' + (nextIndex + 1),
          name: 'Can ' + (nextIndex + 1),
          x: snapped.x,
          y: snapped.y,
          row: 0,
          col: nextIndex
        });
        this._selected = nextIndex;
        this._addMode = false;
      } else {
        this._selected = null;
      }
      this._renderPanel();
    }

    _snapPoint(x, y) {
      var room = this._scene.room || { width: 6, height: 4.5 };
      var grid = this._scene.grid || { rows: 3, cols: 4 };
      if (!this._snap) return { x: Math.round(x * 100) / 100, y: Math.round(y * 100) / 100 };
      var stepX = (room.width || 6) / Math.max(1, grid.cols || 1) / 2;
      var stepY = (room.height || 4.5) / Math.max(1, grid.rows || 1) / 2;
      var pad = room.padding === undefined ? 0 : room.padding;
      var sx = pad + Math.round((x - pad) / stepX) * stepX;
      var sy = pad + Math.round((y - pad) / stepY) * stepY;
      return {
        x: Math.round(ENGINE.clamp(sx, 0, room.width) * 100) / 100,
        y: Math.round(ENGINE.clamp(sy, 0, room.height) * 100) / 100
      };
    }

    _onPointerMove(ev) {
      if (!this._drag) return;
      var point = this._pointerToRoom(ev);
      if (!point) return;
      var light = this._scene.lights[this._drag.index];
      if (!light) return;
      var room = this._scene.room || { width: 6, height: 4.5 };
      var x = ENGINE.clamp(point.x, 0, room.width);
      var y = ENGINE.clamp(point.y, 0, room.height);
      if (ev.shiftKey) {
        light.x = Math.round(x * 100) / 100;
        light.y = Math.round(y * 100) / 100;
      } else {
        var snapped = this._snapPoint(x, y);
        light.x = snapped.x;
        light.y = snapped.y;
      }
      this._updateSelectedInfo();
    }

    _onPointerUp(ev) {
      if (this._drag) {
        try { this._refs.canvas.releasePointerCapture(ev.pointerId); } catch (err) { /* ignore */ }
      }
      this._drag = null;
    }
  }

  customElements.define('ceiling-scene-card', CeilingSceneCard);

  root.customCards = root.customCards || [];
  root.customCards.push({
    type: 'ceiling-scene-card',
    name: 'Ceiling Scene Card',
    description: 'Spatial ceiling light orchestrator - 10 mathematical effects, palette builder and live generator.',
    preview: false
  });
})(typeof globalThis !== 'undefined' ? globalThis : this);
