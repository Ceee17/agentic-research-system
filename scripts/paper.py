"""./ra paper — the papers in this workspace (one folder + git repository each, under papers/).

  list                  all papers (* = active)
  current               the active paper's name
  new <name>            create papers/<name>/ (own git repo) and make it active; inside Claude Code only from a
                        fresh conversation (the /ra-init skill uses this)
  use <name>            HUMAN ONLY: make <name> the active paper
In chat the human types `/ra-init [...]`, `NEW PAPER <name>` or `PAPER <name>`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import core, papers  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra paper", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("current")
    s = sub.add_parser("new"); s.add_argument("name")
    s = sub.add_parser("use"); s.add_argument("name")
    a = ap.parse_args()

    if a.cmd == "list":
        print(papers.dumps_list())
        return 0
    if a.cmd == "current":
        slug = core.active_paper()
        print(slug or core.no_paper_message())
        return 0 if slug else 13
    if core.in_agent_session() and a.cmd == "use":
        print(f"Refused: switching to an existing paper is the human's decision.\n"
              f"Human: type `PAPER {a.name}` in the chat, or run this command in your own terminal.", file=sys.stderr)
        return 3
    # `new` inside Claude Code: the pre-bash hook allows it only from a fresh conversation (/ra-init)
    if a.cmd == "new":
        ok, msg = papers.create(a.name)
        if ok:
            core.set_active_paper(a.name)
            msg += f"; active paper is now '{a.name}'"
    else:
        if a.name not in core.list_papers():
            ok, msg = False, f"no paper '{a.name}' (existing: {', '.join(core.list_papers()) or 'none'})"
        else:
            core.set_active_paper(a.name)
            ok, msg = True, f"active paper is now '{a.name}'. Start a fresh Claude session (or /clear) before working on it."
    print(msg, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
