"""./ra selftest — workspace self-tests on throwaway copies (the real workspace is never touched).

Covers: hook guardrails (pre-edit, pre-read, pre-bash, pre-skill, prompt, post-edit, stop, session-start),
paper isolation and one-paper-per-session binding, the hard rules (no formulas in the abstract, reference
age, no AI statement / attribution), verify_bib, the state machine and gates, the feedback channels,
number tracing, results integrity and the Overleaf export. Network is not required; TeX is optional.
  ./ra selftest [group ...]     groups: hooks papers rules bib state feedback export
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SRC / "scripts"))
from ra import bib, latex  # noqa: E402  (pure helpers; workspace copies are exercised via subprocesses)
PY = sys.executable
RESULTS: list[tuple[str, bool]] = []
FRAMEWORK = ["ra", "CLAUDE.md", "README.md", "requirements.txt", "scripts", ".claude"]
YEAR = dt.date.today().year


# ------------------------------------------------------------------ helpers
def env_for(extra=None):
    e = dict(os.environ, PYTHONUTF8="1", RA_LATEX="off")
    for k in ("CLAUDECODE", "RA_PAPER", "RA_WORKSPACE", "RA_PROJECT_DIR"):
        e.pop(k, None)
    e.update(extra or {})
    return e


def run(ws: Path, *args, stdin=None, env=None):
    r = subprocess.run([PY, str(ws / "scripts" / "cli.py"), *args], cwd=str(ws), input=stdin, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env_for(env))
    return r.returncode, r.stdout, r.stderr


def fresh(paper: str = "test") -> Path:
    """Copy of the framework with one new paper (active)."""
    d = Path(tempfile.mkdtemp(prefix="ra-selftest-"))
    for name in FRAMEWORK:
        src = SRC / name
        if src.is_dir():
            ignore = shutil.ignore_patterns("__pycache__", "settings*.json*") if name == ".claude" else \
                shutil.ignore_patterns("__pycache__")
            shutil.copytree(src, d / name, ignore=ignore)
        else:
            shutil.copy2(src, d / name)
    if paper:
        code, out, err = run(d, "paper", "new", paper)
        assert code == 0, out + err
    return d


def active(ws: Path) -> str:
    return (ws / ".ra" / "active-paper").read_text().strip()


def pp(ws: Path, rel: str = "") -> Path:
    return ws / "papers" / active(ws) / rel


def hook(ws: Path, event: str, payload: dict, env=None, sid="S1"):
    payload = dict(payload)
    payload.setdefault("session_id", sid)
    payload.setdefault("cwd", str(ws))
    return run(ws, "hook", event, stdin=json.dumps(payload), env=env)


def edit(path: Path, old, new, tool="Edit"):
    return {"tool_name": tool, "tool_input": {"file_path": str(path), "old_string": old, "new_string": new}}


def write(path: Path, content):
    return {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": content}}


def read(path: Path):
    return {"tool_name": "Read", "tool_input": {"file_path": str(path)}}


def bash(cmd, tool="Bash"):
    return {"tool_name": tool, "tool_input": {"command": cmd}}


def put(path: Path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"\n      {str(detail)[:700]}"))


def set_state(ws, done=(), gates=(), confirmed=None):
    st = json.loads(pp(ws, "state.json").read_text())
    for s in done:
        st["stages"][s]["status"] = "done"
    for g in gates:
        st["gates"][g].update(approved=True, status="approved")
    pp(ws, "state.json").write_text(json.dumps(st, indent=2))
    if confirmed is not None:
        pj = json.loads(pp(ws, "project.json").read_text())
        pj["journal"] = {"name": "Journal of Test Theory", "guidelines_url": "https://example.org/guide",
                         "article_type": "full paper"}
        pj["intake_confirmed"] = confirmed
        pp(ws, "project.json").write_text(json.dumps(pj, indent=2))


def ready_for_paper(ws):
    set_state(ws, done=("intake", "topic-fit-check", "literature-review", "topic-selection"),
              gates=("gate1_topic",), confirmed=True)


def bib_entry(key, year, doi):
    return f"@article{{{key},\n  author = {{Doe, Jane}},\n  title = {{Title {key}}},\n  year = {{{year}}},\n  doi = {{{doi}}},\n}}"


def verified_bib(ws, entries: list[tuple[str, int, str]], abstracts: dict | None = None):
    """Write references.bib + a ledger as ./ra fetch-bib would (entries: key, year, doi)."""
    text = "\n\n".join(bib_entry(*e) for e in entries) + "\n"
    ledger = {"version": 1, "entries": {}}
    for e in bib.parse(text):
        ledger["entries"][e["key"]] = {"doi": e["fields"]["doi"], "fingerprint": bib.fingerprint(e),
                                       "title": e["fields"]["title"], "year": e["fields"]["year"],
                                       "abstract": (abstracts or {}).get(e["key"])}
    put(pp(ws, "paper/references.bib"), text)
    pp(ws, "paper/references.verified.json").write_text(json.dumps(ledger))


# ------------------------------------------------------------------ hooks (single paper)
def test_hooks():
    ws = fresh()
    P = lambda rel="": pp(ws, rel)  # noqa: E731
    code, _, err = hook(ws, "pre-skill", {"tool_name": "Skill", "tool_input": {"skill": "literature-review"}})
    check("hook pre-skill: stage skill blocked before intake", code == 2 and "journal.name" in err, err)
    code, _, _ = hook(ws, "pre-skill", {"tool_name": "Skill", "tool_input": {"skill": "intake"}})
    check("hook pre-skill: intake skill allowed", code == 0)
    code, _, err = hook(ws, "pre-edit", write(P("paper/sections/intro.tex"), "x"))
    check("hook pre-edit: paper write blocked before intake", code == 2 and "intake" in err, err)
    code, out, _ = hook(ws, "prompt", {"prompt": "continue"})
    check("hook prompt: missing intake fields surfaced (with the paper name)", code == 0 and "journal.name" in out
          and "paper: test" in out, out)
    pj = json.loads(P("project.json").read_text())
    pj["journal"] = {"name": "J", "guidelines_url": "https://x", "article_type": "letter"}
    code, _, _ = hook(ws, "pre-edit", write(P("project.json"), json.dumps(pj)))
    check("hook pre-edit: filling project.json fields allowed", code == 0)
    pj["intake_confirmed"] = True
    code, _, err = hook(ws, "pre-edit", write(P("project.json"), json.dumps(pj)))
    check("hook pre-edit: agent cannot set intake_confirmed", code == 2 and "APPROVE intake" in err, err)
    for rel, word in [("state.json", "./ra state"), ("paper/references.bib", "fetch-bib"), ("results/x/m.json", "./ra run"),
                      ("reviews/external/round-1/r1.md", "never be altered"), ("figures/fig1.pdf", "./ra figs"),
                      ("feedback/new.md", "inbox"), ("templates/x/a.cls", "pristine"), ("exports/x.zip", "./ra export"),
                      ("CLAUDE.md", "pointer"), (".git/config", "git repository")]:
        code, _, err = hook(ws, "pre-edit", write(P(rel), "x"))
        check(f"hook pre-edit: paper {rel} protected", code == 2 and word in err, err)
    for rel, word in [(".claude/settings.json", "human-owned"), ("scripts/ra/hooks.py", "human-owned"),
                      ("CLAUDE.md", "human-owned"), ("README.md", "human-owned"), ("notes.md", "framework only")]:
        code, _, err = hook(ws, "pre-edit", write(ws / rel, "x"))
        check(f"hook pre-edit: workspace {rel} protected", code == 2 and word in err, err)
    pj["intake_confirmed"] = False
    P("project.json").write_text(json.dumps(pj))
    code, out, _ = hook(ws, "prompt", {"prompt": "APPROVE intake"})
    check("hook prompt: APPROVE intake refused until intake stages are done", "NOT recorded" in out, out)
    set_state(ws, done=("intake", "topic-fit-check"))
    code, out, _ = hook(ws, "prompt", {"prompt": "Looks good.\nAPPROVE intake - go ahead"})
    confirmed = json.loads(P("project.json").read_text())["intake_confirmed"]
    check("hook prompt: APPROVE intake recorded by the human channel", confirmed and "recorded" in out, out)
    check("hook prompt: approval logged as (human) decision", "(human)" in P("decisions.md").read_text())
    code, out, _ = hook(ws, "prompt", {"prompt": "APPROVE gate1"})
    check("hook prompt: gate1 cannot be approved before topic-selection", "NOT recorded" in out, out)
    code, _, err = hook(ws, "pre-skill", {"tool_name": "Skill", "tool_input": {"skill": "drafting"}})
    check("hook pre-skill: drafting blocked before gate1", code == 2 and "Gate 1" in err, err)
    code, _, err = hook(ws, "pre-edit", write(P("experiments/sim.py"), "x"))
    check("hook pre-edit: experiments/ blocked before gate1", code == 2 and "Gate 1" in err, err)
    code, _, _ = hook(ws, "pre-edit", write(P("literature/papers/a.md"), "note"))
    check("hook pre-edit: literature notes allowed after intake", code == 0)
    ready_for_paper(ws)
    code, _, _ = hook(ws, "pre-skill", {"tool_name": "Skill", "tool_input": {"skill": "drafting"}})
    check("hook pre-skill: drafting allowed after gate1", code == 0)
    code, _, err = hook(ws, "pre-skill", {"tool_name": "Skill", "tool_input": {"skill": "revision"}})
    check("hook pre-skill: revision blocked before gate2", code == 2, err)
    pj = json.loads(P("project.json").read_text())
    pj2 = json.loads(json.dumps(pj)); pj2["journal"]["name"] = "Other Journal"
    code, _, err = hook(ws, "pre-edit", write(P("project.json"), json.dumps(pj2)))
    check("hook pre-edit: journal change blocked while confirmed", code == 2 and "scope journal" in err, err)

    # LOCKED regions
    tex = "Intro text.\n% LOCKED-START\nThe main theorem, as the human wants it.\n% LOCKED-END\nMore text.\n"
    put(P("paper/sections/intro.tex"), tex)
    f = P("paper/sections/intro.tex")
    code, _, err = hook(ws, "pre-edit", edit(f, "as the human wants it", "improved"))
    check("hook pre-edit: edit inside LOCKED region blocked", code == 2 and "LOCKED" in err, err)
    code, _, err = hook(ws, "pre-edit", edit(f, "% LOCKED-END\n", ""))
    check("hook pre-edit: removing a LOCK marker blocked", code == 2, err)
    code, _, err = hook(ws, "pre-edit", write(f, "Intro text.\nMore text.\n"))
    check("hook pre-edit: Write that drops locked text blocked", code == 2, err)
    code, _, err = hook(ws, "pre-edit", edit(f, "More text.", "More careful text."))
    check("hook pre-edit: edit outside LOCKED region allowed", code == 0, err)
    code, _, err = hook(ws, "pre-edit", edit(f, "Intro text.", "Intro.\n% @agent: todo"))
    check("hook pre-edit: agent cannot add % @agent comments", code == 2 and "@agent" in err, err)
    code, _, err = hook(ws, "pre-edit", edit(f, "More text.", "More 0.5 text. % @num-ok"))
    check("hook pre-edit: agent cannot add % @num-ok", code == 2, err)
    hook(ws, "session-start", {"source": "startup"})
    put(f, tex.replace("as the human wants it", "tampered"))
    code, _, err = hook(ws, "stop", {"stop_hook_active": False})
    check("hook stop: LOCKED tampering detected at end of turn", code == 2 and "LOCKED" in err, err)
    code, out, _ = hook(ws, "stop", {"stop_hook_active": True})
    check("hook stop: no loop when stop_hook_active (warns user)", code == 0 and "systemMessage" in out, out)
    code, _, err = hook(ws, "pre-edit", edit(f, "tampered", "as the human wants it"))
    check("hook pre-edit: restoring the snapshot of a LOCKED region allowed", code == 0, err)

    # unregistered human edits are never overwritten
    m = P("paper/sections/model.tex")
    put(m, "We utilize a model.\n")
    hook(ws, "post-edit", write(m, "We utilize a model.\n"))
    put(m, "We use a model.\n")
    code, _, err = hook(ws, "pre-edit", edit(m, "We use", "We employ"))
    check("hook pre-edit: file with unregistered human edits blocked", code == 2 and "edits accept" in err, err)
    run(ws, "edits", "accept")
    code, _, err = hook(ws, "pre-edit", edit(m, "a model", "a simple model"))
    check("hook pre-edit: allowed after edits are registered", code == 0, err)

    # (human) decisions immutable
    put(P("decisions.md"), "# Decisions\n\n## D-001 (human) 2026-01-01 — Scope\n- Decision: discrete time only\n")
    old = "discrete time only"
    code, _, err = hook(ws, "pre-edit", edit(P("decisions.md"), old, "continuous time too"))
    check("hook pre-edit: (human) decision cannot be changed", code == 2 and "(human)" in err, err)
    code, _, _ = hook(ws, "pre-edit", edit(P("decisions.md"), old, old + "\n\n## D-002 (agent) 2026-01-02 — Notation\n- x"))
    check("hook pre-edit: appending an agent decision allowed", code == 0)

    # post-edit: verify_bib + latexmk
    put(P("paper/main.tex"), "\\documentclass{article}\\begin{document}Claim \\cite{nobody2020}.\\end{document}\n")
    code, _, err = hook(ws, "post-edit", write(P("paper/main.tex"), ""))
    check("hook post-edit: unknown citation reported (exit 2)", code == 2 and "MISSING" in err, err)
    put(P("paper/main.tex"), "\\documentclass{article}\\begin{document}No cites.\\end{document}\n")
    code, _, err = hook(ws, "post-edit", write(P("paper/main.tex"), ""))
    check("hook post-edit: clean paper passes", code == 0, err)
    fake = ws / "fakebin"
    fake.mkdir()
    if os.name == "nt":
        (fake / "latexmk.bat").write_text(
            "@echo off\r\nmkdir build 2>nul\r\necho ./sections/intro.tex:3: Undefined control sequence.> build\\main.log\r\n"
            "exit /b 1\r\n")
    else:
        p = fake / "latexmk"
        p.write_text("#!/bin/sh\nmkdir -p build\nprintf './sections/intro.tex:3: Undefined control sequence.\\n' "
                     "> build/main.log\nexit 1\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    path_env = {"PATH": str(fake) + os.pathsep + os.environ.get("PATH", ""), "RA_LATEX": "auto"}
    code, _, err = hook(ws, "post-edit", write(P("paper/main.tex"), ""), env=path_env)
    check("hook post-edit: latexmk failure reported with file:line", code == 2 and "intro.tex:3" in err, err)

    # pre-bash (paper-relative and workspace-relative forms)
    root = str(ws)
    cases = [
        ("./ra state approve gate1", 2), ("python scripts/state.py approve intake", 2),
        ("sed -i 's/a/b/' papers/test/paper/sections/intro.tex", 2), ("echo hi > papers/test/paper/main.tex", 2),
        ("cp /tmp/x.tex papers/test/paper/sections/intro.tex", 2), ("git -C papers/test checkout -- paper/main.tex", 2),
        ("git -C papers/test reset --hard HEAD", 2), ("git -C papers/test push origin main", 2),
        ("git -C papers/test stash", 2), ("git -C papers/test commit --amend -m x", 2),
        ("echo '{}' > papers/test/state.json", 2), ("./ra py -c \"open('papers/test/state.json','w').write('{}')\"", 2),
        ("rm -rf papers/test/paper", 2), ("rm -rf papers", 2),
        ("cat >> papers/test/paper/references.bib <<EOF\n@article{x,}\nEOF", 2),
        (f"echo x > \"{root}/papers/test/results/run/metrics.json\"", 2), ("mv papers/test/results/a papers/test/results/b", 2),
        ("sed -i 's/x/y/' scripts/ra/hooks.py", 2), ("echo x > CLAUDE.md", 2),
        ("RA_PAPER=other ./ra state status", 2), ("RA_LATEX=off ./ra state complete drafting", 2),
        ("./ra paper use other", 2), ("./ra paper new other", 2),
        ("git -C papers/test commit -m 'x\n\nCo-Authored-By: Claude <noreply@anthropic.com>'", 2),
        ("cat papers/test/paper/main.tex", 0), ("./ra lit search \"graph dynamics\" --save q1", 0),
        ("./ra git status && ./ra git diff", 0), ("./ra run experiments/sim.py --seed 0", 0),
        ("grep -n cite papers/test/paper/sections/*.tex | head", 0), ("ls papers", 0),
        ("git -C papers/test add -A && git -C papers/test commit -m 'stage done'", 0), ("./ra state complete drafting", 0),
        ("./ra paper list", 0),
    ]
    for cmd, want in cases:
        code, _, err = hook(ws, "pre-bash", bash(cmd))
        check(f"hook pre-bash: {'block' if want else 'allow'} `{cmd[:55]}`", code == want, err)
    for cmd in ("Move-Item .claude/settings.json .claude/x.json", "Set-Content -Path papers/test/state.json -Value '{}'",
                "Remove-Item -Recurse papers/test/paper"):
        code, _, err = hook(ws, "pre-bash", bash(cmd, tool="PowerShell"))
        check(f"hook pre-bash (PowerShell): block `{cmd[:50]}`", code == 2, err)
    code, out, _ = hook(ws, "session-start", {"source": "startup"})
    check("hook session-start: prints active paper and pipeline status", code == 0 and "ACTIVE PAPER: test" in out
          and "Stages:" in out, out)
    shutil.rmtree(ws, ignore_errors=True)


# ------------------------------------------------------------------ papers: isolation + sessions
def test_papers():
    ws = fresh()
    code, out, err = run(ws, "paper", "new", "other", env={"CLAUDECODE": "1"})
    check("paper: `paper new` works inside Claude Code (the hook gates it)", code == 0 and active(ws) == "other",
          out + err)
    code, _, err = run(ws, "paper", "use", "test", env={"CLAUDECODE": "1"})
    check("paper: `paper use` refused inside Claude Code", code == 3 and "human" in err, err)
    check("paper: new paper has its own git repository", (ws / "papers/other/.git").exists() or not shutil.which("git"))
    check("paper: scaffold has state, project, style guide with workspace rules",
          (ws / "papers/other/state.json").exists() and "no formulas" in (ws / "papers/other/style-guide.md").read_text())
    run(ws, "paper", "use", "test")
    check("paper: `paper use` switches the active paper", active(ws) == "test")
    code, out, _ = run(ws, "paper", "list")
    check("paper: list marks the active paper", "* test" in out and "other" in out, out)
    t, o = ws / "papers/test", ws / "papers/other"
    ready_for_paper(ws)
    # reads / searches
    code, _, err = hook(ws, "pre-read", read(o / "project.json"))
    check("isolation: Read of another paper blocked", code == 2 and "isolated" in err, err)
    code, _, _ = hook(ws, "pre-read", read(t / "project.json"))
    check("isolation: Read of the active paper allowed", code == 0)
    code, _, _ = hook(ws, "pre-read", read(ws / ".claude/skills/drafting/SKILL.md"))
    check("isolation: Read of framework files allowed", code == 0)
    for payload, want, label in [
        ({"tool_name": "Glob", "tool_input": {"pattern": "**/*.tex"}}, 2, "Glob **/*.tex from root"),
        ({"tool_name": "Glob", "tool_input": {"pattern": "papers/*/paper/*.tex"}}, 2, "Glob papers/*/..."),
        ({"tool_name": "Glob", "tool_input": {"pattern": "papers/test/paper/*.tex"}}, 0, "Glob scoped to active paper"),
        ({"tool_name": "Glob", "tool_input": {"pattern": ".claude/skills/*/SKILL.md"}}, 0, "Glob framework"),
        ({"tool_name": "Glob", "tool_input": {"pattern": "*.md"}}, 0, "Glob root-level names"),
        ({"tool_name": "Grep", "tool_input": {"pattern": "theorem"}}, 2, "Grep from root"),
        ({"tool_name": "Grep", "tool_input": {"pattern": "x", "glob": "*.tex"}}, 2, "Grep root with basename glob"),
        ({"tool_name": "Grep", "tool_input": {"pattern": "x", "path": str(t)}}, 0, "Grep in active paper"),
        ({"tool_name": "Grep", "tool_input": {"pattern": "x", "path": str(o)}}, 2, "Grep in other paper"),
        ({"tool_name": "Grep", "tool_input": {"pattern": "x", "path": str(ws / "scripts")}}, 0, "Grep in scripts"),
    ]:
        code, _, err = hook(ws, "pre-read", payload)
        check(f"isolation: {'block' if want else 'allow'} {label}", code == want, err)
    code, _, err = hook(ws, "pre-edit", write(o / "paper/x.tex", "x"))
    check("isolation: write into another paper blocked", code == 2 and "isolated" in err, err)
    for cmd, want in [("cat papers/other/paper/main.tex", 2), ("cat papers/*/project.json", 2),
                      ("grep -rn foo .", 2), ("grep -rn foo", 2), ("rg foo", 2), ("find . -name '*.tex'", 2),
                      ("ls -R papers", 2), ("grep -rn foo papers/test/paper", 0),
                      ("cd papers/test && grep -rn foo .", 0), ("rg foo papers/test/literature", 0),
                      ("grep -rn hooks scripts", 0), ("find papers/test -name '*.md'", 0)]:
        code, _, err = hook(ws, "pre-bash", bash(cmd))
        check(f"isolation: pre-bash {'block' if want else 'allow'} `{cmd}`", code == want, err)

    # one paper per conversation
    hook(ws, "session-start", {"source": "startup"}, sid="A")
    hook(ws, "pre-read", read(t / "project.json"), sid="A")                      # A has now worked on 'test'
    code, out, _ = hook(ws, "prompt", {"prompt": "PAPER other"}, sid="A")
    check("session: a conversation that worked on one paper cannot switch", "NOT done" in out and active(ws) == "test", out)
    hook(ws, "session-start", {"source": "startup"}, sid="B")
    code, out, _ = hook(ws, "prompt", {"prompt": "PAPER other"}, sid="B")
    check("session: a fresh conversation can switch (PAPER other)", "done" in out and active(ws) == "other", out)
    code, _, err = hook(ws, "pre-read", read(o / "project.json"), sid="A")
    check("session: the old conversation is blocked on the new paper", code == 2 and "working on paper 'test'" in err, err)
    code, out, _ = hook(ws, "prompt", {"prompt": "APPROVE gate1"}, sid="A")
    check("session: approvals from the old conversation are refused", "NOT recorded" in out and "belongs to paper" in out,
          out)
    hook(ws, "session-start", {"source": "clear"}, sid="A")
    code, _, err = hook(ws, "pre-read", read(o / "project.json"), sid="A")
    check("session: after /clear the conversation may work on the active paper", code == 0, err)
    code, out, _ = hook(ws, "prompt", {"prompt": "NEW PAPER Third-One"}, sid="C")
    check("session: NEW PAPER creates and activates a paper", "done" in out and active(ws) == "third-one"
          and (ws / "papers/third-one/state.json").exists(), out)
    code, out, _ = hook(ws, "prompt", {"prompt": "NEW PAPER bad_name!"}, sid="D")
    check("session: invalid paper names are ignored", active(ws) == "third-one", out)
    # /ra-init: the agent may create a NEW paper, but only from a fresh conversation
    hook(ws, "session-start", {"source": "startup"}, sid="F")
    for cmd, sid, want, label in [
        ("./ra paper new fresh-one", "F", 0, "fresh conversation may create a paper"),
        ("./ra paper new x2", "A", 2, "conversation that worked on a paper may not"),
        ("./ra paper new x3 && cat papers/test/state.json", "F", 2, "only the plain command form"),
        ("./ra paper use test", "F", 2, "switching stays human-only"),
        ("./ra py -c \"from ra import papers; papers.create('x4')\"", "F", 2, "no creation through python"),
        ("echo test > .ra/active-paper", "F", 2, "no pointer tampering")]:
        code, _, err = hook(ws, "pre-bash", bash(cmd), sid=sid)
        check(f"ra-init: {label}", code == want, err)
    code, out, err = run(ws, "paper", "new", "fresh-one", env={"CLAUDECODE": "1"})
    code2, _, err2 = hook(ws, "pre-read", read(ws / "papers/fresh-one/project.json"), sid="F")
    check("ra-init: the fresh conversation then works on the new paper", code == 0 and code2 == 0, out + err + err2)
    code, _, err = hook(ws, "pre-read", read(ws / "papers/test/project.json"), sid="F")
    check("ra-init: ...and cannot reach the other papers", code == 2, err)

    # lean status: no other paper's topic/journal leaks into a conversation
    pj = json.loads((t / "project.json").read_text())
    pj["topic"] = "SECRET-TOPIC-XYZ"
    (t / "project.json").write_text(json.dumps(pj))
    run(ws, "paper", "use", "test")
    code, out, _ = hook(ws, "session-start", {"source": "startup"}, sid="G")
    code2, out2, _ = run(ws, "paper", "list")
    check("isolation: session start and paper list show no topics", "SECRET-TOPIC-XYZ" not in out + out2
          and "Journal of Test Theory" not in out + out2, out + out2)

    # MAINTENANCE: framework edits only when the human switches it on, for that conversation only
    code, _, err = hook(ws, "pre-edit", write(ws / "scripts/new_tool.py", "x"), sid="M")
    check("maintenance: framework edit blocked by default (hint shown)", code == 2 and "MAINTENANCE ON" in err, err)
    code, out, _ = hook(ws, "prompt", {"prompt": "MAINTENANCE ON 30"}, sid="M")
    check("maintenance: human switches it on", "MAINTENANCE ON until" in out, out)
    code, _, err = hook(ws, "pre-edit", write(ws / "scripts/new_tool.py", "x"), sid="M")
    check("maintenance: that conversation may edit the framework", code == 0, err)
    code, _, err = hook(ws, "pre-bash", bash("sed -i 's/a/b/' scripts/ra/hooks.py"), sid="M")
    check("maintenance: ...also through the shell", code == 0, err)
    code, _, err = hook(ws, "pre-edit", write(ws / "scripts/new_tool.py", "x"), sid="N")
    check("maintenance: other conversations stay blocked", code == 2, err)
    code, _, err = hook(ws, "pre-edit", write(ws / ".ra/active-paper", "x"), sid="M")
    check("maintenance: runtime state stays protected", code == 2, err)
    code, _, err = hook(ws, "pre-bash", bash("echo x > .ra/maintenance.json"), sid="N")
    check("maintenance: the agent cannot switch it on itself", code == 2, err)
    hook(ws, "prompt", {"prompt": "MAINTENANCE OFF"}, sid="M")
    code, _, err = hook(ws, "pre-edit", write(ws / "scripts/new_tool.py", "x"), sid="M")
    check("maintenance: OFF protects the framework again", code == 2, err)
    skill = (SRC / ".claude/skills/ra-init/SKILL.md").read_text(encoding="utf-8")
    check("ra-init: skill exists, human-invoked only", "disable-model-invocation: true" in skill
          and "./ra paper new" in skill)

    (ws / ".ra/active-paper").unlink()
    code, _, err = run(ws, "state", "status")
    check("paper: ./ra commands refuse to run with no active paper", code == 13 and "PAPER <name>" in err, err)
    code, _, err = hook(ws, "pre-skill", {"tool_name": "Skill", "tool_input": {"skill": "intake"}})
    check("paper: stage skills blocked with no active paper", code == 2 and "No active paper" in err, err)
    code, out, _ = hook(ws, "session-start", {"source": "startup"}, sid="E")
    check("paper: session start with no paper asks the human to choose", "No active paper" in out, out)
    shutil.rmtree(ws, ignore_errors=True)


# ------------------------------------------------------------------ hard rules
MAIN = r"""\documentclass{article}
\newcommand{\NA}{\textsc{na-bbht}}
\IfFileExists{generated/results.tex}{\input{generated/results.tex}}{}
\begin{document}
\begin{abstract}
\input{sections/abstract}
\end{abstract}
\input{sections/intro}
\end{document}
"""


def test_rules():
    ws = fresh()
    ready_for_paper(ws)
    P = lambda rel="": pp(ws, rel)  # noqa: E731
    put(P("paper/main.tex"), MAIN)
    put(P("paper/sections/intro.tex"), "The cost is $O(\\sqrt{N})$ here, which is fine outside the abstract.\n")
    put(P("paper/sections/abstract.tex"), "We study noisy search and show that the cost grows slowly.\n")
    put(P("paper/generated/results.tex"), "\\providecommand{\\resRunGain}{12.5}\n"
                                          "\\providecommand{\\resRunTiny}{\\ensuremath{1.2\\times 10^{-3}}}\n")
    code, out, _ = run(ws, "check-abstract")
    check("abstract: clean abstract passes (formulas elsewhere are fine)", code == 0, out)
    a = P("paper/sections/abstract.tex")
    for new, label in [("with cost $O(\\sqrt{N})$.", "math mode"), ("with cost O(sqrt(N)).", "plain-text big-O"),
                       ("for N/M items.", "symbolic fraction"), ("when n = 10.", "operator"),
                       ("at noise \\gamma.", "Greek macro"), ("at noise γ.", "Unicode Greek"),
                       ("a gain of \\resRunTiny.", "results macro that typesets math"),
                       ("using the \\NA{} schedule.", "(expanded user macro is text)")]:
        code, _, err = hook(ws, "pre-edit", edit(a, "grows slowly.", "grows slowly " + new))
        want = 0 if label.startswith("(") else 2
        check(f"abstract: pre-edit {'allows' if not want else 'blocks'} {label}", code == want, err)
    code, _, _ = hook(ws, "pre-edit", edit(a, "grows slowly.", "grows slowly, by \\resRunGain\\% per step."))
    check("abstract: plain-number results macro allowed", code == 0)
    put(a, "The cost is $O(\\sqrt{N})$.\n")                                        # legacy/human formula
    code, out, _ = run(ws, "check-abstract")
    check("abstract: ./ra check-abstract reports a formula (exit 1)", code == 1 and "math mode" in out, out)
    code, _, err = hook(ws, "pre-edit", edit(P("paper/main.tex"), "\\input{sections/intro}", "\\input{sections/intro}\n"))
    check("abstract: unrelated edits still allowed while a legacy formula exists", code == 0, err)
    code, _, err = hook(ws, "post-edit", write(a, ""))
    check("abstract: post-edit reports the violation after editing the abstract", code == 2 and "check-abstract" in err, err)
    put(P("paper/main.tex"), MAIN.replace("\\begin{abstract}\n\\input{sections/abstract}\n\\end{abstract}",
                                          "\\abstract{Cost $x^2$ for all.}"))
    code, out, _ = run(ws, "check-abstract")
    check("abstract: \\abstract{...} command form is checked too", code == 1, out)

    # AI statements
    i = P("paper/sections/intro.tex")
    for text, want, label in [
        ("The author used Claude to draft the manuscript text.", 2, "authorial AI-use sentence"),
        ("This work was prepared with the assistance of ChatGPT.", 2, "prepared-with-AI sentence"),
        ("\\section*{Declaration of generative AI in the writing process}", 2, "declaration heading"),
        ("We used ChatGPT to generate 200 tutoring dialogues for students.", 0, "AI as the research subject"),
        ("Chatbots such as Claude and Gemini are widely used by students.", 0, "AI tools mentioned as topic")]:
        code, _, err = hook(ws, "pre-edit", edit(i, "here, which", f"here. {text} Which"))
        check(f"no-AI-statement: pre-edit {'blocks' if want else 'allows'} {label}", code == want, err)
    code, _, err = hook(ws, "pre-edit", write(P("paper/ai-disclosure.tex"), "Nothing."))
    check("no-AI-statement: creating an ai-disclosure file is blocked", code == 2 and "hard rule" in err, err)
    code, _, err = hook(ws, "pre-bash", bash("git -C papers/test commit -m 'x' -m 'Generated with [Claude Code](https://claude.com)'"))
    check("no-AI-signature: commit with 'Generated with Claude' blocked", code == 2, err)
    shutil.rmtree(ws, ignore_errors=True)


# ------------------------------------------------------------------ verify_bib (+ reference age)
def test_bib():
    ws = fresh()
    P = lambda rel="": pp(ws, rel)  # noqa: E731
    y = YEAR - 2
    good = {"type": "article", "key": "smith2024theory",
            "fields": {"author": "Smith, Jane", "title": "A theory of tests", "year": str(y), "doi": "10.1000/xyz123"}}
    tampered = {"type": "article", "key": "lee2023bounds",
                "fields": {"author": "Lee, K", "title": "Bounds", "year": str(y), "doi": "10.1000/abc"}}
    noid = {"type": "misc", "key": "anon2024note", "fields": {"author": "Anon", "title": "A note", "year": str(y)}}
    unver = {"type": "article", "key": "kim2024unverified",
             "fields": {"author": "Kim, A", "title": "Unverified", "year": str(y), "doi": "10.1000/def"}}
    text = "\n\n".join(bib.format_entry(e["type"], e["key"], e["fields"]) for e in (good, tampered, noid, unver))
    ledger = {"version": 1, "entries": {
        "smith2024theory": {"doi": "10.1000/xyz123", "fingerprint": bib.fingerprint(good), "title": "A theory of tests",
                            "abstract": "We develop a theory of sequential tests and prove that they converge under "
                                        "mild assumptions, with explicit bounds."},
        "lee2023bounds": {"doi": "10.1000/abc", "fingerprint": bib.fingerprint(tampered), "title": "Bounds"},
        "anon2024note": {"fingerprint": bib.fingerprint(noid), "title": "A note"}}}
    text = text.replace("title = {Bounds}", "title = {Bounds (edited by hand)}")
    put(P("paper/references.bib"), text + "\n")
    P("paper/references.verified.json").write_text(json.dumps(ledger))
    put(P("paper/main.tex"), r"""
        \documentclass{article}
        \begin{document}

        Sequential tests converge under mild assumptions \cite{smith2024theory}.
        Prior bounds exist \citep[Thm.~2]{lee2023bounds, anon2024note}.
        See also \citet{kim2024unverified} and \cite{ghost2022}.
        % \cite{commentedout2020} must be ignored
        The error rate is 5\% \cite{smith2024theory}.
        \bibliography{references}
        \end{document}
    """)
    code, out, err = run(ws, "verify-bib", "--json")
    rep = json.loads(out)
    codes = {(i["code"], i["key"]) for i in rep["errors"]}
    check("verify_bib: exits 1 when there are errors", code == 1, err)
    check("verify_bib: MISSING (cited, not in bib)", ("MISSING", "ghost2022") in codes, codes)
    check("verify_bib: UNVERIFIED (no ledger record)", ("UNVERIFIED", "kim2024unverified") in codes, codes)
    check("verify_bib: TAMPERED (edited after fetch)", ("TAMPERED", "lee2023bounds") in codes, codes)
    check("verify_bib: NO-ID (no DOI / arXiv)", ("NO-ID", "anon2024note") in codes, codes)
    check("verify_bib: commented-out cite ignored", not any(k == "commentedout2020" for _, k in codes), codes)
    check("verify_bib: verified entry passes", not any(k == "smith2024theory" for _, k in codes), codes)
    put(P("paper/extra.tex"), r"\bibliography{references,handmade}")
    code, out, _ = run(ws, "verify-bib", "--json")
    check("verify_bib: FOREIGN-BIB for other .bib files", any(i["code"] == "FOREIGN-BIB" for i in json.loads(out)["errors"]))
    P("paper/extra.tex").unlink()
    code, out, _ = run(ws, "verify-bib", "--claims", "--json")
    claims = json.loads(out)["claims"]
    c1 = [c for c in claims if "converge" in c["sentence"]]
    check("claims: supported sentence is not flagged", c1 and not any("LOW-OVERLAP" in f for f in c1[0]["flags"]), c1)
    check("claims: sentence extraction stops at the paragraph", c1 and "documentclass" not in c1[0]["sentence"], c1)
    c2 = [c for c in claims if "error rate" in c["sentence"]]
    check("claims: number missing from the cited abstract flagged", c2 and any("NUMBER" in f for f in c2[0]["flags"]), c2)
    c3 = [c for c in claims if c["key"] == "lee2023bounds"]
    check("claims: source without abstract flagged", c3 and any("NO-ABSTRACT" in f for f in c3[0]["flags"]), c3)
    put(P("paper/main.tex"), "\\documentclass{article}\\begin{document}\nTests converge \\cite{smith2024theory}.\n"
                             "\\bibliography{references}\\end{document}\n")
    code, out, err = run(ws, "verify-bib")
    check("verify_bib: clean paper exits 0", code == 0, out + err)

    # reference age (hard rule)
    old, mid, new = YEAR - 12, YEAR - 8, YEAR - 1
    verified_bib(ws, [("old2000x", old, "10.1/a"), ("mid2010x", mid, "10.1/b")] +
                 [(f"new{k}x", new, f"10.1/n{k}") for k in range(8)])
    cites = ",".join(["old2000x", "mid2010x"] + [f"new{k}x" for k in range(8)])
    put(P("paper/main.tex"), f"\\documentclass{{article}}\\begin{{document}}\nWork \\cite{{{cites}}}.\n"
                             "\\bibliography{references}\\end{document}\n")
    code, out, _ = run(ws, "verify-bib", "--json")
    rep = json.loads(out)
    codes = {(i["code"], i["key"]) for i in rep["errors"]}
    check("age: reference older than 10 years is an error (no exceptions)", ("REF-TOO-OLD", "old2000x") in codes, codes)
    check("age: 6-10-year-old reference without justification is an error", ("REF-UNJUSTIFIED", "mid2010x") in codes,
          codes)
    check("age: recent references pass", not any(k.startswith("new") for _, k in codes), codes)
    put(P("literature/reference-justifications.md"),
        f"## mid2010x ({mid})\n- Essential because: short\n- No recent alternative because: short\n")
    code, out, _ = run(ws, "verify-bib", "--json")
    codes = {(i["code"], i["key"]) for i in json.loads(out)["errors"]}
    check("age: a weak justification is rejected", ("REF-UNJUSTIFIED", "mid2010x") in codes, codes)
    words = " ".join(["because the original derivation of the lemma we extend is only stated there"] * 2)
    put(P("literature/reference-justifications.md"),
        f"## mid2010x ({mid})\n- Essential because: {words}\n- No recent alternative because: {words}\n")
    put(P("paper/main.tex"), f"\\documentclass{{article}}\\begin{{document}}\nWork \\cite{{{cites.replace('old2000x,', '')}}}."
                             "\n\\bibliography{references}\\end{document}\n")
    code, out, err = run(ws, "verify-bib")
    check("age: justified 6-10-year-old reference + recent ones pass", code == 0 and "reference age" in out, out + err)
    put(P("paper/main.tex"), "\\documentclass{article}\\begin{document}\nWork \\cite{mid2010x,new0x}."
                             "\n\\bibliography{references}\\end{document}\n")
    code, out, _ = run(ws, "verify-bib", "--json")
    check("age: warning when fewer than 80% of references are recent",
          any(i["code"] == "RECENCY" for i in json.loads(out)["warnings"]), out)
    shutil.rmtree(ws, ignore_errors=True)


# ------------------------------------------------------------------ state machine
def test_state():
    ws = fresh()
    P = lambda rel="": pp(ws, rel)  # noqa: E731
    code, out, _ = run(ws, "state", "next")
    check("state: empty project -> INTAKE (exit 11)", code == 11 and "journal.name" in out, out)
    code, _, err = run(ws, "state", "start", "literature-review")
    check("state: literature-review cannot start before intake", code == 1 and "intake" in err, err)
    set_state(ws, confirmed=False)
    code, out, _ = run(ws, "state", "next")
    check("state: fields complete -> RUN intake", code == 0 and "intake" in out, out)
    code, _, err = run(ws, "state", "complete", "intake", "--no-commit")
    check("state: intake refused while journal-profile is a placeholder", code == 1 and "placeholder" in err, err)
    put(P("journal-profile.md"), "# Journal profile\nresearched\n")
    code, out, err = run(ws, "state", "complete", "intake", "--no-commit")
    check("state: intake completes once outputs exist", code == 0, out + err)
    put(P("literature/topic-fit.md"), "fit\n")
    put(P("gates/gate0_intake.md"), "summary\n")
    code, out, err = run(ws, "state", "complete", "topic-fit-check", "--no-commit")
    check("state: topic-fit-check opens gate0", code == 0 and "gate0_intake" in out, out + err)
    code, out, _ = run(ws, "state", "next")
    check("state: next = GATE gate0 (exit 10)", code == 10 and "gate0_intake" in out, out)
    code, _, err = run(ws, "state", "approve", "intake", env={"CLAUDECODE": "1"})
    check("state: CLI approve refused inside Claude Code", code == 3, err)
    code, out, err = run(ws, "state", "approve", "intake", "--note", "ok")
    check("state: human CLI approve works", code == 0 and json.loads(P("project.json").read_text())["intake_confirmed"],
          out + err)
    code, out, _ = run(ws, "state", "next")
    check("state: then RUN literature-review", code == 0 and "literature-review" in out, out)
    code, _, err = run(ws, "state", "start", "theory-experiment")
    check("state: theory-experiment blocked by deps + gate1", code == 1 and "gate1_topic" in err, err)
    run(ws, "state", "start", "literature-review")
    put(P("paper/sections/intro.tex"), "Text.\n% @agent: shorten this\n")
    code, _, err = run(ws, "state", "complete", "literature-review", "--no-commit")
    check("state: open @agent comment blocks completion", code == 1 and "@agent" in err, err)
    check("state: missing outputs are listed", "literature/papers/*.md" in err, err)
    st = json.loads(P("state.json").read_text())
    st["stages"]["journal-format"]["outputs"] = ["paper/ai-disclosure.tex"]      # stale definitions from an older run
    st["stages"]["journal-format"]["checks"] = []
    P("state.json").write_text(json.dumps(st))
    code, out, _ = run(ws, "state", "show", "journal-format")
    shown = json.loads(out)
    check("state: stage definitions refreshed from the code (new rules apply to older papers)",
          "abstract" in shown["checks"] and "paper/ai-disclosure.tex" not in shown["outputs"], out)
    st = json.loads(P("state.json").read_text())
    for s in st["stages"]:
        st["stages"][s]["status"] = "done"
    for g in st["gates"]:
        st["gates"][g].update(approved=True, status="approved")
    P("state.json").write_text(json.dumps(st))
    P("paper/sections/intro.tex").unlink()
    run(ws, "state", "stale", "--scope", "claims", "--reason", "t")
    st = json.loads(P("state.json").read_text())
    stale = sorted(s for s, v in st["stages"].items() if v["status"] == "stale")
    check("state: scope claims -> theory-experiment + drafting only", stale == ["drafting", "theory-experiment"], stale)
    code, out, _ = run(ws, "state", "next")
    check("state: next RUN = first stale stage", "theory-experiment" in out, out)
    run(ws, "state", "stale", "--scope", "journal", "--reason", "new journal")
    check("state: scope journal resets intake confirmation",
          json.loads(P("project.json").read_text())["intake_confirmed"] is False)
    st = json.loads(P("state.json").read_text())
    for s in st["stages"]:
        st["stages"][s]["status"] = "done" if s != "revision" else "pending"
    st["gates"]["gate3_response"].update(approved=False, status="not_reached")
    P("state.json").write_text(json.dumps(st))
    set_state(ws, confirmed=True)
    code, out, _ = run(ws, "state", "next")
    check("state: revision WAITs for reviews/external/round-N", code == 10 and "WAIT" in out, out)
    put(P("reviews/external/round-1/reviewer1.md"), "The bound in Thm 2 is not tight.\n")
    code, out, _ = run(ws, "state", "next")
    check("state: reviews present -> RUN revision", code == 0 and "revision" in out, out)
    shutil.rmtree(ws, ignore_errors=True)


# ------------------------------------------------------------------ feedback + numbers + results
def test_feedback():
    ws = fresh()
    ready_for_paper(ws)
    P = lambda rel="": pp(ws, rel)  # noqa: E731
    m = P("paper/sections/method.tex")
    put(m, "We utilize a simple model.\nThe error is 0.123.\n")
    hook(ws, "post-edit", write(m, ""))
    code, out, _ = run(ws, "edits", "detect")
    check("edits: nothing detected right after the agent's write", "no unregistered" in out, out)
    put(m, "We use a simple model.\nThe error is 0.123.\n% @agent[claims]: is this bound tight?\n")
    code, out, _ = run(ws, "edits", "detect", "--diff")
    check("edits: human edit detected with a diff", "modified" in out and "+We use" in out, out)
    put(P("feedback/reframe.md"), "scope: novelty\nchange: |\n  Reframe around stability.\nkeep: |\n  Keep Theorem 1.\n")
    code, out, _ = run(ws, "feedback", "collect", "--json")
    c = json.loads(out)
    check("feedback: edit + tagged comment + file collected",
          len(c["edits"]) == 1 and c["comments"][0]["scope"] == "claims" and c["files"][0]["scopes"] == ["novelty"], out)
    code, _, err = run(ws, "state", "start", "theory-experiment")
    check("state: stage start refused while feedback is unprocessed", code == 1 and "apply-feedback" in err, err)
    cid = c["comments"][0]["id"]
    code, _, err = run(ws, "comments", "resolve", cid, "--note", "x", "--no-commit")
    check("comments: resolve refused before edits are registered", code == 1 and "edits accept" in err, err)
    run(ws, "edits", "accept", "papers/test/paper/sections/method.tex")
    pats = json.loads(P("feedback/edit-patterns.json").read_text())
    check("edits: accept takes workspace paths and learns 'utilize -> use'",
          any(k.startswith("utilize -> use") for k in pats["pairs"]), pats)
    code, out, err = run(ws, "feedback", "plan", "--scope", "novelty", "--items", f"fb:reframe.md,{cid}",
                         "--title", "Reframe", "--no-commit")
    st = json.loads(P("state.json").read_text())
    check("feedback: impact plan P001 awaiting, novelty stages stale",
          st["impact_plans"]["P001"]["status"] == "awaiting" and st["stages"]["topic-selection"]["status"] == "stale"
          and P("gates/impact-P001.md").exists(), out + err)
    code, out, _ = run(ws, "state", "next")
    check("state: next = PLAN awaiting approval", code == 10 and "P001" in out, out)
    code, out, _ = hook(ws, "prompt", {"prompt": "REJECT P001: keep the current framing"})
    st = json.loads(P("state.json").read_text())
    check("prompt: REJECT plan restores stage statuses", st["impact_plans"]["P001"]["status"] == "rejected" and
          st["stages"]["topic-selection"]["status"] == "done", out)
    check("prompt: REJECT plan restores the gate approvals it had reset", st["gates"]["gate1_topic"]["approved"], st["gates"])
    code, out, err = run(ws, "comments", "resolve", cid, "--note", "answered", "--no-commit")
    check("comments: resolve deletes the comment and logs it", code == 0 and "@agent" not in m.read_text()
          and "answered" in P("feedback/log.md").read_text(), out + err)
    code, out, err = run(ws, "feedback", "done", "reframe.md", "--resolution", "rejected by human", "--no-commit")
    check("feedback: processed file archived to feedback/done", code == 0 and not P("feedback/reframe.md").exists()
          and list(P("feedback/done").glob("*reframe.md")), out + err)
    code, out, _ = run(ws, "check-numbers")
    check("numbers: untraceable decimal flagged", code == 1 and "0.123" in out, out)
    put(m, "Width 0.8\\linewidth, \\vspace{1.5em}, Python 3.14.7.\nThe error is 0.123.\n")
    P("results/sim").mkdir(parents=True, exist_ok=True)
    P("results/sim/metrics.json").write_text(json.dumps({"error": 0.12304, "n": 100}))
    code, out, _ = run(ws, "check-numbers")
    check("numbers: traced to results (layout lengths, versions ignored)", code == 0, out)
    put(m, "The error is 12.3\\% here.\n")
    code, out, _ = run(ws, "check-numbers")
    check("numbers: percentage matched against fraction x100", code == 0, out)
    r = subprocess.run([PY, "-c", "import sys; sys.path.insert(0,'scripts'); from ra import results; "
                        "print('\\n'.join(results.integrity_problems()))"], cwd=str(ws), capture_output=True, text=True,
                       env=env_for())
    check("results: hand-made results file detected", "not produced by a recorded" in r.stdout, r.stdout + r.stderr)
    code, out, _ = run(ws, "results-tex")
    gen = P("paper/generated/results.tex").read_text()
    check("results-tex: \\resSimError macro generated", "\\resSimError" in gen and "0.123" in gen, gen)
    put(P("experiments/tiny.py"), """
        import argparse, json, random
        from pathlib import Path
        ap = argparse.ArgumentParser(); ap.add_argument('--seed', type=int); ap.add_argument('--out', type=Path)
        a = ap.parse_args(); a.out.mkdir(parents=True, exist_ok=True); random.seed(a.seed)
        (a.out / 'metrics.json').write_text(json.dumps({'value': random.random()}))
    """)
    code, out, err = run(ws, "run", "papers/test/experiments/tiny.py", "--seed", "3")
    man = json.loads(P("results/manifest.json").read_text()) if P("results/manifest.json").exists() else {"runs": {}}
    check("run: experiment (workspace path) recorded in manifest with hashes", code == 0 and "tiny" in man["runs"]
          and man["runs"]["tiny"]["outputs"], out + err)
    code, out, err = run(ws, "run", "--verify", "tiny")
    check("run: --verify confirms reproducibility", code == 0 and "reproducible" in out, out + err)
    shutil.rmtree(ws, ignore_errors=True)


# ------------------------------------------------------------------ Overleaf export
def test_export():
    ws = fresh()
    ready_for_paper(ws)
    P = lambda rel="": pp(ws, rel)  # noqa: E731
    put(P("paper/main.tex"), r"""\documentclass{article}
