# Ceiling Scene Generator

Turn an array of individual recessed ceiling lights into one orchestrated spatial canvas.

Ceiling Scene Generator maps every fixture in a room to real coordinates, evaluates one of ten
mathematical effects against those coordinates in real time, and pushes the resulting colours and
brightness to your lights through Home Assistant — slowly enough to be kind to Wi-Fi, smoothly
enough to look continuous.

It ships three things:

| Piece | What it is |
| --- | --- |
| `custom_components/ceiling_scene_generator/` | The integration: async task runner, six services, HA Storage persistence, a compiled-script exporter and a switch entity. |
| `www/ceiling-scene-card.js` | A dependency-free Lovelace card: photorealistic ceiling canvas, drag-and-drop fixture editor, 10 effect presets, palette builder, live generator control. |
| `studio/ceiling-scene-studio.html` | A standalone browser studio for designing a scene without Home Assistant (same engine, exports the YAML/JSON to paste back). |
| `dist/ceiling-scene-card.js` | The same card bundle, published at the repo root for card-only installs (generated — `python tools/build_dist.py`). |

Works with Luxrite, Tuya, Philips Hue, Govee — anything exposed as a `light.*` entity that supports
RGB / RGBW / RGBWW colour and brightness.

---

## Install

### HACS (custom repository)

1. HACS → **⋯** → **Custom repositories**.
2. Repository: `https://github.com/tantzers-center/ceiling-scene-generator`, category **Integration**.
3. Install **Ceiling Scene Generator**, then restart Home Assistant.
4. **Settings → Devices & services → Add integration → Ceiling Scene Generator.**
5. **Add the card to a dashboard** (see below) — installing the integration does *not* put the
   generator UI on a dashboard by itself.

> **Installing the integration gives you three things: a `switch.ceiling_scene` entity, six services,
> and the card bundle served as a Lovelace resource. The generator UI — canvas, effects, palettes,
> Start/Stop — is the card, and a dashboard card has to be added once by hand. If all you see after
> installing is a switch toggle, that is expected: add the card.**

To add it: open a dashboard → **✏️ Edit dashboard** → **+ Add card** → **Manual** → paste:

```yaml
type: custom:ceiling-scene-card
title: Living Room Ceiling
```

If Home Assistant answers **Custom element doesn't exist: ceiling-scene-card**, the resource is not
loaded yet — **Settings → Dashboards → ⋮ → Resources** should list
`/ceiling_scene_generator/ceiling-scene-card.js`; add it (type: JavaScript module) if missing, then
hard-refresh the browser (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>R</kbd>).

### Manual

Copy the folder into your Home Assistant configuration directory:

```
config/
└── custom_components/
    └── ceiling_scene_generator/
```

then restart Home Assistant and add the integration from **Settings → Devices & services**.

### The dashboard card

The integration serves the card itself and registers it as a Lovelace resource automatically:

```
/ceiling_scene_generator/ceiling-scene-card.js
```

If you prefer to manage resources yourself, copy
`custom_components/ceiling_scene_generator/www/ceiling-scene-card.js` into `config/www/` and add
`/local/ceiling-scene-card.js` (type: JavaScript module) under **Settings → Dashboards → Resources**.

Only want the card, no integration? `dist/ceiling-scene-card.js` is the identical bundle published at
the repository root — download it, drop it in `config/www/`, and register
`/local/ceiling-scene-card.js`. It is generated from the integration's copy by
`python tools/build_dist.py`, and a test fails if the two ever drift apart.

Add the card to a dashboard as a manual card:

```yaml
type: custom:ceiling-scene-card
title: Living Room Ceiling
```

Card options:

| Option | Default | Meaning |
| --- | --- | --- |
| `title` | `Ceiling Scene Generator` | Card heading. |
| `scene` | a generated 3×4 grid | Preloaded room + fixture layout. |
| `effect` | `linear_wave` | Which of the ten effects to start on. |
| `params` | engine defaults | Any subset of the parameter table below. |
| `palette` | `sunset` | Preset name or a list of `#RRGGBB` stops. |
| `update_interval` | `1.5` | Seconds between frames pushed to the lights. |
| `transition` | `1.4` | Hardware fade time sent with each call. |
| `preview_only` | `false` | Hide the editor and show just the live canvas + Start/Stop. |

---

## Using it

