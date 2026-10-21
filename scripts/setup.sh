#!/usr/bin/env bash
# One-time setup of the shared workspace: Python venv + science stack, toolchain check.
# Papers are created afterwards with `NEW PAPER <name>` in chat (or `./ra paper new <name>`);
# each paper gets its own git repository in papers/<name>/ (there is no git repo at the root).
# Usage: bash scripts/setup.sh [--no-venv]
set -euo pipefail
cd "$(dirname "$0")/.."
NO_VENV=0
for a in "$@"; do
  case "$a" in --no-venv) NO_VENV=1 ;; esac
done

echo "== Python environment (.venv) =="
if [ "$NO_VENV" = 0 ]; then
  if command -v uv >/dev/null 2>&1; then
    [ -d .venv ] || uv venv .venv --python 3.12 || uv venv .venv
    VIRTUAL_ENV="$PWD/.venv" uv pip install -r requirements.txt --python .venv
  else
    PY=""
    for c in python3 python; do
      if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then PY="$c"; break; fi
    done
    [ -n "$PY" ] || { echo "Need Python >= 3.9 or uv (https://docs.astral.sh/uv/)"; exit 1; }
    [ -d .venv ] || "$PY" -m venv .venv
    VPY=.venv/bin/python; [ -x "$VPY" ] || VPY=.venv/Scripts/python.exe
    "$VPY" -m pip install --upgrade pip
    "$VPY" -m pip install -r requirements.txt
  fi
fi

echo "== TeX toolchain =="
echo "TeX is found automatically (PATH, TinyTeX, TeX Live, MiKTeX). If ./ra doctor reports it missing:"
echo "  TinyTeX (small):  https://yihui.org/tinytex/   then: tlmgr install latexmk latexdiff texcount"
echo "  TeX Live (full):  https://www.tug.org/texlive/"
echo "Without TeX the Overleaf zip is still produced; PDFs then come from Overleaf."
command -v git >/dev/null 2>&1 || echo "WARNING: git not found; papers need it for their repositories."

echo "== doctor =="
bash ./ra doctor || true
echo
echo "Next: open Claude Code in THIS folder and type \`NEW PAPER <name>\` (or \`PAPER <name>\`). See README.md."
