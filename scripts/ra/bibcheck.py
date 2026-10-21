"""Core of verify_bib: every \\cite must resolve to a fetched, untampered, identified entry.

Ledger (paper/references.verified.json) is written only by `./ra fetch-bib`; it stores,
per key, the identifier, provenance, a content fingerprint and the source abstract.
"""
from __future__ import annotations

import difflib
import re

from . import bib, core, tex

LEDGER = ("paper", "references.verified.json")
BIBFILE = ("paper", "references.bib")
ALLOWED_BIB = {"references.bib"}

STOP = set("""a an the and or of in on for to with by from as at is are was were be been being this that these
those it its we our us they their them which who whom whose what when where how why than then also such via using
use used based can may might could would should will shall has have had not no do does did into onto over under
between among both each either neither more most less least very much many some any all other another same
different paper work works show shows shown result results propose proposed method methods approach approaches
model models prior previous recent recently studied study studies et al e g i eg ie cf see known well first""".split())


# ------------------------------------------------------------------ ledger
def load_ledger() -> dict:
    return core.read_json(core.path(*LEDGER), {"version": 1, "entries": {}}) or {"version": 1, "entries": {}}


def save_ledger(ledger: dict) -> None:
    core.write_json(core.path(*LEDGER), ledger)


def load_bib() -> list[dict]:
    return bib.parse(core.read_text(core.path(*BIBFILE)) or "")


# ------------------------------------------------------------------ helpers
def collect_cites(base: str = "paper") -> dict[str, list[str]]:
    where: dict[str, list[str]] = {}
    for p in tex.tex_files(base):
        r = core.rel(p)
        for key, line in bib.cites_in_tex(core.read_text(p) or ""):
            where.setdefault(key, []).append(f"{r}:{line}")
    return where


def referenced_bib_files(base: str = "paper") -> set[str]:
    files = set()
    for p in tex.tex_files(base):
        files.update(bib.bib_files_in_tex(core.read_text(p) or ""))
    return files


def _issue(code, key, msg, where=None):
    return {"code": code, "key": key, "msg": msg, "where": where or []}


