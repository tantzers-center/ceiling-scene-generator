/* Dump JS engine output for the Python parity test.
 *
 * usage: node tests/parity_dump.js fixtures.json
 *
 * projects.json holds {palettes: {...}, layouts: [...], cases: [...]}; the output
 * is {version, effects, paletteTable, palettes, layouts, paletteSweep, frames}.
 */
'use strict';

const fs = require('fs');
const path = require('path');

require(path.join(__dirname, '..', 'custom_components', 'ceiling_scene_generator', 'www', 'ceiling-scene-card.js'));

const ENGINE = globalThis.CeilingSceneEngine;
if (!ENGINE) {
  process.stderr.write('CeilingSceneEngine was not exported by the card bundle\n');
  process.exit(2);
}

const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const out = {
  version: ENGINE.VERSION,
  effects: ENGINE.EFFECTS,
  paletteTable: ENGINE.PALETTES,
  palettes: {},
  layouts: [],
  paletteSweep: {},
  frames: []
};

const paletteNames = Object.keys(payload.palettes || {});
for (const name of paletteNames) {
  const stops = ENGINE.normalizePalette(payload.palettes[name]);
  out.palettes[name] = stops.map(ENGINE.colorHex);
  const sweep = [];
  for (let index = 0; index <= 64; index++) {
    const position = index / 64;
    const rgb = ENGINE.paletteColor(stops, position);
    sweep.push([position, rgb[0], rgb[1], rgb[2]]);
  }
  out.paletteSweep[name] = sweep;
}

for (const options of payload.layouts || []) {
  out.layouts.push(ENGINE.buildLayout(options));
}

for (const testCase of payload.cases) {
  out.frames.push(
    ENGINE.computeFrame(testCase.scene, testCase.effect, testCase.params, testCase.palette, testCase.t)
  );
}

process.stdout.write(JSON.stringify(out));
