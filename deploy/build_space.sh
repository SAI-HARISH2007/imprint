#!/usr/bin/env bash
# Assemble a folder that can be pushed to a Hugging Face Docker Space.
# usage: deploy/build_space.sh /path/to/output
set -euo pipefail
OUT="${1:?output folder}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
rm -rf "$OUT" && mkdir -p "$OUT/service"
cp "$HERE"/deploy/space/{Dockerfile,README.md,requirements.txt} "$OUT/"
cp "$HERE"/service/{app,chain,core,limits,receipt,stress,verdict}.py "$HERE"/service/abi.json "$OUT/service/"
echo "space folder ready: $OUT"
