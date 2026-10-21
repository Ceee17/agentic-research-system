"""./ra diff — tracked-changes PDF (latexdiff) of the current paper against a git ref.

  ./ra diff --base <git-ref> [--round N]
The base is normally the submitted version: `./ra state commit-of self-review` (or a tag you created).
Writes reviews/response/round-N/diff.pdf (N defaults to the current unprocessed review round).
"""
from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
from ra import core, latex, pipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra diff", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--round", type=int)
    a = ap.parse_args()
    for tool in ("latexdiff", "latexmk", "git"):
        if not (latex.find_tool(tool) or shutil.which(tool)):
            print(f"{tool} not installed (install TeX Live; see scripts/setup.sh)", file=sys.stderr)
            return 3
    st = pipeline.load_state()
    rnd = a.round or pipeline.current_round(st) or st["stages"]["revision"].get("round")
    if not rnd:
        print("cannot determine the review round; pass --round N", file=sys.stderr)
        return 1
    arch = subprocess.run(["git", "archive", "--format=tar", a.base, "paper"], cwd=str(core.root()), capture_output=True)
    if arch.returncode != 0:
        print(f"git archive failed for {a.base}: {arch.stderr.decode(errors='replace')}", file=sys.stderr)
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="ra-diff-"))
    with tarfile.open(fileobj=io.BytesIO(arch.stdout)) as tf:
        tf.extractall(tmp, filter="data") if sys.version_info >= (3, 12) else tf.extractall(tmp)
    old_main = tmp / "paper" / "main.tex"
    build = core.path("paper", "build")
    build.mkdir(parents=True, exist_ok=True)
    diff_tex = build / f"diff-round{rnd}.tex"
    r = subprocess.run([latex.find_tool("latexdiff"), "--flatten", "--type=UNDERLINE", str(old_main), str(core.path("paper", "main.tex"))],
                       cwd=str(core.path("paper")), capture_output=True, text=True, encoding="utf-8", errors="replace")
    shutil.rmtree(tmp, ignore_errors=True)
    if r.returncode != 0 or not r.stdout.strip():
        print(f"latexdiff failed: {r.stderr[-800:]}", file=sys.stderr)
        return 1
    diff_tex.write_text(r.stdout, encoding="utf-8")
    c = subprocess.run([latex.find_tool("latexmk"), "-pdf", "-interaction=nonstopmode", "-outdir=build", f"build/{diff_tex.name}"],
                       cwd=str(core.path("paper")), capture_output=True, text=True, timeout=600,
                       env=latex.tex_env())
    pdf = build / f"diff-round{rnd}.pdf"
    if not pdf.exists():
        print("compiling the diff failed:\n" + latex.format_result(latex.summarize_log(
            core.read_text(build / f"diff-round{rnd}.log") or "") | {"status": "failed"}), file=sys.stderr)
        return 1
    dest = core.path("reviews", "response", f"round-{rnd}", "diff.pdf")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, dest)
    print(f"tracked-changes PDF: {core.rel(dest)} (latexmk rc={c.returncode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
