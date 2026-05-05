#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXT_DIR="$ROOT_DIR/extensions/chrome-web-clipper-mvp"

required_files=(
  "manifest.json"
  "background.js"
  "content-script.js"
  "popup.html"
  "popup.js"
  "options.html"
  "options.js"
  "styles.css"
  "icons/lumina-128.png"
)

for relative in "${required_files[@]}"; do
  if [[ ! -f "$EXT_DIR/$relative" ]]; then
    echo "Missing required extension file: $relative" >&2
    exit 1
  fi
done

node - <<'NODE' "$EXT_DIR/manifest.json"
const fs = require('fs');
const manifestPath = process.argv[2];
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
if (manifest.manifest_version !== 3) {
  throw new Error('Extension manifest must use manifest_version 3.');
}
if (!manifest.background || !manifest.background.service_worker) {
  throw new Error('Extension manifest is missing background.service_worker.');
}
if (!Array.isArray(manifest.content_scripts) || manifest.content_scripts.length === 0) {
  throw new Error('Extension manifest is missing a content_scripts entry.');
}
NODE

node --check "$EXT_DIR/background.js"
node --check "$EXT_DIR/content-script.js"
node --check "$EXT_DIR/popup.js"
node --check "$EXT_DIR/options.js"

echo "Chrome extension MVP validation passed."
