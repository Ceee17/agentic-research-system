"""./ra doctor — report which parts of the toolchain are available, and the papers in the workspace."""
from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import core, latex  # noqa: E402

TEX_TOOLS = [
    ("latexmk", True, "compile the paper and the Overleaf export into PDFs"),
    ("pdflatex", True, "LaTeX engine"),
    ("bibtex", True, "bibliography"),
    ("latexdiff", True, "tracked-changes PDF for revisions (TinyTeX/TeX Live: `tlmgr install latexdiff`)"),
    ("biber", False, "biblatex backend, if a journal template uses biblatex"),
    ("texcount", False, "accurate word counts for journal limits (`tlmgr install texcount`)"),
]
OTHER_TOOLS = [
    ("git", True, "one repository per paper (commits after every stage)"),
    ("dot", False, "Graphviz diagrams"),
    ("mmdc", False, "Mermaid diagrams (npm @mermaid-js/mermaid-cli)"),
]
PKGS = ["numpy", "scipy", "sympy", "matplotlib", "seaborn", "pandas"]


def main() -> int:
    ok = True
    print(f"python  {sys.version.split()[0]}  ({sys.executable})")
    for pkg in PKGS:
        have = importlib.util.find_spec(pkg) is not None
        ok &= have
        print(f"  {'ok ' if have else 'MISSING':<18} python package {pkg}")
    for tool, required, why in TEX_TOOLS:
        where = latex.find_tool(tool)
        ok &= bool(where) or not required
        tag = "ok " if where else ("MISSING" if required else "absent (optional)")
        print(f"  {tag:<18} {tool:<10} {why}" + (f"  [{where}]" if where and not shutil.which(tool) else ""))
    for tool, required, why in OTHER_TOOLS:
        have = shutil.which(tool) is not None
        ok &= have or not required
        print(f"  {'ok ' if have else ('MISSING' if required else 'absent (optional)'):<18} {tool:<10} {why}")
    papers = core.list_papers()
    active = core.active_paper()
    print(f"\npapers ({len(papers)}), active: {active or '(none)'}")
    for p in papers:
        git = "git repo" if (core.papers_dir() / p / ".git").exists() else "NO git repo"
        print(f"  {'*' if p == active else ' '} {p:<24} {git}")
    if not ok:
        print("\nInstall missing pieces with scripts/setup.sh (Git Bash) or scripts/setup.ps1 (Windows); TeX: install "
              "TinyTeX or TeX Live (found automatically even when not on PATH).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