1. Open the card, **Room & Lights** tab: set room width/height, wall padding, rows/cols, and choose
   **Grid** or **Brick** (staggered alternate rows). Hit **Generate grid**, then drag fixtures into
   place (snap-to-grid is on by default; hold <kbd>Shift</kbd> for free positioning) or type an
   entity id per fixture. **Renumber** re-assigns `light.<prefix>_1…N` in row-major order.
2. **Effects** tab: pick one of the ten effects and tune its parameters.
3. **Palette** tab: pick one of the eight curated palettes or build your own from 2–20+ stops
   (reorder, edit, delete, reverse). Interpolation is cyclic and happens in linear light.
4. **Deploy** tab: set the scene name, update interval and transition, then **Start Generator** for
   the live, rate-limited version — or **Compile to HA Script** to get a static `scripts.yaml`
   entry that keeps animating without the integration running.

### Entities

`switch.ceiling_scene` is on while the generator is running. Attributes show the active effect,
scene name, light count, update interval, frames sent, service calls and the list of saved scenes.

---

## Services

| Service | Purpose |
| --- | --- |
| `ceiling_scene_generator.start` | Start/restart the live generator (pass a `scene:` layout or the `name:` of a saved scene). |
| `ceiling_scene_generator.stop` | Stop it, optionally restoring the lights' previous state. |
| `ceiling_scene_generator.save_as_script` | Compile one cycle into a `scripts.yaml` entry (returns the YAML, optionally writes `<config>/ceiling_scenes/<name>.yaml`). |
| `ceiling_scene_generator.save_scene` | Persist a scene (layout + effect + params + palette) in HA Storage. |
| `ceiling_scene_generator.delete_scene` | Remove a stored scene. |
| `ceiling_scene_generator.list_scenes` | Return all stored scenes plus the runner status. |

Example — start a saved scene at sunset each evening:

```yaml
automation:
  - alias: Living room ceiling - evening wave
    triggers:
      - trigger: sun
        event: sunset
    actions:
      - action: ceiling_scene_generator.start
        data:
          name: Living Room
          effect: linear_wave
          palette: sunset
          update_interval: 1.5
          transition: 1.4
          params:
            speed: 0.12
            wavelength: 0.35
            brightness_min: 15
            brightness_max: 100
```

Example — compile a static script:

```yaml
- action: ceiling_scene_generator.save_as_script
  data:
    name: Living Room
    effect: spiral_vortex
    frames: 8
    write_file: true
  response_variable: compiled
```

`compiled.yaml` then holds something like:

```yaml
ceiling_scene_living_room_linear_wave:
  alias: Ceiling Scene - Living Room - Linear Wave
  icon: mdi:ceiling-light-multiple
  mode: restart
  sequence:
    - repeat:
        count: 8
        sequence:
          - parallel:
              - service: light.turn_on
                target:
                  entity_id:
                    - light.ceiling_can_1
                    - light.ceiling_can_4
                data:
                  rgb_color: [255, 107, 53]
                  brightness_pct: 91
                  transition: 0.99
          - delay:
              seconds: 1.042
```

Lights that share a colour and brightness in a frame are grouped into one service call, so symmetric
effects (checkerboard, bouncing jumps, sharp bands) compile to a couple of calls per frame.

---

## The ten effects

With `nx = x / room_width`, `ny = y / room_height`, `xn`/`yn` the isotropic (aspect-corrected)
coordinates centred on the room, `u` the projection onto the wave direction, `r` the distance to the
pulse centre, `s` the speed in cycles/second, `λ` the wavelength and `t` the elapsed seconds:

| Effect | Equation |
| --- | --- |
| **Linear Wave** | `u = nx·cos(a) + ny·sin(a)`; `v = 0.5 + 0.5·sin(2π(u/λ − s·t))` |
| **Radial Pulse** | `r = hypot(xn−cx, yn−cy)`; `v = 0.5 + 0.5·sin(2π(r/λ − s·t))` |
| **Checkerboard Breathe** | `c = (row+col) mod 2`; `v = frac(s·t + c/2)`; `i = 0.5 + 0.5·sin(2π(2·s·t + c/2))` |
| **Diagonal Runs** | `u = (nx+ny)/2`; `p = frac(u/λ − s·t)`; `v = exp(−(p−0.5)² / 2σ²)` |
| **Perimeter Chase** | `S` = arc length of the projection onto the room boundary; `v = 0.5 + 0.5·sin(2π(S/λ − s·t))` |
| **Bouncing Jumps** | `p = frac(u/λ + s·t)`; `tri = 1 − |2p−1|`; `v = floor(tri·steps)/(steps−1)` |
| **Galaxy Stars** | per-fixture hash `h`; `v = frac(h₁ + 0.1·s·t)`; `i = h₃ + (0.5+0.5·sin(2π(s·rate·t + h₂)))³(1−h₃)` |
| **Spiral Vortex** | `ang = atan2(yn−cy, xn−cx)/2π`; `v = 0.5 + 0.5·sin(2π(ang·arms − r/λ + s·t))` |
| **Crossfire Waves** | `wx = 0.5+0.5·sin(2π(nx/λ − s·t))`, `wy = 0.5+0.5·sin(2π(ny/λ + s·t))`; `v = (wx+wy)/2` |
| **Center Burst** | `r₀ = frac(s·t)·0.75`; `v = exp(−(r−r₀)² / 2σ²)` |

