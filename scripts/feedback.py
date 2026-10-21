"""./ra feedback — collect and route human feedback (used by the apply-feedback skill).

  collect [--json] [--diff]          everything unprocessed: direct edits, `% @agent` comments, feedback files
  plan --scope S[,S] --items ID[,ID] --title T
                                     structural change: write gates/impact-<id>.md, mark affected stages
                                     stale, register the plan as awaiting human approval (then STOP)
  plans                              list impact plans
  done <feedback-file> --resolution T  archive a processed feedback file into feedback/done/ (+ log, commit)
  log --item ID --summary T [--scope S]  log a resolved item (comment / edit / plan step) and commit
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import core, feedbackcore, pipeline  # noqa: E402

PLAN_TEMPLATE = (".claude", "skills", "apply-feedback", "templates", "impact-plan.md")


def log_line(item: str, summary: str, scope: str | None = None) -> None:
    p = core.path("feedback", "log.md")
    if not p.exists():
        core.write_text(p, "# Feedback log\n\nEvery processed human feedback item (auto-appended by `./ra`).\n\n")
    core.append_text(p, f"- {core.now()} `{item}`" + (f" ({scope})" if scope else "") + f": {summary}\n")


def describe(it: dict) -> str:
    if it["id"].startswith("fb:"):
        return (f"{it['id']}  scope: {','.join(it['scopes']) or '(missing -> classify)'}\n"
                f"      change: {it['change'][:300]}\n      keep:   {it['keep'][:200] or '-'}")
    if it["id"].startswith("c:"):
        return f"{it['id']}  {it['file']}:{it['line']}  [scope tag: {it['scope'] or 'none'}]  \"{it['request']}\""
    return f"{it['id']}  {it['status']}" + (f"  hints: {'; '.join(it['hints'])}" if it["hints"] else "")


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra feedback", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("collect"); s.add_argument("--json", action="store_true"); s.add_argument("--diff", action="store_true")
    s = sub.add_parser("plan"); s.add_argument("--scope", required=True); s.add_argument("--items", default="")
    s.add_argument("--title", required=True); s.add_argument("--no-commit", action="store_true")
    sub.add_parser("plans")
    s = sub.add_parser("done"); s.add_argument("file"); s.add_argument("--resolution", required=True)
    s.add_argument("--no-commit", action="store_true")
    s = sub.add_parser("log"); s.add_argument("--item", required=True); s.add_argument("--summary", required=True)
    s.add_argument("--scope"); s.add_argument("--no-commit", action="store_true")
    a = ap.parse_args()
    st = pipeline.load_state()

    if a.cmd == "collect":
        c = feedbackcore.collect(st)
        if a.json:
            print(json.dumps(c, indent=2, ensure_ascii=False))
            return 0
        pend = sum(1 for g in c.values() for it in g if not it["in_plan"])
        print(f"== Unprocessed human feedback: {pend} item(s) ==")
        for title, key in (("[1] Direct edits to paper/*.tex (not yet registered)", "edits"),
                           ("[2] `% @agent` inline comments", "comments"), ("[3] Feedback files", "files")):
            items = c[key]
            print(f"{title}: {len(items)}")
            for it in items:
                print(f"  {'(in plan) ' if it['in_plan'] else ''}{describe(it)}")
                if key == "edits" and a.diff:
                    print("\n".join("      " + line for line in it["diff"].splitlines()[:80]))
        plans = {k: v for k, v in (st.get("impact_plans") or {}).items() if v["status"] in ("awaiting", "approved")}
        for pid, p in plans.items():
            print(f"Impact plan {pid}: {p['status']} [{','.join(p['scopes'])}] {p['title']} -> {', '.join(p['stages'])}")
        print("[4] LOCKED regions are enforced by hooks (nothing to process).")
        return 0

    if a.cmd == "plan":
        scopes = [x.strip() for x in a.scope.split(",") if x.strip()]
        items = [x.strip() for x in a.items.split(",") if x.strip()]
        known = {it["id"]: it for g in feedbackcore.collect(st).values() for it in g}
        unknown = [i for i in items if i not in known]
        if unknown:
            print(f"warning: unknown item id(s) {unknown} (see `./ra feedback collect`)", file=sys.stderr)
        try:
            pid, stages = pipeline.create_plan(scopes, items, a.title)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
        tpl = core.read_text(core.wpath(*PLAN_TEMPLATE)) or "# Impact plan {{id}}: {{title}}\n"
        details = "\n".join(f"- {describe(known[i])}" if i in known else f"- {i}" for i in items) or "- (none listed)"
        for k, v in {"id": pid, "title": a.title, "scopes": ", ".join(scopes), "stages": ", ".join(stages),
                     "items": details, "date": core.today()}.items():
            tpl = tpl.replace("{{" + k + "}}", v)
        rel = f"gates/impact-{pid}.md"
        core.write_text(core.path(rel), tpl)
        if not a.no_commit:
            core.git_commit_all(f"feedback: impact plan {pid} ({','.join(scopes)}) awaiting approval")
        print(f"impact plan {pid} registered; stages marked stale: {', '.join(stages)}\n"
              f"Fill in {rel} (what changes, what is kept, risks), then STOP: the human must type "
              f"`APPROVE {pid}` or `REJECT {pid}: <why>`.")
        return 0

    if a.cmd == "plans":
        for pid, p in (st.get("impact_plans") or {}).items():
            print(f"{pid} {p['status']:<9} [{','.join(p['scopes'])}] {p['title']} -> {', '.join(p['stages'])} ({p['file']})")
        return 0

    if a.cmd == "done":
        src = core.path("feedback", Path(a.file).name)
        if not src.exists():
            print(f"no such feedback file: {core.rel(src)}", file=sys.stderr)
            return 1
        core.append_text(src, f"\n\n---\n## Resolution (agent, {core.now()})\n{a.resolution}\n")
        dest = core.path("feedback", "done", f"{core.stamp()}-{src.name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        log_line(f"fb:{src.name}", a.resolution)
        if not a.no_commit:
            core.git_commit_all(f"feedback: processed {src.name}")
        print(f"archived -> {core.rel(dest)}")
        return 0

    if a.cmd == "log":
        log_line(a.item, a.summary, a.scope)
        if not a.no_commit:
            core.git_commit_all(f"feedback: {a.item} - {a.summary[:60]}")
        print("logged")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
