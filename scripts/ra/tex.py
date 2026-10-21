"""LaTeX helpers: comments, LOCKED regions, `% @agent` requests, file discovery."""
from __future__ import annotations

import re
from pathlib import Path

from . import core

LOCK_START = re.compile(r"^\s*%+\s*LOCKED-START\b")
LOCK_END = re.compile(r"^\s*%+\s*LOCKED-END\b")
# `% @agent: request` or `% @agent[claims]: request`
AGENT_RE = re.compile(r"%+\s*@agent(?:\[(?P<scope>[A-Za-z_-]+)\])?\s*:?\s*(?P<req>.*)$")
AGENT_MARK = re.compile(r"(?<!\\)%+\s*@agent\b")
NUM_OK_MARK = "@num-ok"

PAPER_EXCLUDE = ("paper/build/",)


def comment_start(line: str) -> int:
    """Index of the first unescaped % in `line`, or -1."""
    i = 0
    while True:
        j = line.find("%", i)
        if j < 0:
            return -1
        k, n = j - 1, 0
        while k >= 0 and line[k] == "\\":
            n += 1
            k -= 1
        if n % 2 == 0:
            return j
        i = j + 1


def strip_comments(text: str) -> str:
    """Remove LaTeX comments, keeping line structure (line numbers stay valid)."""
    out = []
    for line in text.split("\n"):
        c = comment_start(line)
        out.append(line if c < 0 else line[:c])
    return "\n".join(out)


def locked_regions(text: str) -> list[dict]:
    """Regions between `% LOCKED-START` and `% LOCKED-END` (marker lines included).

    An unclosed LOCKED-START locks everything to end of file (fail safe).
    """
    lines = core.norm_newlines(text).split("\n")
    regions, start = [], None
    for i, line in enumerate(lines):
        if start is None and LOCK_START.match(line):
            start = i
        elif start is not None and LOCK_END.match(line):
            regions.append({"start": start + 1, "end": i + 1, "text": "\n".join(lines[start:i + 1])})
            start = None
    if start is not None:
        regions.append({"start": start + 1, "end": len(lines), "text": "\n".join(lines[start:]), "unclosed": True})
    return regions


def locked_blocks(text: str | None) -> list[str]:
    return [r["text"] for r in locked_regions(text or "")]


def agent_comments(text: str) -> list[dict]:
    """All `% @agent` requests in `text` with 1-based line numbers."""
    found = []
    for i, line in enumerate(core.norm_newlines(text).split("\n"), start=1):
        c = comment_start(line)
        if c < 0:
            continue
        m = AGENT_RE.match(line[c:])
        if m:
            found.append({
                "line": i,
                "scope": (m.group("scope") or "").lower() or None,
                "request": m.group("req").strip(),
                "raw": line,
                "code_before": line[:c].rstrip(),
            })
    return found


def count_agent_marks(text: str | None) -> int:
    return len(AGENT_MARK.findall(text or ""))


def tex_files(base: str = "paper", exclude: tuple[str, ...] = PAPER_EXCLUDE) -> list[Path]:
    """All .tex files under `base` (project-relative), skipping build output."""
    d = core.path(base)
    if not d.exists():
        return []
    files = []
    for p in sorted(d.rglob("*.tex")):
        r = core.rel(p)
        if r and not any(r.startswith(x) for x in exclude):
            files.append(p)
    return files


def all_agent_comments(base: str = "paper") -> list[dict]:
    """`% @agent` requests across the paper, each with a stable id."""
    items = []
    for p in tex_files(base):
        text = core.read_text(p) or ""
        r = core.rel(p)
        for c in agent_comments(text):
            c["file"] = r
            c["id"] = "c:" + core.short_hash(f"{r}|{c['request']}")
            items.append(c)
    return items


def human_protected_units(text: str) -> list[str]:
    """Units of a markdown file marked `(human)` that the agent may never alter.

    A heading containing `(human)` protects its whole section (until the next heading
    of the same or higher level); any other line containing `(human)` protects that line.
    """
    lines = core.norm_newlines(text or "").split("\n")
    units, i = [], 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(#{1,6})\s", line)
        if m and "(human)" in line:
            level = len(m.group(1))
            j = i + 1
            while j < len(lines):
                m2 = re.match(r"^(#{1,6})\s", lines[j])
                if m2 and len(m2.group(1)) <= level:
                    break
                j += 1
            units.append("\n".join(lines[i:j]).rstrip())
            i = j
            continue
        if "(human)" in line:
            units.append(line.rstrip())
        i += 1
    return [u for u in units if u.strip()]
