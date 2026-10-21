"""./ra fetch-bib — the ONLY way references enter paper/references.bib.

  add <id> [<id>...] [--key K] [--force] [--prefer-arxiv]
        id = DOI (10.xxxx/..., doi:..., https://doi.org/...), arXiv id (2101.00001, arXiv:..., URL),
             or Semantic Scholar id (S2:<paperId>, CorpusId:<n>)
        Published DOI is preferred for arXiv papers that have one (eprint fields are kept).
  list | show <key> | remove <key>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import bib, bibcheck, pipeline, refs, rules  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra fetch-bib", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add"); s.add_argument("ids", nargs="+"); s.add_argument("--key")
    s.add_argument("--force", action="store_true"); s.add_argument("--prefer-arxiv", action="store_true")
    sub.add_parser("list")
    s = sub.add_parser("show"); s.add_argument("key")
    s = sub.add_parser("remove"); s.add_argument("key")
    a = ap.parse_args()

    if a.cmd == "add":
        if not pipeline.intake_confirmed():
            print("refused: intake is not complete/confirmed (see `./ra state next`)", file=sys.stderr)
            return 1
        if a.key and len(a.ids) > 1:
            print("--key can only be used with a single id", file=sys.stderr)
            return 2
        failed = 0
        for ident in a.ids:
            try:
                key = refs.add(ident, key=a.key, force=a.force, prefer_arxiv=a.prefer_arxiv)
                led = bibcheck.load_ledger()["entries"].get(key, {})
                print(f"OK  {key:<28} {led.get('year') or ''} {(led.get('title') or '')[:80]}  <- {ident}")
                warn = rules.age_note(rules.parse_year(led.get("year")))
                if warn:
                    print(f"    WARNING: {warn}")
            except refs.FetchError as e:
                failed += 1
                print(f"ERR {ident}: {e}", file=sys.stderr)
        return 1 if failed else 0

    if a.cmd == "list":
        led = bibcheck.load_ledger()["entries"]
        for e in bibcheck.load_bib():
            ok = "verified" if e["key"] in led and led[e["key"]]["fingerprint"] == bib.fingerprint(e) else "UNVERIFIED"
            ident = e["fields"].get("doi") or e["fields"].get("eprint") or "-"
            print(f"{e['key']:<28} {ok:<10} {e['fields'].get('year', ''):<5} {ident}")
        return 0

    if a.cmd == "show":
        e = bib.by_key(bibcheck.load_bib()).get(a.key)
        if not e:
            print(f"no entry {a.key}", file=sys.stderr)
            return 1
        print(e["raw"])
        print(json.dumps(bibcheck.load_ledger()["entries"].get(a.key, {}), indent=2, ensure_ascii=False))
        return 0

    if a.cmd == "remove":
        if not refs.remove(a.key):
            print(f"no entry {a.key}", file=sys.stderr)
            return 1
        print(f"removed {a.key}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
