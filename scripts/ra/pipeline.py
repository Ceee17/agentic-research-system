"""Pipeline state machine: stages, gates, impact plans, scope routing, intake checks.

state.json is the single source of truth for stage status and gate approvals, except
intake confirmation, which lives in project.json (`intake_confirmed`) as specified.
Only this module (via `./ra state ...`) and the human write state.json.
"""
from __future__ import annotations

import glob as _glob
import os
import re

from . import core, feedbackcore, tex

STAGE_ORDER = ["intake", "topic-fit-check", "literature-review", "topic-selection", "theory-experiment",
               "figures", "drafting", "citation-verify", "journal-format", "self-review", "revision"]
PROFILE_PLACEHOLDER = "STATUS: NOT RESEARCHED"
ARTICLE_TYPES = ["full paper", "letter", "short communication", "review"]

STAGE_DEFS = {
    "intake": {"skill": "intake", "depends_on": [], "checks": ["intake_fields"],
               "outputs": ["project.json", {"glob": "journal-profile.md", "forbid": PROFILE_PLACEHOLDER}]},
    "topic-fit-check": {"skill": "intake", "depends_on": ["intake"], "checks": ["intake_fields"],
                        "outputs": ["literature/topic-fit.md", "gates/gate0_intake.md"]},
    "literature-review": {"skill": "literature-review", "depends_on": ["topic-fit-check"], "checks": [],
                          "outputs": [{"glob": "literature/papers/*.md", "min_count": 15}, "literature/gap-analysis.md",
                                      "literature/search-log.md", "paper/references.bib",
                                      "paper/references.verified.json"]},
    "topic-selection": {"skill": "topic-selection", "depends_on": ["literature-review"], "checks": [],
                        "outputs": ["literature/topics.md", "literature/novelty-check.md", "gates/gate1_topic.md"]},
    "theory-experiment": {"skill": "theory-experiment", "depends_on": ["topic-selection"],
                          "checks": ["results_integrity"],
                          "outputs": ["experiments/theory.md", {"glob": "experiments/*.py"}, "results/manifest.json",
                                      "paper/generated/results.tex"]},
    "figures": {"skill": "figures", "depends_on": ["theory-experiment"], "checks": ["figures_integrity"],
                "outputs": [{"glob": "figures/*.pdf"}, "figures/manifest.json"]},
    "drafting": {"skill": "drafting", "depends_on": ["theory-experiment", "figures"],
                 "checks": ["bib", "numbers", "results_integrity", "figures_integrity", "abstract", "ai_statement",
                            "export"],
                 "outputs": ["paper/main.tex", {"glob": "paper/sections/*.tex", "min_count": 4}]},
    "citation-verify": {"skill": "citation-verify", "depends_on": ["drafting"],
                        "checks": ["bib", "abstract", "ai_statement", "export"],
                        "outputs": ["reviews/internal/citation-report.md", "paper/references.verified.json"]},
    "journal-format": {"skill": "journal-format", "depends_on": ["citation-verify"],
                       "checks": ["bib", "numbers", "compile_strict", "abstract", "ai_statement", "export"],
                       "outputs": ["paper/build/main.pdf", "reviews/internal/format-report.md"]},
    "self-review": {"skill": "self-review", "depends_on": ["journal-format"],
                    "checks": ["bib", "abstract", "ai_statement", "export"],
                    "outputs": [{"glob": "reviews/internal/review-*.md"}, "gates/gate2_draft.md"]},
    "revision": {"skill": "revision", "depends_on": ["self-review"],
                 "checks": ["bib", "numbers", "compile_strict", "abstract", "ai_statement", "export"],
                 "outputs": ["reviews/response/round-{round}/response-letter.tex",
                             "reviews/response/round-{round}/diff.pdf", "gates/gate3_response.md"]},
}
GATE_DEFS = {
    "gate0_intake": {"after": "topic-fit-check", "file": "gates/gate0_intake.md", "short": "intake",
                     "label": "Confirm journal, journal profile and topic fit"},
    "gate1_topic": {"after": "topic-selection", "file": "gates/gate1_topic.md", "short": "gate1",
                    "label": "Pick or approve the research topic"},
    "gate2_draft": {"after": "self-review", "file": "gates/gate2_draft.md", "short": "gate2",
                    "label": "Read and approve the draft for submission"},
    "gate3_response": {"after": "revision", "file": "gates/gate3_response.md", "short": "gate3",
                       "label": "Approve the revision and response to reviewers"},
}
SCOPE_MAP = {
    "wording": ["drafting"],
    "claims": ["theory-experiment", "drafting"],
    "novelty": ["topic-selection", "theory-experiment", "drafting"],
    "figures": ["figures", "drafting"],
    "template": ["journal-format"],
    "journal": ["intake", "topic-fit-check", "journal-format"],
}
GATE_ALIASES = {"intake": "gate0_intake", "gate0": "gate0_intake", "journal": "gate0_intake",
                "gate1": "gate1_topic", "topic": "gate1_topic", "gate2": "gate2_draft", "draft": "gate2_draft",
                "gate3": "gate3_response", "response": "gate3_response", "revision": "gate3_response"}


