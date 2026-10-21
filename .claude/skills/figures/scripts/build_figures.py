"""./ra figs — (re)build every figure from its saved source; record figures/manifest.json.

Sources (each produces figures/<stem>.pdf):
  figures/scripts/<stem>.py     matplotlib/seaborn; called as `python <script> --out figures/<stem>.pdf`
                                (must read data only from results/; may also write figures/<stem>.png)
  figures/tikz/<stem>.tex       standalone TikZ document, compiled with latexmk
  figures/diagrams/<stem>.dot   Graphviz (dot -Tpdf)
  figures/diagrams/<stem>.mmd   Mermaid (mmdc)
Options: --only STEM, --list
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
from ra import core, latex, pipeline, results  # noqa: E402

OUT_EXT = (".pdf", ".png", ".svg")


def sources() -> list[tuple[str, Path]]:
    f = core.path("figures")
    out = [("python", p) for p in sorted((f / "scripts").glob("*.py")) if not p.name.startswith("_")]
    out += [("tikz", p) for p in sorted((f / "tikz").glob("*.tex"))]
    out += [("dot", p) for p in sorted((f / "diagrams").glob("*.dot"))]
    out += [("mermaid", p) for p in sorted((f / "diagrams").glob("*.mmd"))]
    return out


def referenced_inputs(src: Path) -> dict:
    """results/ files a script mentions (files, or every file of a mentioned run directory)."""
    text = core.read_text(src) or ""
    found = {}
    for m in re.finditer(r"results/[A-Za-z0-9_.\-/]+", text):
        p = core.path(m.group(0).rstrip("/"))
        files = [p] if p.is_file() else ([x for x in p.rglob("*") if x.is_file() and x.name != "log.txt"]
                                         if p.is_dir() else [])
        for x in files:
            found[core.rel(x)] = core.sha256_file(x)
    return found


def build(kind: str, src: Path) -> tuple[bool, str, list[Path]]:
    fdir = core.path("figures")
    target = fdir / f"{src.stem}.pdf"
    t0 = time.time() - 1
    env = dict(latex.tex_env(), MPLBACKEND="Agg", PYTHONHASHSEED="0", RA_WORKSPACE=str(core.ws()))
    try:
        if kind == "python":
            r = subprocess.run([sys.executable, str(src), "--out", str(target)], cwd=str(core.root()), env=env,
                               capture_output=True, text=True, timeout=600)
        elif kind == "tikz":
            if not latex.find_tool("latexmk"):
                return False, "latexmk not installed", []
            tmp = Path(tempfile.mkdtemp(prefix="ra-tikz-"))
            r = subprocess.run([latex.find_tool("latexmk"), "-pdf", "-interaction=nonstopmode", "-halt-on-error", f"-outdir={tmp}",
                                src.name], cwd=str(src.parent), capture_output=True, text=True, timeout=300,
                               env=env)
            if r.returncode == 0:
                shutil.copyfile(tmp / f"{src.stem}.pdf", target)
            shutil.rmtree(tmp, ignore_errors=True)
        elif kind == "dot":
            if not shutil.which("dot"):
                return False, "graphviz `dot` not installed", []
            r = subprocess.run(["dot", "-Tpdf", str(src), "-o", str(target)], capture_output=True, text=True, timeout=120)
        else:
            if not shutil.which("mmdc"):
                return False, "mermaid-cli `mmdc` not installed", []
            r = subprocess.run(["mmdc", "-i", str(src), "-o", str(target)], capture_output=True, text=True, timeout=300,
                               shell=(os.name == "nt"))
    except subprocess.TimeoutExpired:
        return False, "timed out", []
    if r.returncode != 0:
        return False, (r.stdout + r.stderr).strip()[-800:], []
    outs = [p for p in fdir.iterdir() if p.is_file() and p.suffix.lower() in OUT_EXT
            and p.stem.startswith(src.stem) and p.stat().st_mtime >= t0]
    if not target.exists():
        return False, f"source ran but did not write {core.rel(target)}", outs
    return True, "", outs


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra figs", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if not pipeline.gate_ok(pipeline.load_state(), "gate1_topic"):
        print("refused: figures are built only after Gate 1 approval", file=sys.stderr)
        return 1
    srcs = [s for s in sources() if not a.only or s[1].stem == a.only]
    if a.list or not srcs:
        for kind, s in srcs:
            print(f"{kind:<8} {core.rel(s)}")
        if not srcs:
            print("no figure sources found (figures/scripts/*.py, figures/tikz/*.tex, figures/diagrams/*.dot|*.mmd)")
        return 0
    man_path = core.path(*results.FIG_MANIFEST)
    man = core.read_json(man_path, {"figures": {}}) or {"figures": {}}
    failed = 0
    for kind, src in srcs:
        ok, err, outs = build(kind, src)
        if not ok:
            failed += 1
            print(f"FAIL {core.rel(src)}: {err}", file=sys.stderr)
            continue
        inputs = referenced_inputs(src) if kind == "python" else {}
        if kind == "python" and not inputs:
            print(f"warn {core.rel(src)}: references no results/ files (data plots must read results/)", file=sys.stderr)
        for o in outs:
            man["figures"][core.rel(o)] = {"kind": kind, "source": core.rel(src), "source_sha256": core.sha256_file(src),
                                           "inputs": inputs, "output_sha256": core.sha256_file(o),
                                           "built_at": core.now()}
            print(f"ok   {core.rel(o)}  <- {core.rel(src)}" + (f"  (inputs: {len(inputs)})" if inputs else ""))
    core.write_json(man_path, man)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
