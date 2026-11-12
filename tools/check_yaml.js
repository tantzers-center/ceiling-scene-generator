/* Parse a YAML file (or stdin) with the vendored `yaml` npm package.
 *
 * usage: node tools/check_yaml.js file.yaml [more.yaml ...]
 *        cat file.yaml | node tools/check_yaml.js
 *
 * exit 0 = parsed, stdout is the JSON document(s)
 * exit 2 = parse error, stderr explains
 * exit 3 = the parser is not installed (caller should skip)
 */
'use strict';

const fs = require('fs');
const path = require('path');

let YAML;
try {
  YAML = require(path.join(__dirname, 'node_modules', 'yaml'));
} catch (err) {
  try {
    YAML = require('yaml');
  } catch (err2) {
    process.stderr.write('YAML_PARSER_MISSING\n');
    process.exit(3);
  }
}

const files = process.argv.slice(2);
try {
  if (files.length === 0) {
    const text = fs.readFileSync(0, 'utf8');
    process.stdout.write(JSON.stringify(YAML.parse(text) === undefined ? null : YAML.parse(text)));
  } else if (files.length === 1) {
    const doc = YAML.parse(fs.readFileSync(files[0], 'utf8'));
    process.stdout.write(JSON.stringify(doc === undefined ? null : doc));
  } else {
    const out = {};
    for (const file of files) {
      const doc = YAML.parse(fs.readFileSync(file, 'utf8'));
      out[file] = doc === undefined ? null : doc;
    }
    process.stdout.write(JSON.stringify(out));
  }
} catch (err) {
  process.stderr.write('PARSE_ERROR: ' + err.message + '\n');
  process.exit(2);
}