# ----------------------------------------------------------------- io
def default_state() -> dict:
    st = {"version": 1, "stage_order": list(STAGE_ORDER), "stages": {}, "gates": {},
          "scope_map": {k: list(v) for k, v in SCOPE_MAP.items()}, "impact_plans": {},
          "revision": {"rounds_done": []}, "history": []}
    for s in STAGE_ORDER:
        d = STAGE_DEFS[s]
        st["stages"][s] = {"status": "pending", "skill": d["skill"], "depends_on": list(d["depends_on"]),
                           "outputs": list(d["outputs"]), "checks": list(d["checks"]), "started_at": None,
                           "completed_at": None, "stale_reason": None}
    for g, d in GATE_DEFS.items():
        st["gates"][g] = {**d, "status": "not_reached", "approved": False, "approved_by": None,
                          "approved_at": None, "note": None}
    return st


def load_state() -> dict:
    """state.json of the active paper, with stage/gate DEFINITIONS refreshed from the code (rules are
    workspace-level: a paper started under older rules gets the current checks and outputs)."""
    st = core.read_json(core.path("state.json")) or default_state()
    fresh = default_state()
    st["stage_order"] = fresh["stage_order"]
    st["scope_map"] = fresh["scope_map"]
    for s, d in fresh["stages"].items():
        cur = st.setdefault("stages", {}).setdefault(s, d)
        cur.update({k: d[k] for k in ("skill", "depends_on", "outputs", "checks")})
    for g, d in fresh["gates"].items():
        cur = st.setdefault("gates", {}).setdefault(g, d)
        cur.update({k: d[k] for k in ("after", "file", "short", "label")})
    return st


def save_state(st: dict, event: str | None = None, **detail) -> None:
    if event:
        st.setdefault("history", []).append({"at": core.now(), "event": event, **detail})
        st["history"] = st["history"][-400:]
    core.write_json(core.path("state.json"), st)


def load_project() -> dict:
    return core.read_json(core.path("project.json"), {}) or {}


def save_project(pj: dict) -> None:
    core.write_json(core.path("project.json"), pj)


# ----------------------------------------------------------------- intake
def intake_missing(pj: dict | None = None) -> list[str]:
    if pj is None:
        if not core.path("project.json").exists():
            return ["project.json (file missing)", "journal.name", "journal.guidelines_url", "journal.article_type"]
        pj = load_project()
    j = pj.get("journal") or {}
    return [f"journal.{f}" for f in ("name", "guidelines_url", "article_type")
            if not (isinstance(j.get(f), str) and j.get(f).strip())]


def intake_confirmed(pj: dict | None = None) -> bool:
    pj = load_project() if pj is None else pj
    return not intake_missing(pj) and pj.get("intake_confirmed") is True


