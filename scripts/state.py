"""./ra state — pipeline status and transitions.

  status [--json]                     full status table
  next [--json|--field F]             what to do now (exit 0 RUN, 10 human needed, 11 intake missing, 12 done)
  check-intake [--confirmed]          exit 0 if project.json is complete (and confirmed), else list missing fields
  start <stage>                       begin a stage (checks intake, dependencies, gates, pending feedback)
  complete <stage> [--note T]         validate outputs + checks, mark done, open the next gate, git commit
  stale (--scope S | --stage X...)    mark stages stale after a change (--reason required)
  show <stage> | log [-n N] | commit-of <stage> | init [--force]
  approve <gate|plan> [--note T]      HUMAN ONLY (refused inside Claude Code; use `APPROVE <gate>` in chat)
  reject <gate|plan> --note T         HUMAN ONLY
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import core, pipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra state", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("next"); s.add_argument("--json", action="store_true"); s.add_argument("--field")
    s = sub.add_parser("check-intake"); s.add_argument("--confirmed", action="store_true")
    s = sub.add_parser("start"); s.add_argument("stage")
    s = sub.add_parser("complete"); s.add_argument("stage"); s.add_argument("--note")
    s.add_argument("--no-commit", action="store_true")
    s = sub.add_parser("stale"); s.add_argument("--scope"); s.add_argument("--stage", action="append")
    s.add_argument("--reason", required=True)
    s = sub.add_parser("show"); s.add_argument("stage")
    s = sub.add_parser("log"); s.add_argument("-n", type=int, default=20)
    s = sub.add_parser("commit-of"); s.add_argument("stage")
    s = sub.add_parser("init"); s.add_argument("--force", action="store_true")
    for name in ("approve", "reject"):
        s = sub.add_parser(name); s.add_argument("target"); s.add_argument("--note")
        s.add_argument("--force", action="store_true")
    a = ap.parse_args()

    if a.cmd == "status":
        st = pipeline.load_state()
        if a.json:
            print(json.dumps({"state": st, "project": pipeline.load_project(), "next": pipeline.next_action(st)}, indent=2))
        else:
            print(pipeline.status_text(st))
        return 0

    if a.cmd == "next":
        nxt = pipeline.next_action()
        if a.field:
            print(nxt.get(a.field) or "")
        elif a.json:
            print(json.dumps(nxt, indent=2))
        else:
            print(f"{nxt['action']}: {nxt['detail']}")
        return nxt["code"]

    if a.cmd == "check-intake":
        miss = pipeline.intake_missing()
        if miss:
            print("INTAKE INCOMPLETE - missing: " + ", ".join(miss))
            return 1
        if a.confirmed and not pipeline.intake_confirmed():
            print("INTAKE NOT CONFIRMED - the human must approve gates/gate0_intake.md (`APPROVE intake`).")
            return 1
        print("intake OK" + (" and confirmed" if pipeline.intake_confirmed() else " (not yet confirmed)"))
        return 0

    if a.cmd == "start":
        ok, problems = pipeline.start(a.stage)
        if not ok:
            print(f"cannot start '{a.stage}':\n  - " + "\n  - ".join(problems), file=sys.stderr)
            return 1
        print(f"started {a.stage}. Follow .claude/skills/{pipeline.load_state()['stages'][a.stage]['skill']}/SKILL.md")
        return 0

    if a.cmd == "complete":
        ok, problems, head = pipeline.complete(a.stage, commit=not a.no_commit, note=a.note)
        if not ok:
            print(f"cannot complete '{a.stage}':\n  - " + "\n  - ".join(problems), file=sys.stderr)
            return 1
        msg = f"{a.stage}: done" + (f" (commit {head[:8]})" if head else "")
        st = pipeline.load_state()
        g = pipeline.gate_after(st, a.stage)
        if g:
            msg += f"\nGATE {g} is now awaiting the human. Write/refresh {st['gates'][g]['file']} and STOP."
        print("\n".join([msg] + problems))
        return 0

    if a.cmd == "stale":
        ok, msg = pipeline.stale(scope=a.scope, stages=a.stage, reason=a.reason)
        print(msg, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    if a.cmd == "show":
        st = pipeline.load_state()
        if a.stage not in st["stages"]:
            print(f"unknown stage {a.stage}", file=sys.stderr)
            return 1
        print(json.dumps(st["stages"][a.stage], indent=2))
        return 0

    if a.cmd == "log":
        for h in pipeline.load_state().get("history", [])[-a.n:]:
            extra = {k: v for k, v in h.items() if k not in ("at", "event")}
            print(f"{h['at']}  {h['event']:<9} {json.dumps(extra, ensure_ascii=False)}")
        return 0

    if a.cmd == "commit-of":
        if not core.is_git_repo():
            print("not a git repository", file=sys.stderr)
            return 1
        r = core.git("log", "-1", "--format=%H", f"--grep=^stage({a.stage}): complete")
        if not r.stdout.strip():
            print(f"no commit found for stage {a.stage}", file=sys.stderr)
            return 1
        print(r.stdout.strip())
        return 0

    if a.cmd == "init":
        p = core.path("state.json")
        if p.exists() and not a.force:
            print("state.json exists (use --force to reset it)", file=sys.stderr)
            return 1
        pipeline.save_state(pipeline.default_state(), "init")
        print("state.json initialised")
        return 0

    if a.cmd in ("approve", "reject"):
        if core.in_agent_session():
            print("Refused: approvals are human-only and this command is running inside Claude Code.\n"
                  f"Human: type `{a.cmd.upper()} {a.target} <note>` in the chat, or run this in your own terminal.",
                  file=sys.stderr)
            return 3
        if a.cmd == "reject" and not a.note:
            print("reject needs --note explaining what to change", file=sys.stderr)
            return 1
        fn = pipeline.approve if a.cmd == "approve" else pipeline.reject
        kwargs = {"force": a.force} if a.cmd == "approve" else {}
        ok, msg = fn(a.target, by="human (cli)", note=a.note, **kwargs)
        print(msg, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
