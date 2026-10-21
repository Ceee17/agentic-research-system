"""latexmk wrapper with a compact error summary."""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess

from . import core

ERR_FILE_LINE = re.compile(r"^(\S[^:\n]*\.(?:tex|sty|cls|bbl)):(\d+): (.*)$")
UNDEF = re.compile(r"LaTeX Warning: (Citation|Reference) [`']([^']+)' on page \d+ undefined")
PAGES = re.compile(r"Output written on .*?\((\d+) pages?")


def _tex_dirs() -> list[str]:
    home = os.path.expanduser("~")
    pats = [os.environ.get("RA_TEX_BIN") or "",
            os.path.join(home, "AppData", "Roaming", "TinyTeX", "bin", "*"),
            os.path.join(home, ".TinyTeX", "bin", "*"),
            os.path.join(home, "Library", "TinyTeX", "bin", "*"),
            "C:/texlive/*/bin/*", "C:/Program Files/MiKTeX/miktex/bin/x64",
            os.path.join(home, "AppData", "Local", "Programs", "MiKTeX", "miktex", "bin", "x64"),
            "/usr/local/texlive/*/bin/*", "/Library/TeX/texbin"]
    dirs = []
    for pat in pats:
        if pat:
            dirs += sorted(glob.glob(pat), reverse=True)
    return [d for d in dirs if os.path.isdir(d)]


def find_tool(name: str) -> str | None:
    """Full path of a TeX tool: PATH first, then common TinyTeX / TeX Live / MiKTeX locations."""
    hit = shutil.which(name)
    if hit:
        return hit
    for d in _tex_dirs():
        hit = shutil.which(name, path=d)
        if hit:
            return hit
    return None


def tex_env() -> dict:
    """Environment whose PATH contains the TeX bin directory (latexmk must find pdflatex/bibtex)."""
    env = dict(os.environ)
    tool = find_tool("latexmk") or find_tool("pdflatex")
    if tool:
        env["PATH"] = os.path.dirname(tool) + os.pathsep + env.get("PATH", "")
    return env


def latexmk_available() -> bool:
    return find_tool("latexmk") is not None


def latex_mode() -> str:
    """RA_LATEX: auto (default: enforce if latexmk exists, warn otherwise) | strict | off."""
    return os.environ.get("RA_LATEX", "auto").lower()


def summarize_log(log: str) -> dict:
    lines = log.splitlines()
    errors = []
    for i, l in enumerate(lines):
        m = ERR_FILE_LINE.match(l)
        if m:
            errors.append(f"{m.group(1)}:{m.group(2)}: {m.group(3)}")
        elif l.startswith("! "):
            ctx = next((x.strip() for x in lines[i + 1:i + 6] if x.startswith("l.")), "")
            errors.append(f"{l[2:]} {ctx}".strip())
    undefined = sorted({f"{m.group(1).lower()} '{m.group(2)}'" for m in UNDEF.finditer(log)})
    pages = PAGES.search(log)
    overfull = len(re.findall(r"^Overfull \\hbox", log, re.M))
    dedup = list(dict.fromkeys(errors))
    return {"errors": dedup[:25], "undefined": undefined, "pages": int(pages.group(1)) if pages else None,
            "overfull": overfull}


def run_latexmk(cwd, main: str, outdir: str, timeout: int = 300):
    """Run latexmk in `cwd`; CompletedProcess, or None on timeout."""
    cmd = [find_tool("latexmk"), "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", f"-outdir={outdir}"]
    if not (os.path.exists(os.path.join(cwd, "latexmkrc")) or os.path.exists(os.path.join(cwd, ".latexmkrc"))):
        cmd.append("-pdf")
    cmd.append(main)
    try:
        return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, env=tex_env())
    except subprocess.TimeoutExpired:
        return None


def compile_paper(main: str = "main.tex", strict: bool = False, timeout: int = 300) -> dict:
    """Compile paper/<main> into paper/build/. status: ok | failed | missing | no-main."""
    pdir = core.path("paper")
    if not (pdir / main).exists():
        return {"status": "no-main", "errors": [], "undefined": [], "pages": None}
    if not latexmk_available():
        return {"status": "missing", "errors": ["latexmk not found on PATH (install TeX Live; see scripts/setup.sh)"],
                "undefined": [], "pages": None}
    res = run_latexmk(pdir, main, "build", timeout)
    if res is None:
        return {"status": "failed", "errors": [f"latexmk timed out after {timeout}s"], "undefined": [], "pages": None}
    proc = res
    log = core.read_text(pdir / "build" / (os.path.splitext(main)[0] + ".log")) or ""
    summary = summarize_log(log)
    failed = proc.returncode != 0
    if failed and not summary["errors"]:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-12:]
        summary["errors"] = tail or ["latexmk failed (no log)"]
    if strict and summary["undefined"]:
        failed = True
    summary["status"] = "failed" if failed else "ok"
    summary["pdf"] = f"paper/build/{os.path.splitext(main)[0]}.pdf"
    return summary


def format_result(res: dict) -> str:
    out = [f"latexmk: {res['status']}" + (f" ({res['pages']} pages)" if res.get("pages") else "")]
    out += [f"  ERROR {e}" for e in res.get("errors", [])]
    if res.get("undefined"):
        out.append(f"  undefined: {', '.join(res['undefined'][:15])}")
    if res.get("overfull"):
        out.append(f"  overfull hboxes: {res['overfull']}")
    return "\n".join(out)