# ----------------------------------------------------------------- gates
def order(st: dict) -> list[str]:
    return st.get("stage_order") or STAGE_ORDER


def gate_after(st: dict, stage: str) -> str | None:
    return next((g for g, d in st["gates"].items() if d["after"] == stage), None)


def gates_before(st: dict, stage: str) -> list[str]:
    o = order(st)
    idx = o.index(stage)
    return [g for g, d in st["gates"].items() if o.index(d["after"]) < idx]


def gate_ok(st: dict, g: str) -> bool:
    if g == "gate0_intake":
        return intake_confirmed()
    return bool(st["gates"][g].get("approved"))


def _reset_gate(st: dict, g: str, status: str = "not_reached") -> None:
    st["gates"][g].update(status=status, approved=False, approved_by=None, approved_at=None)
    if g == "gate0_intake":
        pj = load_project()
        if pj.get("intake_confirmed"):
            pj.update(intake_confirmed=False, intake_confirmed_at=None, intake_confirmed_by=None)
            save_project(pj)


def blocking_plan(st: dict, stage: str) -> str | None:
    for pid, plan in (st.get("impact_plans") or {}).items():
        if plan.get("status") == "awaiting" and stage in plan.get("stages", []):
            return pid
    return None


# ----------------------------------------------------------------- revision rounds
def external_rounds() -> list[int]:
    d = core.path("reviews", "external")
    rounds = []
    if d.exists():
        for p in d.iterdir():
            m = re.match(r"round-(\d+)$", p.name)
            if m and p.is_dir() and any(f.is_file() and not f.name.startswith(".") for f in p.rglob("*")):
                rounds.append(int(m.group(1)))
    return sorted(rounds)


def loose_external_files() -> list[str]:
    d = core.path("reviews", "external")
    return [p.name for p in d.iterdir() if p.is_file() and not p.name.startswith(".")] if d.exists() else []


def current_round(st: dict) -> int | None:
    done = set((st.get("revision") or {}).get("rounds_done") or [])
    pending = [r for r in external_rounds() if r not in done]
    return pending[0] if pending else None


# ----------------------------------------------------------------- checks
def check_outputs(st: dict, stage: str) -> list[str]:
    problems = []
    rnd = current_round(st) or (st["stages"][stage].get("round") if stage == "revision" else None)
    for o in st["stages"][stage].get("outputs", []):
        spec = {"glob": o} if isinstance(o, str) else dict(o)
        pattern = spec["glob"].replace("{round}", str(rnd or "N"))
        matches = [m for m in _glob.glob(os.path.join(_glob.escape(str(core.root())), pattern))
                   if os.path.isfile(m) and os.path.getsize(m) > 0]
        need = spec.get("min_count", 1)
        if len(matches) < need:
            problems.append(f"missing output: {pattern} (found {len(matches)}, need {need})")
        if spec.get("forbid"):
            for m in matches:
                if spec["forbid"] in (core.read_text(m) or ""):
                    problems.append(f"{core.rel(m)} still contains the placeholder '{spec['forbid']}'")
    return problems


