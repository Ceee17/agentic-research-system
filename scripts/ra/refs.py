"""Fetch BibTeX from registries (doi.org / Crossref / arXiv / Semantic Scholar) into
paper/references.bib and record provenance in the ledger. Nothing is ever composed from
model memory: every field comes from an API response."""
from __future__ import annotations

import re

from . import bib, bibcheck, core, net

DROP_FIELDS = {"abstract", "file", "keywords", "mendeley-tags", "annote"}


class FetchError(Exception):
    pass


def _name_to_bibtex(full: str) -> str:
    parts = full.split()
    if len(parts) < 2 or "," in full:
        return full
    particles = {"van", "von", "de", "der", "den", "da", "di", "du", "del", "la", "le"}
    i = len(parts) - 1
    while i > 1 and parts[i - 1].lower() in particles:
        i -= 1
    return f"{' '.join(parts[i:])}, {' '.join(parts[:i])}"


def _write_entry(key: str, etype: str, fields: dict, replace: bool) -> None:
    p = core.path(*bibcheck.BIBFILE)
    text = core.read_text(p) or ""
    entry = bib.format_entry(etype, key, fields)
    existing = bib.by_key(bib.parse(text))
    if key in existing:
        if not replace:
            raise FetchError(f"key '{key}' already exists (use --force to re-fetch)")
        e = existing[key]
        text = text[:e["start"]] + entry + text[e["end"]:]
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + entry + "\n"
    core.write_text(p, text)


def _record(key: str, etype: str, fields: dict, meta: dict, source: str) -> None:
    ledger = bibcheck.load_ledger()
    ledger.setdefault("entries", {})[key] = {
        "doi": bib.norm_doi(fields.get("doi")), "arxiv": fields.get("eprint"), "source": source,
        "fetched_at": core.now(), "fingerprint": bib.fingerprint({"type": etype, "key": key, "fields": fields}),
        "title": meta.get("title") or bib.latex_to_plain(fields.get("title", "")),
        "authors": (meta.get("authors") or [])[:15], "year": meta.get("year") or fields.get("year"),
        "venue": meta.get("venue"), "abstract": (meta.get("abstract") or "")[:5000] or None,
    }
    bibcheck.save_ledger(ledger)


def _existing_by_id(doi: str | None = None, arxiv: str | None = None) -> str | None:
    for e in bibcheck.load_bib():
        f = e["fields"]
        if doi and (bib.norm_doi(f.get("doi")) or "").lower() == doi.lower():
            return e["key"]
        if arxiv and bib.strip_version(f.get("eprint") or "") == bib.strip_version(arxiv):
            return e["key"]
    return None


def add_doi(doi: str, key: str | None = None, force: bool = False, extra: dict | None = None,
            fallback_meta: dict | None = None) -> str:
    doi = bib.norm_doi(doi)
    if not bib.looks_like_doi(doi):
        raise FetchError(f"not a DOI: {doi}")
    old = _existing_by_id(doi=doi)
    if old and not force:
        return old
    try:
        meta = net.resolve(doi)
    except net.HTTPError as e:
        raise FetchError(f"DOI {doi} did not resolve: {e}") from e
    if fallback_meta and not meta.get("abstract"):
        meta["abstract"] = fallback_meta.get("abstract")
    source, etype, fields = None, None, None
    try:
        parsed = bib.parse(net.doi_bibtex(doi))
        if parsed:
            etype, fields, source = parsed[0]["type"], dict(parsed[0]["fields"]), "doi.org content negotiation (BibTeX)"
    except net.HTTPError:
        pass
    if not fields:
        if not meta.get("title"):
            raise FetchError(f"no BibTeX and no metadata for DOI {doi}")
        typ = (meta.get("type") or "").lower()
        etype = "article" if "journal" in typ or typ == "article" else ("inproceedings" if "proceedings" in typ or
                                                                          "paper-conference" in typ else "misc")
        fields = {"title": meta["title"], "author": " and ".join(_name_to_bibtex(a) for a in meta.get("authors") or []),
                  "year": str(meta.get("year") or ""), "journal" if etype == "article" else "howpublished":
                  meta.get("venue") or ""}
        source = "doi.org CSL-JSON metadata"
    fields = {k: v for k, v in fields.items() if k not in DROP_FIELDS}
    fields["doi"] = doi
    fields.update({k: v for k, v in (extra or {}).items() if v})
    keys = {e["key"] for e in bibcheck.load_bib()}
    if old:
        key = old
    elif not key:
        fams = meta.get("author_families") or [a.split()[-1] for a in meta.get("authors") or [] if a]
        key = bib.make_key(fams[0] if fams else "anon", meta.get("year") or fields.get("year"),
                           meta.get("title") or fields.get("title", ""), keys)
    _write_entry(key, etype, fields, replace=bool(old) or force)
    _record(key, etype, fields, meta, source)
    return key


