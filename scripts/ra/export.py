"""Overleaf export: a self-contained, upload-ready project zip + PDFs.

exports/<slug>-overleaf.zip   main.tex at the root, sections/, generated/, figures/, .bib/.bst/.cls,
                              every other standalone document (cover page, biographies, response letters)
exports/<slug>.pdf            main document compiled FROM THE ZIP (proves it is self-contained),
exports/<slug>-<doc>.pdf      other standalone documents; diff PDFs are copied as <slug>-diff-round-N.pdf
exports/export.json           what was built, from which sources, and any problems

Paths are rewritten in the exported copy only (e.g. ../figures/x.pdf -> figures/x.pdf); sources are untouched.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from . import core, latex, tex

SUPPORT_EXT = {".bib", ".bst", ".cls", ".sty", ".clo", ".cfg", ".def", ".bbx", ".cbx", ".tex"}
FIG_EXT = [".pdf", ".png", ".jpg", ".jpeg", ".eps"]
SKIP_DIRS = ("build/", "export/")
SKIP_FILES = {"references.verified.json"}
SHELL_ESCAPE = {"minted", "pythontex", "svg", "gnuplottex", "shellesc", "bashful"}
ZIP_TIME = (2020, 1, 1, 0, 0, 0)
INCLUDE_RE = re.compile(r"\\(input|include)\s*\{([^}]+)\}")
GRAPHICS_RE = re.compile(r"\\includegraphics\s*(\[[^\]]*\])?\s*\{([^}]+)\}")
GPATH_RE = re.compile(r"\\graphicspath\s*\{((?:\s*\{[^}]*\})*)\s*\}")
BIB_RE = re.compile(r"\\(bibliography|addbibresource)\s*(\[[^\]]*\])?\s*\{([^}]+)\}")
BST_RE = re.compile(r"\\bibliographystyle\s*\{([^}]+)\}")
PKG_RE = re.compile(r"\\usepackage\s*(\[[^\]]*\])?\s*\{([^}]+)\}")
STD_BST = {"plain", "plainnat", "abbrv", "abbrvnat", "alpha", "unsrt", "unsrtnat", "apalike", "ieeetr", "siam",
           "acm", "amsplain", "amsalpha", "agsm", "dcu", "kluwer", "chicago", "apacite", "IEEEtran", "elsarticle-num",
           "elsarticle-harv", "model1-num-names", "spbasic", "spmpsci", "splncs04", "sn-basic", "sn-mathphys"}


def _is_standalone(text: str) -> bool:
    return re.search(r"^\s*\\documentclass", tex.strip_comments(text), re.M) is not None


def _paper_rel(p: Path) -> str:
    return os.path.relpath(p, core.path("paper")).replace(os.sep, "/")


def source_files() -> list[Path]:
    pdir = core.path("paper")
    out = []
    for p in sorted(pdir.rglob("*")):
        r = _paper_rel(p)
        if not p.is_file() or r.startswith(SKIP_DIRS) or p.name in SKIP_FILES or p.name.startswith("."):
            continue
        if p.suffix.lower() in SUPPORT_EXT or r.startswith("generated/"):
            out.append(p)
    return out


def _closure(entry: Path, texts: dict[str, str], seen: set[str]) -> None:
    r = _paper_rel(entry)
    if r in seen or r not in texts:
        return
    seen.add(r)
    for m in INCLUDE_RE.finditer(tex.strip_comments(texts[r])):
        name = m.group(2).strip()
        target = name if name.endswith(".tex") else name + ".tex"
        _closure(core.path("paper", target), texts, seen)


def _resolve_graphic(target: str, gpaths: list[str]) -> Path | None:
    pdir = core.path("paper")
    for base in [""] + gpaths:
        cand = (pdir / base / target).resolve()
        options = [cand] if cand.suffix.lower() in FIG_EXT else [cand.with_name(cand.name + e) for e in FIG_EXT]
        for o in options:
            if o.is_file():
                return o
    return None


def build(compile_pdf: bool = True) -> dict:
    slug = core.active_paper()
    pdir = core.path("paper")
    result = {"status": "ok", "problems": [], "warnings": [], "zip": None, "pdfs": [], "pdf_note": None}
    if not (pdir / "main.tex").exists():
        result.update(status="no-main", problems=["paper/main.tex does not exist yet"])
        return result
    files = source_files()
    texts = {_paper_rel(p): core.read_text(p) or "" for p in files if p.suffix == ".tex"}
    docs = ["main.tex"] + sorted(r for r, t in texts.items() if r != "main.tex" and _is_standalone(t)
                                 and not r.startswith("generated/"))
    reach: set[str] = set()
    for d in docs:
        _closure(core.path("paper", d), texts, reach)
    out: dict[str, bytes] = {}
    for p in files:
        r = _paper_rel(p)
        if p.suffix == ".tex" and r not in reach and not r.startswith("generated/"):
            continue
        out[r] = p.read_bytes()

    # standalone documents outside paper/: response letters
    for letter in sorted(core.path("reviews", "response").glob("round-*/response-letter.tex")):
        arc = f"response-letter-{letter.parent.name}.tex"
        out[arc] = letter.read_bytes()
        texts[arc] = core.read_text(letter) or ""
        docs.append(arc)
        reach.add(arc)

    # figures: resolve against \graphicspath, copy into the zip, rewrite to explicit project paths
    main_text = tex.strip_comments(texts.get("main.tex", ""))
    gpaths = []
    gm = GPATH_RE.search(main_text)
    if gm:
        gpaths = re.findall(r"\{([^}]*)\}", gm.group(1))
    for r in sorted(x for x in reach if x.endswith(".tex")):
        body = core.norm_newlines(out[r].decode("utf-8", errors="replace"))
        clean = tex.strip_comments(body)

        def fix(m):
            opts, target = m.group(1) or "", m.group(2).strip()
            if re.match(r"^([A-Za-z]:|/|~)", target):
                result["problems"].append(f"{r}: absolute graphics path '{target}'")
                return m.group(0)
            src = _resolve_graphic(target, gpaths)
            if src is None:
                result["problems"].append(f"{r}: figure '{target}' not found")
                return m.group(0)
            rp = core.rel(src) or ""
            arc = rp[len("paper/"):] if rp.startswith("paper/") else "figures/" + src.name
            out[arc] = src.read_bytes()
            shown = arc if Path(target).suffix else arc[: -len(src.suffix)]
            return f"\\includegraphics{opts}{{{shown}}}"
        if GRAPHICS_RE.search(clean):
            body = GRAPHICS_RE.sub(fix, body)
        body = GPATH_RE.sub(lambda m: "\\graphicspath{{./}{figures/}}", body)
        for m in INCLUDE_RE.finditer(tex.strip_comments(body)):
            name = m.group(2).strip()
            target = name if name.endswith(".tex") else name + ".tex"
            if ".." in target or re.match(r"^([A-Za-z]:|/|~)", target):
                result["problems"].append(f"{r}: \\{m.group(1)}{{{name}}} points outside the project")
            elif target not in out:
                result["problems"].append(f"{r}: \\{m.group(1)}{{{name}}} -> {target} is missing")
        for m in BIB_RE.finditer(tex.strip_comments(body)):
            for b in m.group(3).split(","):
                b = b.strip()
                b = b if b.endswith(".bib") else b + ".bib"
                if b not in out:
                    result["problems"].append(f"{r}: bibliography {b} is missing")
        for m in BST_RE.finditer(tex.strip_comments(body)):
            s = m.group(1).strip()
            if s not in STD_BST and f"{s}.bst" not in out:
                result["warnings"].append(f"{r}: bibliography style {s}.bst is not in the project (fine only if "
                                          "it is on CTAN / Overleaf)")
        for m in PKG_RE.finditer(tex.strip_comments(body)):
            for pkg in m.group(2).split(","):
                if pkg.strip() in SHELL_ESCAPE:
                    result["warnings"].append(f"{r}: package '{pkg.strip()}' needs shell-escape")
        if "\\write18" in body:
            result["problems"].append(f"{r}: uses \\write18 (shell escape)")
        out[r] = body.encode("utf-8")

    others = [d for d in docs if d != "main.tex"]
    readme = ["Overleaf project export", "",
              "Upload: Overleaf > New Project > Upload Project > select this zip.",
              "Compiler: pdfLaTeX. Main document: main.tex."]
    if others:
        readme.append("Other standalone documents (set each as main document to compile it): " + ", ".join(others) + ".")
    readme += ["Numbers in the text come from generated/results.tex (generated from the results; do not edit).", ""]
    out["README.txt"] = "\n".join(readme).encode("utf-8")

    exports = core.path("exports")
    exports.mkdir(parents=True, exist_ok=True)
    zpath = exports / f"{slug}-overleaf.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for arc in sorted(out):
            info = zipfile.ZipInfo(arc, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, out[arc])
    zpath.write_bytes(buf.getvalue())
    result["zip"] = core.rel(zpath)
    result["files"] = len(out)
    result["sha256"] = hashlib.sha256(buf.getvalue()).hexdigest()

    for diff in sorted(core.path("reviews", "response").glob("round-*/diff.pdf")):
        dest = exports / f"{slug}-diff-{diff.parent.name}.pdf"
        shutil.copyfile(diff, dest)
        result["pdfs"].append(core.rel(dest))

    if compile_pdf and not result["problems"]:
        if latex.latexmk_available():
            tmp = Path(tempfile.mkdtemp(prefix="ra-export-"))
            try:
                with zipfile.ZipFile(zpath) as z:
                    z.extractall(tmp)
                for d in docs:
                    proc = latex.run_latexmk(tmp, d, ".", timeout=int(os.environ.get("RA_EXPORT_TIMEOUT", "300")))
                    pdf = tmp / (d[:-4] + ".pdf")
                    if proc is None or proc.returncode != 0 or not pdf.exists():
                        log = core.read_text(tmp / (d[:-4] + ".log")) or ""
                        errs = latex.summarize_log(log)["errors"][:3] or ["latexmk failed"]
                        result["problems"].append(f"exported {d} does not compile: {'; '.join(errs)}")
                        continue
                    name = f"{slug}.pdf" if d == "main.tex" else f"{slug}-{Path(d).stem}.pdf"
                    shutil.copyfile(pdf, exports / name)
                    result["pdfs"].append(core.rel(exports / name))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        else:
            result["pdf_note"] = "no TeX installation found here: open the zip in Overleaf to get the PDF"
    if result["problems"]:
        result["status"] = "failed"
    core.write_json(exports / "export.json", {k: v for k, v in result.items()} | {"built_at": core.now()})
    return result


def format_result(res: dict) -> str:
    lines = [f"export: {res['status']}" + (f" -> {res['zip']} ({res.get('files')} files)" if res.get("zip") else "")]
    lines += [f"  PDF   {p}" for p in res.get("pdfs", [])]
    if res.get("pdf_note"):
        lines.append(f"  note: {res['pdf_note']}")
    lines += [f"  ERROR {p}" for p in res.get("problems", [])]
    lines += [f"  WARN  {w}" for w in res.get("warnings", [])]
    return "\n".join(lines)
