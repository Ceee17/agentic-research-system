"""./ra limits — check the manuscript against the journal's limits and requirements.

Reads the ```json block in journal-profile.md ("limits", "required_sections", "required_files";
"ai_disclosure" is ignored) and measures paper/main.tex (texcount when available, else an approximation).
Workspace rules are part of the verdict: no formulas in the abstract, no AI-use statement.
  --report PATH   write a markdown report (e.g. reviews/internal/format-report.md)
Exit 1 if any hard limit or requirement fails.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
from ra import bibcheck, core, latex, rules, tex  # noqa: E402


def profile_spec() -> dict:
    text = core.read_text(core.path("journal-profile.md")) or ""
    for block in re.findall(r"```json\s*(.*?)```", text, re.S):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "limits" in data:
            return data
    return {}


def flatten(path: Path, depth: int = 0) -> str:
    text = core.read_text(path) or ""
    if depth > 10:
        return text

    def repl(m):
        name = m.group(1).strip()
        cand = (path.parent / name) if name.endswith(".tex") else (path.parent / (name + ".tex"))
        if not cand.exists():
            cand = core.path("paper", name if name.endswith(".tex") else name + ".tex")
        return flatten(cand, depth + 1) if cand.exists() else ""
    return re.sub(r"\\(?:input|include)\s*\{([^}]+)\}", repl, tex.strip_comments(text))


def approx_words(body: str) -> int:
    body = re.sub(r"\\begin\{(equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{\1\*?\}", " ", body, flags=re.S)
    body = re.sub(r"\\\[.*?\\\]|\$\$.*?\$\$|\$[^$]*\$", " ", body, flags=re.S)
    body = re.sub(r"\\(cite\w*|ref|eqref|label|includegraphics|url)\*?(\[[^\]]*\])*\{[^}]*\}", " ", body)
    body = re.sub(r"\\[A-Za-z]+\*?", " ", body)
    return len(re.findall(r"[A-Za-z][A-Za-z'\-]*", body))


def measure() -> dict:
    main = core.path("paper", "main.tex")
    full = flatten(main)
    body = full.split("\\begin{document}", 1)[-1].split("\\end{document}", 1)[0]
    main_text = re.split(r"\\bibliography\{|\\printbibliography|\\begin\{thebibliography\}", body)[0]
    words, method = None, "approximate"
    if latex.find_tool("texcount"):
        r = subprocess.run([latex.find_tool("texcount"), "-merge", "-sum", "-1", "-q", "main.tex"], cwd=str(core.path("paper")),
                           capture_output=True, text=True)
        m = re.match(r"\s*(\d+)", r.stdout)
        if m:
            words, method = int(m.group(1)), "texcount -sum"
    if words is None:
        words = approx_words(main_text)
    abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", body, re.S) or \
        re.search(r"\\abstract\{(.*?)\}\s*\n", full, re.S)
    kw = re.search(r"\\begin\{keywords?\}(.*?)\\end\{keywords?\}", body, re.S) or re.search(r"\\keywords\{(.*?)\}", full, re.S)
    keywords = [k.strip() for k in re.split(r"\\sep|,|;", kw.group(1)) if k.strip()] if kw else []
    title = re.search(r"\\title(?:\[[^\]]*\])?\{(.*?)\}", full, re.S)
    log = core.read_text(core.path("paper", "build", "main.log")) or ""
    pages = re.search(r"Output written on .*?\((\d+) pages?", log)
    sections = [re.sub(r"\s+", " ", s).strip() for s in re.findall(r"\\section\*?\{([^}]*)\}", body)]
    return {
        "words": words, "words_method": method,
        "abstract_words": approx_words(abstract.group(1)) if abstract else 0,
        "figures": len(re.findall(r"\\begin\{figure\*?\}", body)), "tables": len(re.findall(r"\\begin\{table\*?\}", body)),
        "references": len(bibcheck.collect_cites()), "keywords": len(keywords),
        "title_chars": len(" ".join(title.group(1).split())) if title else 0,
        "pages": int(pages.group(1)) if pages else None, "sections": sections,
    }


CHECKS = [("words_max", "words", "main-text words"), ("abstract_words_max", "abstract_words", "abstract words"),
          ("pages_max", "pages", "pages"), ("figures_max", "figures", "figures"), ("tables_max", "tables", "tables"),
          ("references_max", "references", "references"), ("keywords_max", "keywords", "keywords"),
          ("title_chars_max", "title_chars", "title characters")]


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra limits", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report")
    a = ap.parse_args()
    if not core.path("paper", "main.tex").exists():
        print("paper/main.tex not found", file=sys.stderr)
        return 1
    spec = profile_spec()
    if not spec:
        print("journal-profile.md has no ```json block with \"limits\" (the intake skill must write it)", file=sys.stderr)
        return 1
    m = measure()
    lim = spec.get("limits", {})
    rows, fail = [], False
    for lkey, mkey, label in CHECKS:
        cap, val = lim.get(lkey), m.get(mkey)
        if cap is None:
            rows.append((label, val, "-", "no limit"))
            continue
        if val is None:
            rows.append((label, "unknown", cap, "UNKNOWN (compile first)"))
            continue
        ok = val <= cap
        fail |= not ok
        rows.append((label, val, cap, "PASS" if ok else "FAIL"))
    if lim.get("keywords_min") and m["keywords"] < lim["keywords_min"]:
        fail = True
        rows.append(("keywords (min)", m["keywords"], lim["keywords_min"], "FAIL"))
    missing_sections = [s for s in spec.get("required_sections", [])
                        if not any(s.lower() in x.lower() or x.lower() in s.lower() for x in m["sections"])]
    missing_files = [f for f in spec.get("required_files", []) if not list(core.path("paper").glob(f"{f}*"))]
    ai_hits = rules.ai_statement_violations()
    abstract_v = rules.abstract_violations()
    fail |= bool(missing_sections or missing_files or ai_hits or abstract_v)
    out = ["# Format / limits report", "", f"_Generated by `./ra limits` on {core.now()}; word count method: "
           f"{m['words_method']}_", "", "| item | value | limit | status |", "|---|---|---|---|"]
    out += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows]
    out += ["", f"- Sections found: {', '.join(m['sections']) or '(none)'}",
            f"- Required sections missing: {', '.join(missing_sections) or 'none'}",
            f"- Required files missing (paper/<name>*): {', '.join(missing_files) or 'none'}",
            f"- Abstract formulas (workspace rule: none): {len(abstract_v) or 'none'}",
            f"- AI-use / AI-assistance statement (workspace rule: none): {len(ai_hits) or 'none'}",
            "", f"**Overall: {'FAIL' if fail else 'PASS'}**", ""]
    report = "\n".join(out)
    print(report)
    if a.report:
        core.write_text(core.resolve_arg(a.report), report + "\n## Agent notes\n\n")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
