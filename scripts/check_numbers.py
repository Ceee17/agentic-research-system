"""./ra check-numbers — every decimal/percentage in paper/*.tex must trace to a file in results/.

Exit 1 if any number is untraceable. Use generated macros (`./ra results-tex`) in prose.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import numbers  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra check-numbers", description=__doc__)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    items = numbers.untraceable()
    print(json.dumps(items, indent=2) if a.json else numbers.format_report(items))
    return 1 if items else 0


if __name__ == "__main__":
    sys.exit(main())