def run_checks(st: dict, stage: str) -> list[str]:
    from . import bibcheck, export, latex, numbers, results, rules
    problems = []
    comments = tex.all_agent_comments()
    if comments:
        where = ", ".join(f"{c['file']}:{c['line']}" for c in comments[:5])
        problems.append(f"{len(comments)} unresolved `% @agent` comment(s) ({where}) -> run apply-feedback")
    for chk in STAGE_DEFS[stage]["checks"]:
        if chk == "intake_fields":
            miss = intake_missing()
            if miss:
                problems.append("project.json incomplete: " + ", ".join(miss))
        elif chk == "bib":
            rep = bibcheck.check()
            if rep["errors"]:
                problems.append(f"verify_bib: {len(rep['errors'])} error(s) -> `./ra verify-bib`")
        elif chk == "numbers":
            items = numbers.untraceable()
            if items:
                problems.append(f"check-numbers: {len(items)} untraceable number(s) -> `./ra check-numbers`")
        elif chk == "results_integrity":
            problems += [f"results: {p}" for p in results.integrity_problems()[:10]]
        elif chk == "figures_integrity":
            problems += [f"figures: {p}" for p in results.figures_integrity()[:10]]
        elif chk == "abstract":
            v = rules.abstract_violations()
            if v:
                problems.append(f"abstract contains formulas ({len(v)}; hard rule) -> `./ra check-abstract`: "
                                + "; ".join(v[:4]))
        elif chk == "ai_statement":
            v = rules.ai_statement_violations()
            if v:
                problems.append("AI-use / AI-assistance statement in the paper (hard rule: none) -> remove: "
                                + "; ".join(v[:3]))
        elif chk == "export":
            res = export.build()
            if res["status"] != "ok":
                problems.append("Overleaf export failed -> `./ra export`: " + "; ".join(res["problems"][:4]))
        elif chk == "compile_strict":
            res = latex.compile_paper(strict=True)
            if res["status"] != "ok":
                problems.append("compile: " + (res["status"] + ": " + "; ".join(
                    (res.get("errors") or []) + res.get("undefined", []))[:300]))
    return problems


def can_start(st: dict, stage: str, for_completion: bool = False) -> list[str]:
    if stage not in st["stages"]:
        return [f"unknown stage '{stage}' (stages: {', '.join(order(st))})"]
    problems = []
    miss = intake_missing()
    if stage != "intake" and miss:
        problems.append("intake incomplete: missing " + ", ".join(miss))
    o = order(st)
    if o.index(stage) > o.index("topic-fit-check") and not intake_confirmed():
        problems.append("intake not confirmed by the human (gate0_intake)")
    for dep in st["stages"][stage].get("depends_on", []):
        if st["stages"][dep]["status"] != "done":
            problems.append(f"dependency '{dep}' is {st['stages'][dep]['status']}")
    for g in gates_before(st, stage):
        if g != "gate0_intake" and not gate_ok(st, g):
            problems.append(f"{g} has not been approved by the human")
    plan = blocking_plan(st, stage)
    if plan:
        problems.append(f"impact plan {plan} awaits human approval ({st['impact_plans'][plan]['file']})")
    if stage == "revision" and current_round(st) is None:
        problems.append("no unprocessed reviewer comments (put them in reviews/external/round-N/)")
    if not for_completion and stage not in ("intake", "topic-fit-check"):
        pend = feedbackcore.pending_summary(st)
        if pend:
            problems.append(f"unprocessed human feedback ({pend}) -> run the apply-feedback skill first")
    return problems


# ----------------------------------------------------------------- transitions
def start(stage: str) -> tuple[bool, list[str]]:
    st = load_state()
    if stage not in st["stages"]:
        return False, [f"unknown stage '{stage}'"]
    info = st["stages"][stage]
    if info["status"] == "done" and not (stage == "revision" and current_round(st)):
        return False, [f"'{stage}' is already done. To redo it, a scope change must mark it stale "
                       f"(`./ra state stale --stage {stage} --reason ...`)."]
    problems = can_start(st, stage)
    if problems:
        return False, problems
    if stage == "revision" and info["status"] == "done":
        _reset_gate(st, "gate3_response")
    info.update(status="in_progress", started_at=core.now())
    save_state(st, "start", stage=stage)
    return True, []


def complete(stage: str, commit: bool = True, note: str | None = None) -> tuple[bool, list[str], str | None]:
    st = load_state()
    if stage not in st["stages"]:
        return False, [f"unknown stage '{stage}'"], None
    info = st["stages"][stage]
    if info["status"] == "done" and not (stage == "revision" and current_round(st)):
        return True, [f"'{stage}' was already done"], None
    problems = can_start(st, stage, for_completion=True) + check_outputs(st, stage) + run_checks(st, stage)
    if problems:
        return False, problems, None
    info.update(status="done", completed_at=core.now(), stale_reason=None, note=note)
    if stage == "revision":
        rnd = current_round(st)
        st.setdefault("revision", {}).setdefault("rounds_done", []).append(rnd)
        info["round"] = rnd
    g = gate_after(st, stage)
    if g:
        _reset_gate(st, g, status="awaiting")
    for plan in (st.get("impact_plans") or {}).values():
        if plan.get("status") == "approved" and all(st["stages"][s]["status"] == "done" for s in plan["stages"]):
            plan["status"] = "executed"
            plan["executed_at"] = core.now()
    save_state(st, "complete", stage=stage, note=note)
    head = core.git_commit_all(f"stage({stage}): complete" + (f"\n\n{note}" if note else "")) if commit else None
    return True, [], head


