"""Papers in the workspace: create / list / activate, and one-paper-per-session binding.

Each paper is papers/<slug>/ with its own state, files and git repository. The human picks the
active paper (`PAPER <slug>` / `NEW PAPER <slug>` in chat, or `./ra paper use|new` in a terminal).

Session binding keeps papers from bleeding into each other through the conversation: a Claude
session that has acted on paper X is refused any action once the active paper is not X, until the
human clears the conversation (/clear) or opens a new session.
"""
from __future__ import annotations

import datetime as _dt
import json
import shutil
import subprocess

from . import core

SCAFFOLD = ("scripts", "scaffold")
PAPER_DIRS = ["templates", "literature/papers", "experiments", "results", "figures/scripts", "figures/tikz",
              "figures/diagrams", "paper/sections", "reviews/internal", "reviews/external", "reviews/response",
              "feedback/done", "gates", "exports"]
SESSIONS = (".ra", "sessions.json")
PRUNE_DAYS = 60


# ------------------------------------------------------------------ papers
def create(slug: str, git: bool = True) -> tuple[bool, str]:
    from . import pipeline
    if not core.SLUG_RE.match(slug or ""):
        return False, f"invalid paper name '{slug}': use lowercase letters, digits and hyphens (max 40), e.g. ai-tutors"
    d = core.papers_dir() / slug
    if d.exists():
        return False, f"papers/{slug} already exists (use `PAPER {slug}` to switch to it)"
    for sub in PAPER_DIRS:
        (d / sub).mkdir(parents=True, exist_ok=True)
        (d / sub / ".gitkeep").touch()
    sc = core.wpath(*SCAFFOLD)
    for name in ("project.json", "journal-profile.md", "style-guide.md", "decisions.md"):
        shutil.copyfile(sc / name, d / name)
    shutil.copyfile(sc / "feedback-TEMPLATE.md", d / "feedback" / "_TEMPLATE.md")
    shutil.copyfile(sc / "reference-justifications.md", d / "literature" / "reference-justifications.md")
    shutil.copyfile(sc / "gitignore", d / ".gitignore")
    core.write_text(d / "CLAUDE.md", (core.read_text(sc / "CLAUDE.md") or "").replace("{{slug}}", slug))
    core.write_json(d / "state.json", pipeline.default_state())
    msg = f"created papers/{slug}/"
    if git and shutil.which("git"):
        run = lambda *a: subprocess.run(["git", *a], cwd=str(d), capture_output=True, text=True)  # noqa: E731
        run("init", "-q")
        run("add", "-A")
        r = run("-c", "user.useConfigOnly=true", "commit", "-q", "-m", f"paper({slug}): scaffold")
        msg += " with its own git repository" + ("" if r.returncode == 0 else
                                                 " (no initial commit: set git user.name/user.email)")
    return True, msg


def status_line(slug: str) -> str:
    """Progress only: no topic or journal, so other papers' content never enters a conversation."""
    st = core.read_json(core.papers_dir() / slug / "state.json", {}) or {}
    stages = st.get("stages") or {}
    done = sum(1 for s in stages.values() if s.get("status") == "done")
    return f"{slug} ({done}/{len(stages) or 11} stages done)"


# ------------------------------------------------------------------ sessions
def _load() -> dict:
    return core.read_json(core.wpath(*SESSIONS), {}) or {}


def _save(data: dict) -> None:
    cutoff = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=PRUNE_DAYS)).isoformat()
    data = {k: v for k, v in data.items() if (v.get("at") or "") >= cutoff[:19]}
    core.write_json(core.wpath(*SESSIONS), data)


def session(sid: str | None) -> dict | None:
    return _load().get(sid) if sid else None


def on_session_start(sid: str | None, source: str | None) -> None:
    if not sid:
        return
    data = _load()
    if source in ("startup", "clear") or sid not in data:
        data[sid] = {"paper": core.active_paper(), "touched": source not in ("startup", "clear", None),
                     "at": core.now()}
        _save(data)


