"""./ra export — Overleaf-ready project zip + PDFs of the active paper, in exports/.

  exports/<paper>-overleaf.zip   upload to Overleaf (New Project > Upload Project); compiler pdfLaTeX
  exports/<paper>.pdf            the manuscript, compiled from the zip itself (when TeX is installed)
  --no-pdf                       only build and validate the zip
Runs automatically when drafting, citation-verify, journal-format, self-review and revision complete.
Exit 1 if the export is not self-contained or does not compile.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import export  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra export", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()
    res = export.build(compile_pdf=not a.no_pdf)
    print(export.format_result(res))
    return 0 if res["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
