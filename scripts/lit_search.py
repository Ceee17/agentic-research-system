"""./ra lit — literature helpers over Semantic Scholar, arXiv, OpenAlex and Crossref.

  search "query" [--source all|s2|arxiv|openalex|crossref] [--limit N] [--year 2019-|2019-2024 | --any-year]
                 [--save NAME] [--json]
                 Default window: the last 10 years (the citation limit). Results older than 10 years are
                 marked [NOT CITABLE]; 6-10-year-old ones [justify].
  get <id>...                      metadata for DOIs / arXiv ids / S2 ids
  refs <id> [--limit N]            works cited by <id>      (Semantic Scholar; for backward snowballing)
  cites <id> [--limit N]           works citing <id>        (Semantic Scholar; for forward snowballing)
  journal "<name|ISSN>" [--recent N] [--since YYYY-MM-DD] [--save]
                                   journal facts (OpenAlex/Crossref) + its recent papers (allowed during intake)
  note <id> [--key K]              fetch verified BibTeX, then create literature/papers/<key>.md from the template

--save writes literature/search/<date>-<name>.json and logs the query in literature/search-log.md
(the search log is a required output of the literature-review stage).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import bib, bibcheck, core, net, pipeline, refs, rules  # noqa: E402

NOTE_TEMPLATE = (".claude", "skills", "literature-review", "templates", "paper-note.md")


def _year_filter(recs: list[dict], spec: str | None) -> list[dict]:
    if not spec:
        return recs
    m = re.match(r"^(\d{4})?-?(\d{4})?$", spec.strip())
    if not m:
        return recs
    lo = int(m.group(1)) if m.group(1) else 0
    hi = int(m.group(2)) if m.group(2) else (lo if "-" not in spec else 9999)
    return [r for r in recs if r.get("year") and lo <= int(r["year"]) <= hi]


def _norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())[:80]


def merge(groups: dict[str, list[dict]]) -> list[dict]:
    merged: dict[str, dict] = {}
    for src, recs in groups.items():
        for r in recs:
            k = (r.get("doi") or "").lower() or (bib.strip_version(r.get("arxiv") or "")) or _norm_title(r.get("title"))
            if not k:
                continue
            if k in merged:
                m = merged[k]
                m["found_in"].append(src)
                for f, v in r.items():
                    if not m.get(f) and v:
                        m[f] = v
            else:
                merged[k] = dict(r, found_in=[src])
    return sorted(merged.values(), key=lambda r: (-len(r["found_in"]), -(r.get("citations") or 0)))


def do_search(query: str, source: str, limit: int, year: str | None) -> tuple[list[dict], list[str]]:
    fns = {"s2": lambda: net.s2_search(query, limit, year=year),
           "arxiv": lambda: net.arxiv_search(query, limit),
           "openalex": lambda: net.openalex_search(query, limit),
           "crossref": lambda: net.crossref_search(query, limit)}
    sources = list(fns) if source == "all" else [source]
    groups, warnings = {}, []
    for s in sources:
        try:
            groups[s] = _year_filter(fns[s](), year)
        except net.HTTPError as e:
            warnings.append(f"{s}: {e}")
    return merge(groups), warnings


def save(name: str, payload: dict, query_desc: str, n: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "search"
    rel = f"literature/search/{core.today()}-{slug}.json"
    core.write_json(core.path(rel), payload)
    log = core.path("literature", "search-log.md")
    if not log.exists():
        core.write_text(log, "# Search log\n\nEvery literature query, for reproducibility (auto-appended by `./ra lit`).\n\n"
                             "| date | source | query | results | saved |\n|---|---|---|---|---|\n")
    core.append_text(log, f"| {core.today()} | {payload.get('source', '-')} | {query_desc.replace('|', '/')} | {n} | "
                          f"`{rel}` |\n")
    return rel


def print_recs(recs: list[dict], as_json: bool) -> None:
    if as_json:
        print(json.dumps(recs, indent=2, ensure_ascii=False))
        return
    for i, r in enumerate(recs, 1):
        src = f" [{'/'.join(r['found_in'])}]" if r.get("found_in") else ""
        cls = rules.age_class(rules.parse_year(r.get("year")))
        mark = {"too-old": " [NOT CITABLE: >10y]", "justify": " [justify: 6-10y]"}.get(cls, "")
        print(f"{i:>3}. {net.fmt_record(r)}{src}{mark}")


def make_note(ident: str, key: str | None) -> int:
    try:
        key = refs.add(ident, key=key)
    except refs.FetchError as e:
        print(f"ERR {ident}: {e}", file=sys.stderr)
        return 1
    led = bibcheck.load_ledger()["entries"][key]
    note = core.path("literature", "papers", f"{key}.md")
    if note.exists():
        print(f"note exists: {core.rel(note)} (bib entry {key} is verified)")
        return 0
    tpl = core.read_text(core.wpath(*NOTE_TEMPLATE)) or "# {{title}}\n"
    vals = {"key": key, "title": led.get("title") or "", "authors": ", ".join(led.get("authors") or []),
            "year": str(led.get("year") or ""), "venue": led.get("venue") or "", "doi": led.get("doi") or "-",
            "arxiv": led.get("arxiv") or "-", "abstract": led.get("abstract") or "(no abstract available from APIs)",
            "fetched": led.get("fetched_at") or "", "source": led.get("source") or ""}
    for k, v in vals.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    core.write_text(note, tpl)
    print(f"created {core.rel(note)}  (bib key: {key}) - fill in the analysis sections from the actual paper")
    warn = rules.age_note(rules.parse_year(led.get("year")))
    if warn:
        print(f"WARNING: {warn}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra lit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--source", default="all",
                                                                         choices=["all", "s2", "arxiv", "openalex", "crossref"])
    s.add_argument("--limit", type=int, default=20); s.add_argument("--year"); s.add_argument("--save")
    s.add_argument("--any-year", action="store_true", help="search all years (older results are for background only)")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("get"); s.add_argument("ids", nargs="+"); s.add_argument("--json", action="store_true")
    for name in ("refs", "cites"):
        s = sub.add_parser(name); s.add_argument("id"); s.add_argument("--limit", type=int, default=50)
        s.add_argument("--save"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("journal"); s.add_argument("name"); s.add_argument("--recent", type=int, default=40)
    s.add_argument("--since"); s.add_argument("--save", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("note"); s.add_argument("id"); s.add_argument("--key")
    a = ap.parse_args()

    if a.cmd == "journal":
        if pipeline.intake_missing():
            print("refused: fill project.json journal fields first (intake)", file=sys.stderr)
            return 1
    elif not pipeline.intake_confirmed():
        print("refused: intake is not confirmed yet; literature work starts after `APPROVE intake`", file=sys.stderr)
        return 1

    try:
        if a.cmd == "search":
            if not a.year and not a.any_year:
                a.year = f"{rules.oldest_allowed()}-"
            recs, warns = do_search(a.query, a.source, a.limit, a.year)
            for w in warns:
                print(f"warning: {w}", file=sys.stderr)
            print_recs(recs, a.json)
            if a.save:
                rel = save(a.save, {"query": a.query, "source": a.source, "year": a.year, "date": core.now(),
                                    "results": recs}, f"{a.query}" + (f" (year {a.year})" if a.year else ""), len(recs))
                print(f"saved {rel}", file=sys.stderr)
            return 0
        if a.cmd == "get":
            recs = []
            for ident in a.ids:
                try:
                    recs.append(net.resolve(ident))
                except net.HTTPError as e:
                    print(f"ERR {ident}: {e}", file=sys.stderr)
            if a.json:
                print(json.dumps(recs, indent=2, ensure_ascii=False))
            else:
                for r in recs:
                    print(net.fmt_record(r, width=200))
                    if r.get("abstract"):
                        print(f"     abstract: {r['abstract'][:600]}{'...' if len(r['abstract']) > 600 else ''}")
            return 0
        if a.cmd in ("refs", "cites"):
            pid = a.id
            if bib.looks_like_doi(pid):
                pid = f"DOI:{bib.norm_doi(pid)}"
            elif bib.looks_like_arxiv(pid):
                pid = f"ARXIV:{bib.strip_version(bib.norm_arxiv(pid))}"
            recs = net.s2_links(pid, "references" if a.cmd == "refs" else "citations", a.limit)
            print_recs(recs, a.json)
            if a.save:
                rel = save(a.save, {"query": f"{a.cmd} of {a.id}", "source": "s2", "date": core.now(), "results": recs},
                           f"{a.cmd} of {a.id} (snowballing)", len(recs))
                print(f"saved {rel}", file=sys.stderr)
            return 0
        if a.cmd == "journal":
            srcs = net.openalex_sources(a.name)
            if not srcs:
                print(f"no journal found for '{a.name}' in OpenAlex", file=sys.stderr)
                return 1
            j = srcs[0]
            since = a.since or (dt.date.today() - dt.timedelta(days=730)).isoformat()
            recent = net.openalex_recent_in_source(j["openalex_id"], since, a.recent) if j.get("openalex_id") else []
            payload = {"journal": j, "alternatives": srcs[1:], "since": since, "recent": recent, "date": core.now()}
            if a.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(f"Journal: {j['name']} | publisher: {j['publisher']} | ISSN-L: {j['issn_l']} | OA: {j['is_oa']} "
                      f"| DOAJ: {j['is_in_doaj']} | APC USD: {j['apc_usd']} | works: {j['works_count']}")
                print(f"Homepage: {j['homepage']}\nTopics: {', '.join(j['topics'])}")
                if srcs[1:]:
                    print("Other matches: " + "; ".join(f"{s['name']} ({s['issn_l']})" for s in srcs[1:]))
                print(f"\nRecent papers since {since} ({len(recent)}):")
                print_recs(recent, False)
            if a.save:
                core.write_json(core.path("literature", "journal-scan.json"), payload)
                print("saved literature/journal-scan.json", file=sys.stderr)
            return 0
        if a.cmd == "note":
            return make_note(a.id, a.key)
    except net.HTTPError as e:
        print(f"ERR: {e}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