def mark_stale(st: dict, stages: list[str], reason: str) -> list[str]:
    changed = []
    for s in stages:
        info = st["stages"][s]
        if info["status"] in ("done", "in_progress"):
            info["status"] = "stale"
            changed.append(s)
        info["stale_reason"] = reason
        g = gate_after(st, s)
        if g:
            _reset_gate(st, g)
    return changed


def stale(scope: str | None = None, stages: list[str] | None = None, reason: str = "") -> tuple[bool, str]:
    st = load_state()
    if scope:
        if scope not in st["scope_map"]:
            return False, f"unknown scope '{scope}' (scopes: {', '.join(st['scope_map'])})"
        stages = st["scope_map"][scope]
    stages = [s for s in stages or [] if s in st["stages"]]
    if not stages:
        return False, "no stages given"
    changed = mark_stale(st, stages, reason or f"scope change: {scope}")
    save_state(st, "stale", scope=scope, stages=stages, reason=reason)
    return True, f"marked stale: {', '.join(changed) or '(none were done)'}; affected: {', '.join(stages)}"


# ----------------------------------------------------------------- impact plans
def create_plan(scopes: list[str], items: list[str], title: str) -> tuple[str, list[str]]:
    st = load_state()
    bad = [s for s in scopes if s not in st["scope_map"]]
    if bad:
        raise ValueError(f"unknown scope(s) {bad}; scopes: {', '.join(st['scope_map'])}")
    stages = []
    for s in scopes:
        for stage in st["scope_map"][s]:
            if stage not in stages:
                stages.append(stage)
    stages.sort(key=order(st).index)
    pid = f"P{len(st.get('impact_plans') or {}) + 1:03d}"
    prev = {s: st["stages"][s]["status"] for s in stages}
    gates = {g: dict(st["gates"][g]) for g in (gate_after(st, s) for s in stages) if g}
    pj = load_project()
    prev_intake = {k: pj.get(k) for k in ("intake_confirmed", "intake_confirmed_at", "intake_confirmed_by")}
    mark_stale(st, stages, f"impact plan {pid}: {title}")
    st.setdefault("impact_plans", {})[pid] = {
        "status": "awaiting", "title": title, "scopes": scopes, "items": items, "stages": stages,
        "prev_status": prev, "prev_gates": gates, "prev_intake": prev_intake,
        "file": f"gates/impact-{pid}.md", "created_at": core.now()}
    save_state(st, "plan", plan=pid, scopes=scopes, stages=stages)
    return pid, stages


# ----------------------------------------------------------------- approvals (human only)
def resolve_target(st: dict, name: str) -> tuple[str | None, str | None]:
    n = name.strip().lower().replace(" ", "")
    if n.startswith("impact-"):
        n = n[len("impact-"):]
    for pid in st.get("impact_plans") or {}:
        if n == pid.lower():
            return "plan", pid
    if n in st["gates"]:
        return "gate", n
    if n in GATE_ALIASES:
        return "gate", GATE_ALIASES[n]
    return None, None


def record_decision(title: str, note: str | None, by: str) -> None:
    p = core.path("decisions.md")
    text = core.read_text(p) or "# Decisions\n"
    n = len(re.findall(r"^## D-\d+", text, re.M)) + 1
    entry = f"\n## D-{n:03d} (human) {core.today()} — {title}\n- Decision: {note or '(no note given)'}\n" \
            f"- Recorded via: {by}\n"
    core.write_text(p, text.rstrip("\n") + "\n" + entry)


