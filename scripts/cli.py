"""Dispatcher behind the `./ra` launcher. Every workspace command goes through here.

Commands act on the ACTIVE paper (papers/<name>/); paths given to them may be paper-relative
(`experiments/x.py`) or workspace-relative (`papers/<name>/experiments/x.py`).
"""
from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
from ra import core  # noqa: E402

COMMANDS = {
    "paper": ("scripts/paper.py", "list papers / show the active one (switching and creating: human only)"),
    "state": ("scripts/state.py", "pipeline status, next action, start/complete stages, mark stale"),
    "lit": ("scripts/lit_search.py", "literature search: Semantic Scholar, arXiv, OpenAlex, Crossref; notes"),
    "fetch-bib": ("scripts/fetch_bib.py", "fetch verified BibTeX by DOI / arXiv id (the only way to add refs)"),
    "verify-bib": ("scripts/verify_bib.py", "citations: verified, <= 10 years old, justified (+ --online, --claims)"),
    "run": ("scripts/run_experiment.py", "run an experiment/derivation script and record it in results/manifest"),
    "results-tex": ("scripts/results_to_tex.py", "generate LaTeX macros for every number in results/"),
    "check-numbers": ("scripts/check_numbers.py", "every decimal/percentage in the paper must trace to results/"),
    "check-abstract": ("scripts/check_abstract.py", "hard rule: no formulas in the abstract"),
    "figs": (".claude/skills/figures/scripts/build_figures.py", "build all figures from figures/scripts, tikz, dot"),
    "compile": ("scripts/compile.py", "latexmk the paper with an error summary"),
    "export": ("scripts/export_paper.py", "Overleaf-ready zip + PDF in exports/"),
    "limits": (".claude/skills/journal-format/scripts/check_limits.py", "check journal limits (words, pages...)"),
    "template": (".claude/skills/intake/scripts/fetch_template.py", "download/install the official LaTeX template"),
    "diff": (".claude/skills/revision/scripts/make_diff.py", "latexdiff tracked-changes PDF against a git ref"),
    "feedback": ("scripts/feedback.py", "collect human feedback, create impact plans, archive processed items"),
    "edits": ("scripts/human_edits.py", "detect/accept direct human edits to paper/*.tex; learned patterns"),
    "comments": ("scripts/agent_comments.py", "list/resolve `% @agent:` inline comments"),
    "doctor": ("scripts/doctor.py", "check the toolchain (Python packages, TeX, latexdiff, graphviz...)"),
    "selftest": ("scripts/tests/run_tests.py", "run the workspace self-tests (hooks, rules, papers, export)"),
}
NO_PAPER_OK = {"paper", "doctor", "selftest"}
GIT_READONLY = {"status", "diff", "log", "show", "ls-files", "rev-parse", "blame", "shortlog", "describe"}


def usage() -> None:
    print("usage: ./ra <command> [args]\n")
    for name, (_, desc) in COMMANDS.items():
        print(f"  {name:<15} {desc}")
    print(f"  {'git':<15} read-only git in the active paper's repository (status, diff, log, show, ...)")
    print(f"  {'py':<15} run the workspace Python interpreter (e.g. ./ra py -c 'import sympy')")
    print(f"  {'hook':<15} (internal) Claude Code hook entry point")
    print(f"\nactive paper: {core.active_paper() or '(none)'}   papers: {', '.join(core.list_papers()) or '(none)'}")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        usage()
        return 0
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "hook":
        from ra import hooks
        return hooks.main(args)
    if cmd == "agy-hook":
        from ra import antigravity_hook
        return antigravity_hook.main(args)
    if cmd == "py":
        return subprocess.call([sys.executable, *args], cwd=os.getcwd())
    if cmd == "git":
        if not args or args[0] not in GIT_READONLY:
            print(f"./ra git runs read-only git in the active paper's repository: {', '.join(sorted(GIT_READONLY))}. "
                  "Commits happen through ./ra state complete / ./ra feedback / ./ra comments.", file=sys.stderr)
            return 2
        try:
            return subprocess.call(["git", *args], cwd=str(core.root()))
        except core.NoActivePaper as e:
            print(e, file=sys.stderr)
            return 13
    if cmd not in COMMANDS:
        print(f"ra: unknown command '{cmd}'\n", file=sys.stderr)
        usage()
        return 2
    if cmd not in NO_PAPER_OK and not core.active_paper():
        print(core.no_paper_message(), file=sys.stderr)
        return 13
    target = ROOT / COMMANDS[cmd][0]
    sys.argv = [str(target), *args]
    try:
        runpy.run_path(str(target), run_name="__main__")
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    except core.NoActivePaper as e:
        print(e, file=sys.stderr)
        return 13
    return 0


if __name__ == "__main__":
    sys.exit(main())
