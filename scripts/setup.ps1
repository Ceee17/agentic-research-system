# One-time setup of the shared workspace on Windows (PowerShell). Requires Git for Windows (bash for ./ra).
# Papers are created afterwards with `NEW PAPER <name>` in chat; each gets its own git repo in papers/<name>/.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "== Python environment (.venv) =="
if (Get-Command uv -ErrorAction SilentlyContinue) {
    if (-not (Test-Path .venv)) { uv venv .venv --python 3.12; if (-not $?) { uv venv .venv } }
    $env:VIRTUAL_ENV = (Resolve-Path .venv).Path
    uv pip install -r requirements.txt --python .venv
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    if (-not (Test-Path .venv)) { py -3 -m venv .venv }
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
} else {
    Write-Host "Install uv (winget install astral-sh.uv) or Python 3.9+ first."; exit 1
}

Write-Host "== TeX toolchain =="
Write-Host "TeX is found automatically (PATH, TinyTeX, TeX Live, MiKTeX). If ./ra doctor reports it missing, install"
Write-Host "TinyTeX (https://yihui.org/tinytex/) then: tlmgr install latexmk latexdiff texcount"
Write-Host "Without TeX the Overleaf zip is still produced; PDFs then come from Overleaf."

if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
    Write-Host "WARNING: bash not found. Install Git for Windows; ./ra and the Claude Code hooks need it."
}

Write-Host "== doctor =="
bash ./ra doctor
Write-Host "Next: open Claude Code in THIS folder and type 'NEW PAPER <name>' (or 'PAPER <name>'). See README.md."
