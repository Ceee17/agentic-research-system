"""./ra check-abstract — hard rule: the abstract contains no formulas of any kind.

Flags math mode, math/Greek macros and symbols, operators (= < > ^ _ + *), symbolic fractions (N/M, 7/8),
function or big-O notation, scientific notation, single-letter variables, and macros that may typeset math
(results macros are expanded first). Exit 1 if anything is found.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import rules  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra check-abstract", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    text = rules.abstract_text()
    if text is None:
        print("check-abstract: no abstract yet (paper/main.tex abstract or paper/sections/abstract.tex)")
        return 0
    v = rules.formula_violations(text)
    print(json.dumps(v, indent=2) if a.json else rules.format_abstract_report(v))
    return 1 if v else 0


if __name__ == "__main__":
    sys.exit(main())