def bind_check(sid: str | None) -> str | None:
    """None if this session may act on the active paper (and marks it as having done so);
    otherwise the reason it may not."""
    if not sid:
        return None
    active = core.active_paper()
    data = _load()
    rec = data.get(sid)
    if rec is None or not rec.get("touched"):
        # a conversation that has not acted on any paper yet simply follows the active paper
        data[sid] = {"paper": active, "touched": active is not None, "at": core.now()}
        _save(data)
        return None
    if rec.get("paper") != active:
        was, now = rec.get("paper") or "(no paper)", active or "(no paper)"
        return (f"this conversation has been working on paper '{was}', but the active paper is now '{now}'. "
                f"To keep papers from mixing, one conversation works on one paper. Human: type `PAPER {was}` to "
                f"continue '{was}' here, or /clear (or open a new session) to work on '{now}'.")
    return None


def may_create(sid: str | None) -> str | None:
    """None if this conversation may create (and switch to) a NEW paper, i.e. it has not acted on any
    paper yet; otherwise the reason it may not."""
    rec = session(sid)
    if rec and rec.get("touched") and rec.get("paper"):
        return (f"this conversation already worked on paper '{rec['paper']}'. A new paper needs a fresh "
                "conversation so the two never mix: the human types /clear (or opens a new session), then "
                "/ra-init again.")
    return None


def request_switch(sid: str | None, slug: str, create_new: bool = False) -> tuple[bool, str]:
    """Human `PAPER <slug>` / `NEW PAPER <slug>` from the chat."""
    rec = session(sid)
    if rec and rec.get("touched") and rec.get("paper") and rec.get("paper") != slug:
        return False, (f"this conversation already worked on paper '{rec['paper']}'. Type /clear (or open a new "
                       f"session) first, then `{'NEW PAPER' if create_new else 'PAPER'} {slug}`, so the two papers' "
                       "context never mixes.")
    if create_new:
        ok, msg = create(slug)
        if not ok:
            return False, msg
    elif slug not in core.list_papers():
        papers = core.list_papers()
        return False, (f"no paper '{slug}' (existing: {', '.join(papers) or 'none'}); "
                       f"to start one, type `NEW PAPER {slug}`")
    else:
        msg = f"switched to papers/{slug}/"
    core.set_active_paper(slug)
    if sid:
        data = _load()
        data[sid] = {"paper": slug, "touched": False, "at": core.now()}
        _save(data)
    return True, msg + f"; active paper is now '{slug}'"


# ------------------------------------------------------------------ maintenance (framework edits)
MAINTENANCE = (".ra", "maintenance.json")


def maintenance_on(sid: str | None, minutes: int = 120) -> str:
    """Human `MAINTENANCE ON [minutes]`: this conversation may edit framework files for a while."""
    until = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=max(5, min(minutes, 480)))
    core.write_json(core.wpath(*MAINTENANCE), {"session": sid, "until": until.isoformat(), "by": "human (chat)",
                                                "at": core.now()})
    return until.astimezone().strftime("%H:%M")


def maintenance_off() -> None:
    p = core.wpath(*MAINTENANCE)
    if p.exists():
        p.unlink()


def maintenance_until(sid: str | None) -> str | None:
    """Local end time if maintenance mode is on for this conversation, else None."""
    m = core.read_json(core.wpath(*MAINTENANCE), {}) or {}
    if not m or not sid or m.get("session") != sid:
        return None
    try:
        until = _dt.datetime.fromisoformat(m["until"])
    except (KeyError, ValueError):
        return None
    if until <= _dt.datetime.now(_dt.timezone.utc):
        return None
    return until.astimezone().strftime("%H:%M")


def dumps_list() -> str:
    papers = core.list_papers()
    active = core.active_paper()
    if not papers:
        return "no papers yet (start one with `NEW PAPER <name>`)"
    return "\n".join(("* " if p == active else "  ") + status_line(p) for p in papers)


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(_load(), indent=2))
