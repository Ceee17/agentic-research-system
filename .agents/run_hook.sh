#!/usr/bin/env bash
# Antigravity hook runner
# Always resolves the workspace root regardless of caller working directory
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$(cd "$HERE/.." && pwd)"
exec "$WS/ra" agy-hook "$@"