def _stem(w: str) -> str:
    for suf in ("ations", "ation", "ities", "ity", "ings", "ing", "ness", "ies", "ied", "ed", "es", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def content_stems(text: str) -> set[str]:
    words = re.findall(r"[a-z]{3,}", bib.ascii_fold(bib.latex_to_plain(text)).lower())
    return {_stem(w) for w in words if w not in STOP}


_ABBREV = re.compile(r"\b(et al|e\.g|i\.e|cf|Fig|Figs|Eq|Eqs|Sec|Secs|Ref|Refs|Thm|Prop|vs|approx|resp)\.")


def sentence_around(text: str, start: int, end: int) -> str:
    para_start = text.rfind("\n\n", 0, start) + 1
    para_end = text.find("\n\n", end)
    para_end = len(text) if para_end < 0 else para_end
    para = _ABBREV.sub(lambda m: m.group(0).replace(".", "\x00"), text[para_start:para_end])
    offset = start - para_start
    pos = 0
    for s in re.split(r"(?<=[.!?])\s+", para):
        if pos <= offset < pos + len(s) + 1:
            return " ".join(s.replace("\x00", ".").split())
        pos += len(s) + 1
    return " ".join(para.replace("\x00", ".").split())[:400]


# ------------------------------------------------------------------ checks
def check(online: bool = False, claims: bool = False, claim_threshold: float = 0.12) -> dict:
    errors, warnings, info = [], [], []
    cites = collect_cites()
    entries = load_bib()
    keyed = bib.by_key(entries)
    ledger = load_ledger().get("entries", {})

    for f in sorted(referenced_bib_files()):
        if f.split("/")[-1] not in ALLOWED_BIB:
            errors.append(_issue("FOREIGN-BIB", f, f"paper uses bibliography file '{f}'; only paper/references.bib "
                                               "(written by ./ra fetch-bib) is allowed"))
    seen = {}
    for e in entries:
        if e["key"] in seen:
            errors.append(_issue("DUPLICATE-KEY", e["key"], "key appears more than once in references.bib"))
        seen[e["key"]] = True
    dois = {}
    for e in entries:
        d = bib.norm_doi(e["fields"].get("doi"))
        if d:
            if d.lower() in dois:
                warnings.append(_issue("DUPLICATE-DOI", e["key"], f"same DOI as '{dois[d.lower()]}' ({d})"))
            dois[d.lower()] = e["key"]

    nocite_all = "*" in cites
    if nocite_all:
        warnings.append(_issue("NOCITE-ALL", "*", "\\nocite{*} pulls every bib entry into the paper", cites.pop("*")))

    for key, where in sorted(cites.items()):
        e = keyed.get(key)
        if e is None:
            errors.append(_issue("MISSING", key, "cited but not in paper/references.bib -> "
                                 "`./ra fetch-bib add <DOI|arXiv>` (never hand-write entries)", where))
            continue
        led = ledger.get(key)
        if not led:
            errors.append(_issue("UNVERIFIED", key, "entry not fetched by ./ra fetch-bib (no ledger record)", where))
            continue
        if led.get("fingerprint") != bib.fingerprint(e):
            errors.append(_issue("TAMPERED", key, "entry differs from what was fetched; re-fetch with "
                                 "`./ra fetch-bib add --force <id>`", where))
        doi = bib.norm_doi(e["fields"].get("doi"))
        arx = e["fields"].get("eprint") if "arxiv" in (e["fields"].get("archiveprefix", "") +
                                                        e["fields"].get("eprinttype", "")).lower() else None
        if not doi and not arx:
            errors.append(_issue("NO-ID", key, "entry has neither a DOI nor an arXiv eprint", where))

    recency = _age_rule(cites, keyed, ledger, errors, warnings, every=[e["key"] for e in entries] if nocite_all else None)

    for key in ledger:
        if key not in keyed:
            warnings.append(_issue("LEDGER-ORPHAN", key, "ledger record without a bib entry"))
    uncited = [e["key"] for e in entries if e["key"] not in cites]
    if uncited:
        info.append(_issue("UNCITED", ",".join(uncited[:20]) + (" ..." if len(uncited) > 20 else ""),
                           f"{len(uncited)} fetched entries are not cited (fine; bibtex ignores them)"))

    report = {"errors": errors, "warnings": warnings, "info": info, "cited_keys": len(cites),
              "bib_entries": len(entries), "claims": [], "recency": recency}
    if online:
        _online(report, cites, keyed)
    if claims:
        report["claims"] = claim_support(threshold=claim_threshold)
    return report


def _age_rule(cites: dict, keyed: dict, ledger: dict, errors: list, warnings: list, every=None) -> dict:
    """Hard rule: cited works at most rules.MAX_YEARS old; 6-10-year-old ones need a justification."""
    from . import rules
    table = rules.justifications()
    counts = {"recent": 0, "justify": 0, "too-old": 0, "unknown": 0}
    for key in sorted(set(cites) | set(every or [])):
        e = keyed.get(key)
        if e is None:
            continue
        where = cites.get(key, [])
        f = e["fields"]
        year = rules.parse_year(f.get("year") or f.get("date") or (ledger.get(key) or {}).get("year"))
        cls = rules.age_class(year)
        counts[cls] += 1
        if cls == "unknown":
            errors.append(_issue("NO-YEAR", key, "no publication year: the reference-age rule cannot be checked", where))
        elif cls == "too-old":
            errors.append(_issue("REF-TOO-OLD", key, f"published {year}: more than {rules.MAX_YEARS} years old. Hard "
                                 f"rule: cite only works from {rules.oldest_allowed()} or later; remove the citation "
                                 "or replace it with a recent source", where))
        elif cls == "justify":
            prob = rules.justification_problem(key, table)
            if prob:
                errors.append(_issue("REF-UNJUSTIFIED", key, f"published {year} ({rules.RECENT_YEARS + 1}-"
                                     f"{rules.MAX_YEARS} years old): allowed only with a strict justification; "
                                     f"{prob}", where))
    total = sum(counts.values())
    if total and counts["recent"] / total < rules.TARGET_RECENT_SHARE:
        warnings.append(_issue("RECENCY", "-", f"only {counts['recent']}/{total} cited references are from "
                               f"{rules.recent_from()} or later (target: at least "
                               f"{rules.TARGET_RECENT_SHARE:.0%}); prefer recent sources"))
    return counts


def _online(report: dict, cites: dict, keyed: dict) -> None:
    from . import net
    ledger_all = load_ledger()
    ledger = ledger_all.get("entries", {})
    for key in sorted(cites):
        e = keyed.get(key)
        if not e or key not in ledger:
            continue
        f = e["fields"]
        doi = bib.norm_doi(f.get("doi"))
        arx = f.get("eprint")
        try:
            if doi and not doi.lower().startswith("10.48550/"):
                rec = net.resolve(doi)
            elif arx or doi:
                recs = net.arxiv_get([arx or doi.split("arXiv.", 1)[-1]])
                rec = recs[0] if recs else None
            else:
                continue
        except net.HTTPError as ex:
            report["warnings"].append(_issue("UNREACHABLE", key, f"could not re-resolve identifier: {ex}"))
            continue
        if not rec:
            report["errors"].append(_issue("NOT-FOUND", key, "identifier does not resolve", cites[key]))
            continue
        t1 = bib.latex_to_plain(f.get("title", "")).lower()
        t2 = (rec.get("title") or "").lower()
        sim = difflib.SequenceMatcher(None, t1, t2).ratio()
        if sim < 0.85:
            report["errors"].append(_issue("TITLE-MISMATCH", key, f"bib title vs registry title similarity {sim:.2f}: "
                                           f"'{t1[:70]}' vs '{t2[:70]}'", cites[key]))
        try:
            if f.get("year") and rec.get("year") and abs(int(re.sub(r'\D', '', f["year"])[:4]) - int(rec["year"])) > 1:
                report["warnings"].append(_issue("YEAR-MISMATCH", key, f"bib {f['year']} vs registry {rec['year']}"))
        except ValueError:
            pass
        fams = [bib.ascii_fold(x or "").lower() for x in (rec.get("author_families") or
                                                           [a.split()[-1] for a in rec.get("authors") or [] if a])]
        first = bib.ascii_fold(bib.latex_to_plain(f.get("author", "").split(" and ")[0].split(",")[0])).lower().strip()
        if fams and first and not any(first.split()[-1] in x for x in fams if x):
            report["warnings"].append(_issue("AUTHOR-MISMATCH", key, f"first author '{first}' not among registry authors"))
        if doi and not doi.lower().startswith("10.48550/"):
            try:
                if net.openalex_work(doi).get("is_retracted"):
                    report["errors"].append(_issue("RETRACTED", key, "OpenAlex marks this work as retracted", cites[key]))
            except net.HTTPError:
                pass
        ledger[key]["online_checked_at"] = core.now()
    save_ledger(ledger_all)


def claim_support(threshold: float = 0.12) -> list[dict]:
    """Heuristic triage: flag citing sentences with little lexical support in the cited abstract.

    This does NOT prove support. Flagged items must be judged by reading the source.
    """
    ledger = load_ledger().get("entries", {})
    out = []
    for p in tex.tex_files("paper"):
        r = core.rel(p)
        clean = tex.strip_comments(core.read_text(p) or "")
        for m in bib.CITE_RE.finditer(clean):
            line = clean.count("\n", 0, m.start()) + 1
            sent = sentence_around(clean, m.start(), m.end())
            sent_wo = bib.CITE_RE.sub(" ", sent)
            s_stems = content_stems(sent_wo)
            nums = re.findall(r"\d+(?:\.\d+)?\s*\\?%|\d+\.\d+", sent_wo)
            for key in [k.strip() for k in m.group(1).split(",") if k.strip()]:
                led = ledger.get(key) or {}
                src = (led.get("title") or "") + " " + (led.get("abstract") or "")
                item = {"file": r, "line": line, "key": key, "sentence": sent[:400], "title": led.get("title"),
                        "score": None, "flags": []}
                if not led.get("abstract"):
                    item["flags"].append("NO-ABSTRACT: cannot auto-assess; read the source")
                if len(s_stems) < 3:
                    item["flags"].append("SHORT-CONTEXT: citing sentence too short to assess")
                elif src.strip():
                    a_stems = content_stems(src)
                    item["score"] = round(len(s_stems & a_stems) / max(1, len(s_stems)), 3)
                    if item["score"] < threshold:
                        item["flags"].append(f"LOW-OVERLAP ({item['score']:.2f}): source abstract may not support this")
                for n in nums:
                    digits = re.sub(r"[^\d.]", "", n)
                    if digits and digits not in (led.get("abstract") or ""):
                        item["flags"].append(f"NUMBER '{n.strip()}' attributed to source but absent from its abstract")
                out.append(item)
    return out


def format_report(rep: dict, show_claims: bool = True) -> str:
    lines = [f"verify_bib: {rep['cited_keys']} cited keys, {rep['bib_entries']} bib entries, "
             f"{len(rep['errors'])} error(s), {len(rep['warnings'])} warning(s)"]
    rc = rep.get("recency") or {}
    if sum(rc.values()):
        lines.append(f"  reference age: {rc.get('recent', 0)} within 5 years, {rc.get('justify', 0)} 6-10 years "
                     f"(need justification), {rc.get('too-old', 0)} older than 10 years (not allowed)")
    for level in ("errors", "warnings", "info"):
        for it in rep[level]:
            where = f"  [{', '.join(it['where'][:3])}{' ...' if len(it['where']) > 3 else ''}]" if it["where"] else ""
            lines.append(f"  {level[:-1].upper():7} {it['code']:15} {it['key']}: {it['msg']}{where}")
    if show_claims and rep.get("claims"):
        flagged = [c for c in rep["claims"] if c["flags"]]
        lines.append(f"claim-support triage: {len(rep['claims'])} citation contexts, {len(flagged)} flagged for review")
        for c in flagged:
            lines.append(f"  FLAG {c['file']}:{c['line']} [{c['key']}] {'; '.join(c['flags'])}")
            lines.append(f"       \"{c['sentence'][:160]}\"")
    return "\n".join(lines)
