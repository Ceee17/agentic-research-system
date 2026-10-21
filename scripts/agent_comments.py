"""./ra comments — `% @agent: <request>` inline comments (feedback channel 2).

  list [--json]                         every open request with its id
  resolve <id> --note "what was done"   delete the comment line (after you made the change), log it, commit

Optional scope tag in the comment: `% @agent[claims]: ...` (wording|claims|novelty|figures|template|journal).
Structural requests go into an impact plan (`./ra feedback plan`) instead of being resolved directly.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import core, shadow, tex  # noqa: E402
from feedback import log_line  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra comments", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("resolve"); s.add_argument("id"); s.add_argument("--note", required=True)
    s.add_argument("--no-commit", action="store_true")
    a = ap.parse_args()
    items = tex.all_agent_comments()

    if a.cmd == "list":
        if a.json:
            print(json.dumps(items, indent=2, ensure_ascii=False))
        elif not items:
            print("no open `% @agent` comments")
        else:
            for c in items:
                print(f"{c['id']}  {c['file']}:{c['line']}  [{c['scope'] or 'untagged'}]  {c['request']}")
        return 0

    cid = a.id if a.id.startswith("c:") else f"c:{a.id}"
    match = [c for c in items if c["id"] == cid]
    if not match:
        print(f"no open comment with id {cid} (see `./ra comments list`)", file=sys.stderr)
        return 1
    c = match[0]
    if shadow.has_unregistered_change(c["file"]):
        print(f"{c['file']} has unregistered human edits: run `./ra edits accept {c['file']}` first", file=sys.stderr)
        return 1
    path = core.path(c["file"])
    raw = path.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    lines = core.norm_newlines(raw.decode("utf-8", errors="replace")).split("\n")
    idx = c["line"] - 1
    for r in tex.locked_regions("\n".join(lines)):
        if r["start"] - 1 <= idx <= r["end"] - 1:
            print("this comment is inside a LOCKED region; the agent may not edit it. Ask the human to move or "
                  "remove it (note it in the gate summary).", file=sys.stderr)
            return 1
    if c["code_before"]:
        lines[idx] = c["code_before"]
    else:
        del lines[idx]
    with open(path, "w", encoding="utf-8", newline=nl) as f:
        f.write("\n".join(lines))
    shadow.record(c["file"])
    log_line(cid, f"{c['file']}:{c['line']} \"{c['request']}\" -> {a.note}", c["scope"])
    if not a.no_commit:
        core.git_commit_all(f"feedback: resolve @agent comment {cid}")
    print(f"resolved {cid} ({c['file']}:{c['line']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
