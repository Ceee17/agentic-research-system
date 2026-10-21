"""./ra compile — build paper/main.tex with latexmk into paper/build/ and summarise errors.

  --strict   undefined citations/references also fail (required for journal-format / revision)
Exit: 0 ok, 1 failed, 3 latexmk missing, 4 no paper/main.tex.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import latex  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra compile", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--main", default="main.tex")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()
    res = latex.compile_paper(a.main, strict=a.strict, timeout=a.timeout)
    print(latex.format_result(res))
    return {"ok": 0, "failed": 1, "missing": 3, "no-main": 4}[res["status"]]


if __name__ == "__main__":
    sys.exit(main())
