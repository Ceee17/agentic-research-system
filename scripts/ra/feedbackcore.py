"""Collection of human feedback from the four channels.

1. direct edits to paper/*.tex      -> shadow.changed()          ids  e:<path>
2. `% @agent: ...` inline comments  -> tex.all_agent_comments()  ids  c:<hash>
3. feedback/*.md files              -> feedback_files()          ids  fb:<filename>
4. LOCKED regions                   -> enforced by hooks (no processing needed)
"""
from __future__ import annotations

import re

from . import core, shadow, tex

FIELD_RE = re.compile(r"^(scope|change|keep|section|priority)\s*:\s*(.*)$", re.I)


def parse_feedback(text: str) -> dict:
    """Parse `scope:` / `change:` / `keep:` fields (multi-line values allowed)."""
    fields, cur = {}, None
    for line in core.norm_newlines(text).split("\n"):
        if line.strip() == "---":
            cur = None
            continue
        m = FIELD_RE.match(line)
        if m:
            cur = m.group(1).lower()
            val = m.group(2).strip()
            fields[cur] = "" if val in ("|", ">") else val
        elif cur and (line.startswith((" ", "\t")) or (line.strip() and fields.get(cur) == "")):
            fields[cur] = (fields[cur] + "\n" + line.strip()).strip()
        elif not line.strip():
            continue
        else:
            cur = None
    scopes = [s.strip().lower() for s in re.split(r"[,\s]+", fields.get("scope", "")) if s.strip()]
    return {"scopes": scopes, "change": fields.get("change", ""), "keep": fields.get("keep", ""),
            "section": fields.get("section"), "priority": fields.get("priority")}


def feedback_files() -> list[dict]:
    d = core.path("feedback")
    out = []
    if not d.exists():
        return out
    for p in sorted(d.glob("*.md")):
        if p.name.startswith("_") or p.name.lower() in ("readme.md", "log.md"):
            continue
        parsed = parse_feedback(core.read_text(p) or "")
        parsed.update({"id": f"fb:{p.name}", "file": core.rel(p)})
        out.append(parsed)
    return out


def items_in_plans(state: dict) -> set[str]:
    ids = set()
    for plan in (state.get("impact_plans") or {}).values():
        if plan.get("status") in ("awaiting", "approved"):
            ids.update(plan.get("items") or [])
    return ids


def collect(state: dict | None = None) -> dict:
    state = state or {}
    planned = items_in_plans(state)
    edits = shadow.changed()
    comments = tex.all_agent_comments()
    files = feedback_files()
    for group in (edits, comments, files):
        for it in group:
            it["in_plan"] = it["id"] in planned
    return {"edits": edits, "comments": comments, "files": files}


def pending(state: dict | None = None) -> dict:
    """Unprocessed items (not yet registered / resolved / attached to an impact plan)."""
    c = collect(state)
    return {k: [it for it in v if not it["in_plan"]] for k, v in c.items()}


def pending_summary(state: dict | None = None) -> str | None:
    p = pending(state)
    parts = []
    if p["edits"]:
        parts.append(f"{len(p['edits'])} human-edited paper file(s)")
    if p["comments"]:
        parts.append(f"{len(p['comments'])} `% @agent` comment(s)")
    if p["files"]:
        parts.append(f"{len(p['files'])} feedback file(s)")
    return ", ".join(parts) or None
