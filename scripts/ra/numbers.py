"""Every decimal or percentage printed in the paper must trace to a file in results/.

Integers are not checked (counts, section numbers, years). Numbers produced through
the generated macros (\\resXxx, paper/generated/results.tex) are traceable by construction.
A human may exempt a line with a trailing `% @num-ok` comment (agents may not add it).
"""
from __future__ import annotations

import re

from . import core, results, tex

EXCLUDE = ("paper/build/", "paper/generated/")
IGNORE_FILES = {"paper/ai-disclosure.tex"}

STRIP_CMDS = re.compile(
    r"\\(?:label|ref|eqref|cref|Cref|autoref|pageref|url|input|include|includegraphics|usepackage|documentclass|"
    r"bibliographystyle|bibliography|addbibresource|[A-Za-z]*cite[A-Za-z]*|vspace|hspace|setlength|addtolength|"
    r"setcounter|rule|resizebox|scalebox|multicolumn|multirow|cline|cmidrule|arraystretch|renewcommand|"
    r"href|hypersetup|geometry|definecolor|color|textcolor)\*?\s*(?:\[[^\]]*\]\s*)*(?:\{[^{}]*\}\s*){0,3}")
OPT_ARGS = re.compile(r"\\[A-Za-z]+\*?\s*\[[^\]]*\]")
TABULAR_SPEC = re.compile(r"\\begin\{(?:tabular\*?|tabularx|array|longtable)\}(?:\{[^{}]*\})?\s*\{[^{}]*\}")
BEGIN_OPT = re.compile(r"\\begin\{[^}]*\}\s*\[[^\]]*\]")
LINEBREAK_OPT = re.compile(r"\\\\\s*\[[^\]]*\]")
UNIT_AFTER = re.compile(r"\s*(?:pt|cm|mm|em|ex|in|bp|sp|\\textwidth|\\linewidth|\\columnwidth|\\textheight|"
                        r"\\baselineskip|\\paperwidth|\\hsize)\b")
DECIMAL = re.compile(r"(?<![\w.])(\d+\.\d+)(?!\w|\.\d)")  # not part of a version like 3.14.7
PERCENT = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*\\%")


class _Pool:
    def __init__(self, values: set[float]):
        self.values = [abs(v) for v in values]
        self._cache: dict = {}

    def _fmt(self, d: int, scale: float) -> set[str]:
        key = (d, scale)
        if key not in self._cache:
            self._cache[key] = {f"{v * scale:.{d}f}" for v in self.values}
        return self._cache[key]

    def has(self, printed: str, pct: bool) -> bool:
        d = len(printed.split(".")[1]) if "." in printed else 0
        norm = f"{float(printed):.{d}f}"
        if norm in self._fmt(d, 1.0):
            return True
        return pct and norm in self._fmt(d, 100.0)


def clean_line(line: str) -> str:
    s = TABULAR_SPEC.sub(" ", line)
    s = BEGIN_OPT.sub(" ", s)
    s = LINEBREAK_OPT.sub(" ", s)
    s = STRIP_CMDS.sub(" ", s)
    s = OPT_ARGS.sub(" ", s)
    return s


def untraceable(base: str = "paper") -> list[dict]:
    pool = None
    found = []
    for p in tex.tex_files(base, exclude=EXCLUDE):
        r = core.rel(p)
        if r in IGNORE_FILES:
            continue
        raw_lines = (core.read_text(p) or "").split("\n")
        for i, raw in enumerate(raw_lines, start=1):
            c = tex.comment_start(raw)
            if c >= 0 and tex.NUM_OK_MARK in raw[c:]:
                continue
            code = raw if c < 0 else raw[:c]
            if not re.search(r"\d", code):
                continue
            line = clean_line(code)
            hits = []
            for m in PERCENT.finditer(line):
                hits.append((m.group(1), True, m.start()))
            pct_spans = {m.start(1) for m in PERCENT.finditer(line)}
            for m in DECIMAL.finditer(line):
                if m.start(1) in pct_spans or UNIT_AFTER.match(line, m.end()):
                    continue
                hits.append((m.group(1), False, m.start()))
            for num, pct, pos in hits:
                if pool is None:
                    pool = _Pool(results.numeric_values())
                if not pool.has(num, pct):
                    found.append({"file": r, "line": i, "number": num + ("\\%" if pct else ""),
                                  "context": code.strip()[:160]})
    return found


def format_report(items: list[dict]) -> str:
    if not items:
        return "check-numbers: OK (every decimal/percentage in the paper matches a value in results/)"
    lines = [f"check-numbers: {len(items)} number(s) in the paper do not trace to any file in results/:"]
    for it in items:
        lines.append(f"  {it['file']}:{it['line']}: {it['number']}   | {it['context']}")
    lines.append("Fix: produce the value with `./ra run`, then use the generated macro from paper/generated/results.tex "
                 "(`./ra results-tex`). Do not type numbers by hand.")
    return "\n".join(lines)