def approve(name: str, by: str, note: str | None = None, force: bool = False) -> tuple[bool, str]:
    st = load_state()
    kind, gid = resolve_target(st, name)
    if kind is None:
        known = [d["short"] for d in st["gates"].values()] + list(st.get("impact_plans") or {})
        return False, f"unknown gate or plan '{name}' (known: {', '.join(known)})"
    if kind == "plan":
        plan = st["impact_plans"][gid]
        if plan["status"] != "awaiting" and not force:
            return False, f"impact plan {gid} is {plan['status']}, not awaiting approval"
        plan.update(status="approved", approved_by=by, approved_at=core.now(), note=note)
        save_state(st, "approve", plan=gid, by=by, note=note)
        record_decision(f"Impact plan {gid} APPROVED: {plan['title']}", note, by)
        return True, f"impact plan {gid} approved; stale stages will be re-run: {', '.join(plan['stages'])}"
    g = st["gates"][gid]
    if gid == "gate0_intake":
        pj = load_project()
        miss = intake_missing(pj)
        if miss and not force:
            return False, "cannot confirm intake: project.json is missing " + ", ".join(miss)
        if st["stages"]["topic-fit-check"]["status"] != "done" and not force:
            return False, ("cannot confirm intake yet: the intake skill has not finished (journal-profile.md, "
                           "topic fit, gates/gate0_intake.md)")
        pj.update(intake_confirmed=True, intake_confirmed_at=core.now(), intake_confirmed_by=by)
        save_project(pj)
    elif g["status"] != "awaiting" and not force:
        return False, (f"{gid} is not awaiting approval (status: {g['status']}); stage '{g['after']}' "
                       "has not produced its gate summary yet")
    g.update(status="approved", approved=True, approved_by=by, approved_at=core.now(), note=note)
    save_state(st, "approve", gate=gid, by=by, note=note)
    record_decision(f"{g['label']} — APPROVED ({gid})", note, by)
    return True, f"{gid} approved" + (f" with note: {note}" if note else "")


def reject(name: str, by: str, note: str | None = None) -> tuple[bool, str]:
    st = load_state()
    kind, gid = resolve_target(st, name)
    if kind is None:
        return False, f"unknown gate or plan '{name}'"
    if kind == "plan":
        plan = st["impact_plans"][gid]
        for s, prev in (plan.get("prev_status") or {}).items():
            if st["stages"][s]["status"] == "stale" and prev == "done":
                st["stages"][s]["status"] = "done"
                st["stages"][s]["stale_reason"] = None
        for g, prev_gate in (plan.get("prev_gates") or {}).items():
            if st["stages"][prev_gate["after"]]["status"] == "done":
                st["gates"][g] = prev_gate
        if plan.get("prev_intake", {}).get("intake_confirmed") and st["stages"]["topic-fit-check"]["status"] == "done":
            pj = load_project()
            pj.update(plan["prev_intake"])
            save_project(pj)
        plan.update(status="rejected", rejected_by=by, rejected_at=core.now(), note=note)
        save_state(st, "reject", plan=gid, by=by, note=note)
        record_decision(f"Impact plan {gid} REJECTED: {plan['title']}", note, by)
        return True, f"impact plan {gid} rejected; stage statuses restored"
    g = st["gates"][gid]
    redo = ["intake", "topic-fit-check"] if gid == "gate0_intake" else [g["after"]]
    mark_stale(st, redo, f"human rejected {gid}: {note or 'no note'}")
    g.update(status="rejected", note=note)
    save_state(st, "reject", gate=gid, by=by, note=note)
    record_decision(f"{g['label']} — REJECTED ({gid})", note, by)
    return True, f"{gid} rejected; '{', '.join(redo)}' will be redone taking the note into account"