\usepackage{graphicx}
\graphicspath{{../figures/}}
\begin{document}
\begin{abstract}
\input{sections/abstract}
\end{abstract}
\input{sections/intro}
\begin{figure}\includegraphics[width=2cm]{fig1}\caption{A figure.}\end{figure}
\end{document}
""")
    put(P("paper/sections/abstract.tex"), "A short abstract in words.\n")
    put(P("paper/sections/intro.tex"), "An introduction.\n")
    put(P("paper/sections/unused.tex"), "Not included anywhere.\n")
    put(P("paper/cover-page.tex"), "\\documentclass{article}\\begin{document}Cover page.\\end{document}\n")
    P("figures").mkdir(exist_ok=True)
    # a valid 1x1 PNG
    P("figures/fig1.png").write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"))
    code, out, err = run(ws, "export", "--no-pdf")
    zp = P("exports/test-overleaf.zip")
    check("export: zip built", code == 0 and zp.exists(), out + err)
    if zp.exists():
        z = zipfile.ZipFile(zp)
        names = set(z.namelist())
        main = z.read("main.tex").decode()
        check("export: main.tex at the root, sections and README included",
              {"main.tex", "sections/abstract.tex", "sections/intro.tex", "README.txt", "cover-page.tex"} <= names, names)
        check("export: figure from ../figures copied into figures/", "figures/fig1.png" in names, names)
        check("export: graphics paths rewritten inside the project", "{figures/fig1}" in main and "../" not in main, main)
        check("export: unreferenced .tex files are left out", "sections/unused.tex" not in names, names)
        check("export: no AI mention in the README", "claude" not in z.read("README.txt").decode().lower())
    P("figures/fig1.png").unlink()
    code, out, _ = run(ws, "export", "--no-pdf")
    check("export: missing figure makes the export fail", code == 1 and "fig1" in out and "not found" in out, out)
    if latex.latexmk_available():
        put(P("paper/main.tex"), "\\documentclass{article}\\begin{document}\n\\begin{abstract}\n"
                                 "\\input{sections/abstract}\n\\end{abstract}\n\\input{sections/intro}\n\\end{document}\n")
        code, out, err = run(ws, "export")
        check("export: PDF compiled from the zip itself (TeX found)", code == 0 and P("exports/test.pdf").exists()
              and P("exports/test-cover-page.pdf").exists(), out + err)
    else:
        print("SKIP  export: PDF compile (no TeX installation found)")
    shutil.rmtree(ws, ignore_errors=True)


GROUPS = {"hooks": test_hooks, "papers": test_papers, "rules": test_rules, "bib": test_bib, "state": test_state,
          "feedback": test_feedback, "export": test_export}

if __name__ == "__main__":
    for g in sys.argv[1:] or list(GROUPS):
        print(f"== {g} ==")
        GROUPS[g]()
    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    sys.exit(1 if failed else 0)