def add_arxiv(aid: str, key: str | None = None, force: bool = False, prefer_arxiv: bool = False) -> str:
    aid = bib.norm_arxiv(aid)
    try:
        recs = net.arxiv_get([aid])
    except net.HTTPError as e:
        raise FetchError(f"arXiv lookup failed for {aid}: {e}") from e
    if not recs:
        raise FetchError(f"arXiv id not found: {aid}")
    rec = recs[0]
    base = bib.strip_version(rec["arxiv"])
    extra = {"eprint": base, "archiveprefix": "arXiv", "primaryclass": rec.get("primary_class")}
    if rec.get("doi") and not prefer_arxiv:
        return add_doi(rec["doi"], key=key, force=force, extra=extra, fallback_meta=rec)
    old = _existing_by_id(arxiv=base)
    if old and not force:
        return old
    fields = {"title": rec["title"], "author": " and ".join(_name_to_bibtex(a) for a in rec["authors"]),
              "year": str(rec.get("year") or ""), "publisher": "arXiv", "doi": f"10.48550/arXiv.{base}",
              "url": f"https://arxiv.org/abs/{base}", **{k: v for k, v in extra.items() if v}}
    keys = {e["key"] for e in bibcheck.load_bib()}
    key = old or key or bib.make_key(rec["authors"][0].split()[-1] if rec["authors"] else "anon", rec.get("year"),
                                     rec["title"], keys)
    _write_entry(key, "misc", fields, replace=bool(old) or force)
    _record(key, "misc", fields, rec, "arXiv API (export.arxiv.org)")
    return key


def add(identifier: str, key: str | None = None, force: bool = False, prefer_arxiv: bool = False) -> str:
    ident = identifier.strip()
    if re.match(r"^(s2|S2):", ident) or re.match(r"^[0-9a-f]{40}$", ident) or ident.lower().startswith("corpusid:"):
        try:
            rec = net.s2_paper(re.sub(r"^(s2|S2):", "", ident))
        except net.HTTPError as e:
            raise FetchError(f"Semantic Scholar lookup failed: {e}") from e
        if rec.get("doi"):
            return add_doi(rec["doi"], key, force, fallback_meta=rec,
                           extra={"eprint": rec.get("arxiv"), "archiveprefix": "arXiv" if rec.get("arxiv") else None})
        if rec.get("arxiv"):
            return add_arxiv(rec["arxiv"], key, force, prefer_arxiv)
        raise FetchError("Semantic Scholar record has neither DOI nor arXiv id; cannot cite it verifiably")
    if bib.looks_like_doi(ident) and not bib.norm_doi(ident).lower().startswith("10.48550/arxiv."):
        return add_doi(ident, key, force)
    if bib.norm_doi(ident) and bib.norm_doi(ident).lower().startswith("10.48550/arxiv."):
        return add_arxiv(bib.norm_doi(ident).split("arXiv.", 1)[-1].split("arxiv.", 1)[-1], key, force, prefer_arxiv)
    if bib.looks_like_arxiv(ident):
        return add_arxiv(ident, key, force, prefer_arxiv)
    raise FetchError(f"'{identifier}' is not a DOI, arXiv id or S2 id. Find the identifier with `./ra lit search`.")


def remove(key: str) -> bool:
    p = core.path(*bibcheck.BIBFILE)
    text = core.read_text(p) or ""
    e = bib.by_key(bib.parse(text)).get(key)
    if not e:
        return False
    core.write_text(p, (text[:e["start"]].rstrip("\n") + "\n\n" + text[e["end"]:].lstrip("\n")).strip("\n") + "\n")
    ledger = bibcheck.load_ledger()
    ledger.get("entries", {}).pop(key, None)
    bibcheck.save_ledger(ledger)
    return True