`v` positions the colour in the cyclically wrapped palette; `i` drives brightness between
`brightness_min` and `brightness_max` scaled by `amplitude`.

The same equations exist twice on purpose: in Python (`engine.py`, what the lights do) and in
JavaScript (the card canvas, what you see). A parity test runs both engines over identical fixtures
and compares every frame — currently 720 frames and 18,720 RGB channels with zero differences — so
the preview cannot drift from the hardware.

### Parameters

| Key | Default | Range | Meaning |
| --- | --- | --- | --- |
| `speed` | `0.12` | 0.01–1 | Cycles per second (0.12 ≈ one cycle every 8.3 s). |
| `angle` | `0` | 0–360 | Direction of the directional effects, in degrees. |
| `wavelength` | `0.35` | 0.05–1.5 | Wave length as a fraction of the room's long axis. |
| `phase` | `0` | 0–1 | Global phase offset in cycles. |
| `center_x` / `center_y` | `0.5` | 0–1 | Pulse / spiral / burst centre, room relative. |
| `arms` | `3` | 1–8 | Spiral arms. |
| `sigma` | `0.18` | 0.02–0.5 | Band width of the sharp effects. |
| `steps` | `6` | 2–12 | Quantisation steps of Bouncing Jumps. |
| `brightness_min` / `brightness_max` | `15` / `100` | 1–100 % | Brightness envelope. |
| `amplitude` | `1` | 0–1 | How much of the envelope the effect actually uses. |

### Palettes

Eight curated palettes: `sunset`, `ocean`, `cyberpunk`, `rainbow`, `forest`, `aurora`, `ember`,
`ice`. Or supply your own list of `#RRGGBB` stops (2 to 20+, any length). Stops are interpolated in
linear light with cyclic wrapping, so the palette loops seamlessly and nearest-neighbour interpolation
never produces uneven transitions.

---

## Why it is gentle on Wi-Fi

Wi-Fi friendly rate limiting is the whole trick: the effect is evaluated continuously, but only
lights whose colour moved ≥ `min_color_delta` (default 5) or whose brightness moved ≥
`min_brightness_delta` (default 4) are sent, and then only every `update_interval` seconds. Each
`light.turn_on` carries `transition` (default 1.4 s ≈ the interval), so the fixtures interpolate
between frames themselves. Result: a handful of packets per second at most, and motion that looks
continuous at 60 FPS in the preview.

Typical live load, 12 fixtures with a moving wave: ~6 lights change per step, so ~4 packets/s at a
1.5 s interval — and 0 when the wave is in a symmetric phase.

---

## Testing

The maths, the compiler and the JS parity suite run on a bare Python install (no Home Assistant, no
pytest):

```bash
python tests/run_tests.py          # add -v for per-test output
node --check custom_components/ceiling_scene_generator/www/ceiling-scene-card.js
```

Optional extras (unlock YAML parsing with a real parser):

```bash
npm install --prefix tools
```

`tests/` covers the engine contract for all ten effects, palette interpolation and wrapping, the
layout builder (grid/brick, clamping, slugified entity ids), rate-limited frame diffing, the YAML
writer round-trip through a real parser, the compiled script structure and timing, and the
Python↔JavaScript parity sweep.

---

## Standalone studio

`studio/ceiling-scene-studio.html` loads the same card bundle and engine, so you can design a room,
drag lights, tune effects and pick colours in a plain browser tab — then copy the generated service
call, script YAML or card config into Home Assistant. Open it directly from disk; no server needed.

---

## License

MIT — see [LICENSE](LICENSE).
