"""./ra edits — direct human edits to paper/*.tex (feedback channel 1).

  detect [--json] [--diff]     files changed since the agent last wrote them (shadow copies / git HEAD)
  accept [FILE...] [--note T]  register the human's edits as the new baseline (never reverts them);
                               archives the diffs to feedback/human-edits/ and updates edit-pattern stats
  patterns [--min N]           recurring human substitutions (candidates for style-guide.md rules)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import core, shadow  # noqa: E402

PATTERNS = ("feedback", "edit-patterns.json")


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra edits", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("detect"); s.add_argument("--json", action="store_true"); s.add_argument("--diff", action="store_true")
    s = sub.add_parser("accept"); s.add_argument("files", nargs="*"); s.add_argument("--note")
    s = sub.add_parser("patterns"); s.add_argument("--min", type=int, default=2)
    a = ap.parse_args()

    if a.cmd == "detect":
        ch = shadow.changed()
        if a.json:
            print(json.dumps(ch, indent=2, ensure_ascii=False))
            return 0
        if not ch:
            print("no unregistered human edits in paper/")
            return 0
        for c in ch:
            print(f"{c['file']}: {c['status']}" + (f"  (hints: {'; '.join(c['hints'])})" if c["hints"] else ""))
            if a.diff:
                print(c["diff"])
        if not a.diff:
            print("(use --diff to see the changes)")
        return 0

    if a.cmd == "accept":
        ch = shadow.changed()
        wanted = {core.rel(core.resolve_arg(f)) for f in a.files}
        todo = [c for c in ch if not wanted or c["file"] in wanted]
        if not todo:
            print("nothing to accept")
            return 0
        stamp = core.stamp()
        archive = core.path("feedback", "human-edits", f"{stamp}.diff")
        header = f"# human edits registered {core.now()}" + (f" - {a.note}" if a.note else "") + "\n"
        core.write_text(archive, header + "\n".join(c["diff"] for c in todo))
        pats = core.read_json(core.path(*PATTERNS), {"pairs": {}}) or {"pairs": {}}
        for c in todo:
            if c["status"] == "modified":
                base = shadow.baseline(c["file"]) or ""
                cur = core.read_text(core.path(c["file"])) or ""
                for old, new in shadow.word_substitutions(base, cur):
                    k = f"{old} -> {new}" if new else f"{old} -> (deleted)"
                    ent = pats["pairs"].setdefault(k, {"count": 0, "files": []})
                    ent["count"] += 1
                    ent["last"] = core.now()
                    if c["file"] not in ent["files"]:
                        ent["files"].append(c["file"])
            shadow.record(c["file"])
        core.write_json(core.path(*PATTERNS), pats)
        print(f"registered {len(todo)} file(s); diffs archived in {core.rel(archive)}")
        for c in todo:
            print(f"  {c['file']} ({c['status']})")
        return 0

    if a.cmd == "patterns":
        pats = (core.read_json(core.path(*PATTERNS), {"pairs": {}}) or {}).get("pairs", {})
        guide = (core.read_text(core.path("style-guide.md")) or "").lower()
        rows = sorted(((v["count"], k) for k, v in pats.items() if v["count"] >= a.min), reverse=True)
        if not rows:
            print(f"no human substitution seen >= {a.min} times yet")
        for n, k in rows:
            old = k.split(" -> ")[0].lower()
            known = " (already in style-guide.md)" if old and old in guide else ""
            print(f"{n:>3}x  {k}{known}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