# ----------------------------------------------------------------- next / status
def _act(action: str, code: int, **kw) -> dict:
    return {"action": action, "code": code, "stage": kw.get("stage"), "gate": kw.get("gate"),
            "plan": kw.get("plan"), "detail": kw.get("detail", "")}


def next_action(st: dict | None = None) -> dict:
    st = st or load_state()
    miss = intake_missing()
    if miss:
        return _act("INTAKE", 11, stage="intake", detail="intake incomplete, missing: " + ", ".join(miss))
    for s in order(st):
        info = st["stages"][s]
        if info["status"] != "done":
            plan = blocking_plan(st, s)
            if plan:
                return _act("PLAN", 10, plan=plan, detail=f"impact plan {plan} awaits human approval: read "
                            f"{st['impact_plans'][plan]['file']}, then type `APPROVE {plan}` or `REJECT {plan}: why`")
            for g in gates_before(st, s):
                if not gate_ok(st, g):
                    return _act("GATE", 10, gate=g, detail=_gate_detail(st, g))
            if s == "revision" and current_round(st) is None:
                loose = loose_external_files()
                hint = f" (found loose files {loose[:3]}: move them into reviews/external/round-1/)" if loose else ""
                return _act("WAIT", 10, stage=s, detail="waiting for real reviewer comments in "
                            "reviews/external/round-N/" + hint)
            reason = f": {info['stale_reason']}" if info.get("stale_reason") else ""
            return _act("RUN", 0, stage=s, detail=f"{s} ({info['status']}{reason})")
        g = gate_after(st, s)
        if g and not gate_ok(st, g):
            return _act("GATE", 10, gate=g, detail=_gate_detail(st, g))
    if current_round(st) is not None:
        return _act("RUN", 0, stage="revision", detail=f"revision round {current_round(st)}")
    return _act("DONE", 12, detail="all stages done and approved")


def _gate_detail(st: dict, g: str) -> str:
    d = st["gates"][g]
    return (f"{g} ({d['label']}) awaits the human: read {d['file']}, then type `APPROVE {d['short']} <notes>` "
            f"or `REJECT {d['short']}: <why>` in chat (or run `./ra state approve {d['short']}` in a terminal)")


def status_text(st: dict | None = None, brief: bool = False) -> str:
    """brief=True leaves out the journal and topic (used where a conversation may not stay on this paper)."""
    st = st or load_state()
    pj = load_project()
    j = pj.get("journal") or {}
    miss = intake_missing()
    if miss:
        intake = "INCOMPLETE (missing: " + ", ".join(miss) + ")"
    else:
        intake = ("" if brief else f"{j.get('name')} [{j.get('article_type')}] - ") + (
            "confirmed" if intake_confirmed(pj) else "NOT confirmed by human")
    lines = [f"Journal/intake: {intake}"] + ([] if brief else [f"Topic: {pj.get('topic') or '(not set)'}"]) + ["Stages:"]
    marks = {"done": "[x]", "pending": "[ ]", "stale": "[~]", "in_progress": "[>]"}
    for s in order(st):
        info = st["stages"][s]
        extra = f"  - {info['stale_reason']}" if info["status"] == "stale" and info.get("stale_reason") else ""
        lines.append(f"  {marks.get(info['status'], '[?]')} {s:<18} {info['status']}{extra}")
    lines.append("Gates:")
    for g, d in st["gates"].items():
        status = ("approved" if gate_ok(st, g) else d["status"]) if g == "gate0_intake" else d["status"]
        lines.append(f"  {g:<15} {status:<11} {d['file']}")
    plans = st.get("impact_plans") or {}
    if plans:
        lines.append("Impact plans:")
        for pid, p in plans.items():
            lines.append(f"  {pid} {p['status']:<9} [{','.join(p['scopes'])}] {p['title']} -> {', '.join(p['stages'])}")
    pend = feedbackcore.pending_summary(st)
    if pend:
        lines.append(f"Pending human feedback: {pend}")
    nxt = next_action(st)
    lines.append(f"Next: {nxt['action']} - {nxt['detail']}")
    return "\n".join(lines)
