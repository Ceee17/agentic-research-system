"""Attribution of paper edits and LOCKED-region snapshots.

Shadow copies (.ra/shadow/<path>) hold the last content *the agent* wrote to each
paper/*.tex file. Any difference between a file and its shadow is a human edit the
agent has not yet registered (channel 1). This works independently of git commits;
when no shadow exists the git HEAD version is used as the baseline.

The lock snapshot (.ra/locks.json) records LOCKED regions at the start of every human
turn, so a Stop hook can detect tampering by any means (e.g. shell commands).
"""
from __future__ import annotations

import difflib
import os
import re

from . import core, tex

EXCLUDE = ("paper/build/", "paper/generated/")


def tracked(r: str | None) -> bool:
    return bool(r) and r.startswith("paper/") and r.endswith(".tex") and not r.startswith(EXCLUDE)


def _shadow_path(r: str):
    return core.path(".ra", "shadow", *r.split("/"))


def record(r: str) -> None:
    """Mark the current content of `r` as agent-authored (baseline)."""
    if not tracked(r):
        return
    cur = core.read_text(core.path(r))
    sp = _shadow_path(r)
    if cur is None:
        if sp.exists():
            sp.unlink()
        return
    core.write_text(sp, core.norm_newlines(cur))


def baseline(r: str) -> str | None:
    s = core.read_text(_shadow_path(r))
    if s is not None:
        return core.norm_newlines(s)
    return core.git_head_file(r)


def has_unregistered_change(r: str) -> bool:
    if not tracked(r):
        return False
    cur, base = core.read_text(core.path(r)), baseline(r)
    if cur is None or base is None:
        return False
    return core.norm_newlines(cur) != base


def _candidate_files() -> set[str]:
    files = {core.rel(p) for p in tex.tex_files("paper", exclude=EXCLUDE)}
    sroot = core.path(".ra", "shadow")
    if sroot.exists():
        for p in sroot.rglob("*.tex"):
            files.add(os.path.relpath(p, sroot).replace(os.sep, "/"))
    return {f for f in files if tracked(f)}


def changed() -> list[dict]:
    """Paper files whose content differs from the agent baseline (i.e. human edits)."""
    out = []
    for r in sorted(_candidate_files()):
        cur = core.read_text(core.path(r))
        cur = core.norm_newlines(cur) if cur is not None else None
        base = baseline(r)
        if cur is not None and base is None:
            status = "added"
        elif cur is None and base is not None:
            status = "deleted"
        elif cur is not None and cur != base:
            status = "modified"
        else:
            continue
        diff = "".join(difflib.unified_diff(
            (base or "").splitlines(True), (cur or "").splitlines(True),
            fromfile=f"a/{r} (agent baseline)", tofile=f"b/{r} (current)", n=2))
        out.append({"id": f"e:{r}", "file": r, "status": status, "diff": diff,
                    "hints": classify_hints(base or "", cur or "")})
    return out


def classify_hints(old: str, new: str) -> list[str]:
    """Cheap hints that a human edit may be more than wording (the agent decides)."""
    hints = []
    removed = "\n".join(l for l in difflib.ndiff(old.splitlines(), new.splitlines()) if l.startswith(("- ", "+ ")))
    if re.search(r"\\begin\{(theorem|lemma|proposition|corollary|definition|proof)", removed):
        hints.append("touches a theorem/definition environment -> maybe 'claims'")
    if re.search(r"\\cite", removed):
        hints.append("changes citations -> check claims/citations")
    if re.search(r"\d+\.\d+|\\%", removed):
        hints.append("changes numbers -> maybe 'claims' (numbers must trace to results/)")
    if re.search(r"\\(section|subsection)\*?\{", removed):
        hints.append("changes section structure -> maybe structural")
    if re.search(r"\\includegraphics|\\begin\{figure", removed):
        hints.append("changes figures -> maybe 'figures'")
    if re.search(r"\b(novel|first|contribution|we propose|we show)\b", removed, re.I):
        hints.append("touches contribution/novelty language -> maybe 'novelty'")
    return hints


def word_substitutions(old: str, new: str, max_len: int = 4) -> list[tuple[str, str]]:
    """Short phrase replacements (old -> new) between two texts, for style learning."""
    a, b = re.findall(r"\S+", old), re.findall(r"\S+", new)
    pairs = []
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "replace" and (i2 - i1) <= max_len and (j2 - j1) <= max_len:
            o, n = " ".join(a[i1:i2]), " ".join(b[j1:j2])
            if o.lower().strip(".,;:") != n.lower().strip(".,;:"):
                pairs.append((o, n))
        elif op == "delete" and (i2 - i1) <= 2:
            pairs.append((" ".join(a[i1:i2]), ""))
    return pairs


# ---------------------------------------------------------------- lock snapshots
LOCKS = (".ra", "locks.json")


def snapshot_locks() -> None:
    snap = {}
    for p in tex.tex_files("paper"):
        blocks = tex.locked_blocks(core.read_text(p))
        if blocks:
            snap[core.rel(p)] = blocks
    core.write_json(core.path(*LOCKS), {"taken_at": core.now(), "files": snap})


def snapshot_blocks(r: str) -> list[str] | None:
    data = core.read_json(core.path(*LOCKS), {}) or {}
    return (data.get("files") or {}).get(r)


def lock_violations() -> list[str]:
    """LOCKED regions from the last snapshot that are missing or altered now."""
    data = core.read_json(core.path(*LOCKS), {}) or {}
    problems = []
    for r, blocks in (data.get("files") or {}).items():
        current = tex.locked_blocks(core.read_text(core.path(r)))
        remaining = list(current)
        for b in blocks:
            if b in remaining:
                remaining.remove(b)
            else:
                first = b.split("\n")[1] if "\n" in b else b
                problems.append(f"{r}: LOCKED region changed or removed (began: {first[:70]!r})")
    return problems
