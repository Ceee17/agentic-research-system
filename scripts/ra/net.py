"""HTTP helper and scholarly API clients (Semantic Scholar, arXiv, OpenAlex, Crossref, doi.org).

All clients return *normalised paper records*:
    {title, authors[], year, venue, doi, arxiv, s2_id, openalex_id, abstract, url,
     citations, source}
Environment:
    RA_CONTACT_EMAIL   polite-pool contact for Crossref/OpenAlex (optional)
    S2_API_KEY         Semantic Scholar API key (optional, raises rate limits)
    OPENALEX_API_KEY   OpenAlex API key (optional)
    RA_NO_CACHE=1      bypass the on-disk response cache (.ra/cache/http)
"""
from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import bib, core

UA = "research-paper-agent/0.1 (scholarly metadata client)"
CACHE_TTL = 7 * 86400
_last_call: dict[str, float] = {}
MIN_INTERVAL = {"export.arxiv.org": 3.0, "arxiv.org": 3.0, "api.semanticscholar.org": 1.1}


class HTTPError(Exception):
    def __init__(self, status, url, detail=""):
        super().__init__(f"HTTP {status} for {url}: {detail}")
        self.status, self.url, self.detail = status, url, detail


def _ua() -> str:
    email = os.environ.get("RA_CONTACT_EMAIL")
    return f"{UA} mailto:{email}" if email else UA


def _cache_file(key: str):
    return core.wpath(".ra", "cache", "http", core.short_hash(key, 20) + ".json")


def _throttle(url: str):
    host = urllib.parse.urlparse(url).netloc
    gap = MIN_INTERVAL.get(host)
    if gap:
        wait = _last_call.get(host, 0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.time()


def get(url: str, params: dict | None = None, accept: str | None = None, headers: dict | None = None,
        timeout: int = 30, retries: int = 4, cache: bool = True, binary: bool = False):
    """GET with retries/backoff on 429/5xx. Returns str (or bytes when binary=True)."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}, doseq=True)
    h = {"User-Agent": _ua()}
    if accept:
        h["Accept"] = accept
    h.update(headers or {})
    ckey = url + "|" + (accept or "")
    use_cache = cache and not binary and os.environ.get("RA_NO_CACHE") != "1"
    if use_cache:
        cached = core.read_json(_cache_file(ckey))
        if cached and time.time() - cached.get("t", 0) < CACHE_TTL:
            return cached["body"]
    last = None
    for attempt in range(retries + 1):
        _throttle(url)
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            if binary:
                return body
            text = body.decode("utf-8", errors="replace")
            if use_cache:
                core.write_json(_cache_file(ckey), {"t": time.time(), "url": url, "body": text})
            return text
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read()[:300].decode("utf-8", "replace")
            except Exception:
                pass
            last = HTTPError(e.code, url, detail)
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                ra = e.headers.get("Retry-After") if e.headers else None
                delay = float(ra) if ra and ra.isdigit() else 2.0 * (2 ** attempt)
                time.sleep(min(delay, 60))
                continue
            raise last
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = HTTPError(None, url, str(e))
            if attempt < retries:
                time.sleep(2.0 * (2 ** attempt))
                continue
            raise last
    raise last  # pragma: no cover


def get_json(url, params=None, **kw):
    return json.loads(get(url, params=params, accept="application/json", **kw))


def _record(**kw) -> dict:
    rec = {"title": None, "authors": [], "year": None, "venue": None, "doi": None, "arxiv": None,
           "s2_id": None, "openalex_id": None, "abstract": None, "url": None, "citations": None,
           "source": None}
    rec.update({k: v for k, v in kw.items() if v is not None})
    if rec["doi"]:
        rec["doi"] = bib.norm_doi(rec["doi"])
    return rec


def _clean(s):
    if not s:
        return None
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))  # strips JATS/HTML tags
    return " ".join(s.split()) or None


# ----------------------------------------------------------- Semantic Scholar
S2 = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "paperId,title,abstract,year,venue,authors,externalIds,citationCount,url,publicationDate,journal"


def _s2_headers():
    k = os.environ.get("S2_API_KEY")
    return {"x-api-key": k} if k else None


def _from_s2(p: dict) -> dict:
    ext = p.get("externalIds") or {}
    venue = p.get("venue") or ((p.get("journal") or {}).get("name"))
    return _record(title=_clean(p.get("title")), authors=[a.get("name") for a in p.get("authors") or [] if a.get("name")],
                   year=p.get("year"), venue=venue or None, doi=ext.get("DOI"), arxiv=ext.get("ArXiv"),
                   s2_id=p.get("paperId"), abstract=_clean(p.get("abstract")), url=p.get("url"),
                   citations=p.get("citationCount"), source="semantic_scholar")


def s2_search(query: str, limit: int = 20, year: str | None = None, fields_of_study: str | None = None) -> list[dict]:
    data = get_json(f"{S2}/paper/search", {"query": query, "limit": min(limit, 100), "fields": S2_FIELDS,
                                           "year": year, "fieldsOfStudy": fields_of_study}, headers=_s2_headers())
    return [_from_s2(p) for p in data.get("data") or []]


def s2_paper(pid: str) -> dict:
    """pid: S2 id, 'DOI:10.x/..', 'ARXIV:2101.00001', 'CorpusId:123'."""
    return _from_s2(get_json(f"{S2}/paper/{urllib.parse.quote(pid, safe=':/')}", {"fields": S2_FIELDS},
                             headers=_s2_headers()))


def s2_links(pid: str, direction: str = "references", limit: int = 50) -> list[dict]:
    key = "citedPaper" if direction == "references" else "citingPaper"
    data = get_json(f"{S2}/paper/{urllib.parse.quote(pid, safe=':/')}/{direction}",
                    {"fields": S2_FIELDS, "limit": min(limit, 1000)}, headers=_s2_headers())
    return [_from_s2(d[key]) for d in data.get("data") or [] if d.get(key) and d[key].get("title")]


# -------------------------------------------------------------------- arXiv
ARXIV = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _parse_arxiv(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for e in root.findall("a:entry", NS):
        eid = (e.findtext("a:id", default="", namespaces=NS) or "").strip()
        if "/abs/" not in eid:
            continue  # error entries
        aid = eid.split("/abs/", 1)[1]
        prim = e.find("arxiv:primary_category", NS)
        rec = _record(
            title=_clean(e.findtext("a:title", default="", namespaces=NS)),
            authors=[_clean(a.findtext("a:name", default="", namespaces=NS)) for a in e.findall("a:author", NS)],
            year=int((e.findtext("a:published", default="", namespaces=NS) or "0000")[:4]) or None,
            venue=_clean(e.findtext("arxiv:journal_ref", default="", namespaces=NS)) or "arXiv",
            doi=_clean(e.findtext("arxiv:doi", default="", namespaces=NS)),
            arxiv=aid, abstract=_clean(e.findtext("a:summary", default="", namespaces=NS)),
            url=f"https://arxiv.org/abs/{bib.strip_version(aid)}", source="arxiv")
        rec["primary_class"] = prim.get("term") if prim is not None else None
        out.append(rec)
    return out


ARXIV_ENDPOINTS = [ARXIV, "https://arxiv.org/api/query"]


def _arxiv_query(params: dict) -> str:
    """The export mirror sometimes answers 406/429/503; fall back to the main endpoint."""
    last = None
    for url in ARXIV_ENDPOINTS:
        try:
            return get(url, params, retries=1)
        except HTTPError as e:
            last = e
            if e.status not in (406, 429, 500, 502, 503, None):
                raise
    raise last


def arxiv_search(query: str, limit: int = 20, sort: str = "relevance") -> list[dict]:
    q = query if re.search(r"\b(ti|abs|au|cat|all):", query) else \
        " AND ".join(f"all:{w}" for w in query.split())
    return _parse_arxiv(_arxiv_query({"search_query": q, "start": 0, "max_results": limit, "sortBy": sort}))


def arxiv_get(ids: list[str]) -> list[dict]:
    ids = [bib.norm_arxiv(i) for i in ids]
    return _parse_arxiv(_arxiv_query({"id_list": ",".join(i for i in ids if i), "max_results": len(ids)}))


# ------------------------------------------------------------------ OpenAlex
OPENALEX = "https://api.openalex.org"


def _oa_params(extra: dict) -> dict:
    p = dict(extra)
    if os.environ.get("RA_CONTACT_EMAIL"):
        p["mailto"] = os.environ["RA_CONTACT_EMAIL"]
    if os.environ.get("OPENALEX_API_KEY"):
        p["api_key"] = os.environ["OPENALEX_API_KEY"]
    return p


def _oa_abstract(inv: dict | None) -> str | None:
    if not inv:
        return None
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos)) or None


def _from_openalex(w: dict) -> dict:
    arxiv = None
    for loc in w.get("locations") or []:
        u = (loc or {}).get("landing_page_url") or ""
        m = re.search(r"arxiv\.org/abs/([^\s?#]+)", u)
        if m:
            arxiv = m.group(1)
            break
    src = ((w.get("primary_location") or {}).get("source") or {})
    rec = _record(title=_clean(w.get("display_name") or w.get("title")),
                  authors=[(a.get("author") or {}).get("display_name") for a in w.get("authorships") or []
                           if (a.get("author") or {}).get("display_name")],
                  year=w.get("publication_year"), venue=src.get("display_name"), doi=w.get("doi"), arxiv=arxiv,
                  openalex_id=(w.get("id") or "").rsplit("/", 1)[-1] or None,
                  abstract=_oa_abstract(w.get("abstract_inverted_index")), url=w.get("doi") or w.get("id"),
                  citations=w.get("cited_by_count"), source="openalex")
    rec["is_retracted"] = w.get("is_retracted")
    rec["type"] = w.get("type")
    rec["publication_date"] = w.get("publication_date")
    return rec


def openalex_search(query: str, limit: int = 25, filters: str | None = None) -> list[dict]:
    data = get_json(f"{OPENALEX}/works", _oa_params({"search": query, "per-page": min(limit, 200), "filter": filters}))
    return [_from_openalex(w) for w in data.get("results") or []]


def openalex_work(doi: str) -> dict:
    return _from_openalex(get_json(f"{OPENALEX}/works/doi:{bib.norm_doi(doi)}", _oa_params({})))


def openalex_sources(name_or_issn: str, limit: int = 5) -> list[dict]:
    q = name_or_issn.strip()
    if re.match(r"^\d{4}-\d{3}[\dXx]$", q):
        data = {"results": [get_json(f"{OPENALEX}/sources/issn:{q}", _oa_params({}))]}
    else:
        data = get_json(f"{OPENALEX}/sources", _oa_params({"search": q, "per-page": limit}))
    out = []
    for s in data.get("results") or []:
        out.append({
            "openalex_id": (s.get("id") or "").rsplit("/", 1)[-1], "name": s.get("display_name"),
            "publisher": s.get("host_organization_name"), "issn_l": s.get("issn_l"), "issn": s.get("issn"),
            "type": s.get("type"), "works_count": s.get("works_count"), "is_oa": s.get("is_oa"),
            "is_in_doaj": s.get("is_in_doaj"), "apc_usd": s.get("apc_usd"), "homepage": s.get("homepage_url"),
            "topics": [t.get("display_name") for t in (s.get("topics") or [])[:10]],
        })
    return out


def openalex_recent_in_source(source_id: str, since: str, limit: int = 50) -> list[dict]:
    flt = f"primary_location.source.id:{source_id},from_publication_date:{since},type:article|review|letter"
    data = get_json(f"{OPENALEX}/works", _oa_params({"filter": flt, "sort": "publication_date:desc",
                                                     "per-page": min(limit, 200)}))
    return [_from_openalex(w) for w in data.get("results") or []]


# ------------------------------------------------------------------ Crossref
CROSSREF = "https://api.crossref.org"


def _from_crossref(m: dict) -> dict:
    issued = ((m.get("issued") or {}).get("date-parts") or [[None]])[0]
    authors = []
    for a in m.get("author") or []:
        name = " ".join(x for x in [a.get("given"), a.get("family")] if x) or a.get("name")
        if name:
            authors.append(name)
    rec = _record(title=_clean((m.get("title") or [None])[0]), authors=authors, year=issued[0] if issued else None,
                  venue=_clean((m.get("container-title") or [None])[0]), doi=m.get("DOI"),
                  abstract=_clean(m.get("abstract")), url=m.get("URL"), citations=m.get("is-referenced-by-count"),
                  source="crossref")
    rec["type"] = m.get("type")
    rec["author_families"] = [a.get("family") or a.get("name") for a in m.get("author") or []]
    return rec


def crossref_work(doi: str) -> dict:
    return _from_crossref(get_json(f"{CROSSREF}/works/{urllib.parse.quote(bib.norm_doi(doi), safe='/')}")["message"])


def crossref_search(query: str, limit: int = 20, filters: str | None = None) -> list[dict]:
    data = get_json(f"{CROSSREF}/works", {"query.bibliographic": query, "rows": min(limit, 100), "filter": filters})
    return [_from_crossref(m) for m in (data.get("message") or {}).get("items") or []]


def crossref_journal(issn: str) -> dict:
    return get_json(f"{CROSSREF}/journals/{issn}")["message"]


# ------------------------------------------------------------------- doi.org
def doi_bibtex(doi: str) -> str:
    """BibTeX for any registered DOI (Crossref or DataCite) via content negotiation."""
    d = urllib.parse.quote(bib.norm_doi(doi), safe="/")
    try:
        return get(f"https://doi.org/{d}", accept="application/x-bibtex; charset=utf-8").strip()
    except HTTPError:
        return get(f"{CROSSREF}/works/{d}/transform/application/x-bibtex").strip()


def doi_csl(doi: str) -> dict:
    """CSL-JSON metadata for any registered DOI (Crossref or DataCite)."""
    d = urllib.parse.quote(bib.norm_doi(doi), safe="/")
    return json.loads(get(f"https://doi.org/{d}", accept="application/vnd.citationstyles.csl+json"))


def csl_to_record(c: dict) -> dict:
    issued = ((c.get("issued") or {}).get("date-parts") or [[None]])[0]
    fams = [a.get("family") or a.get("literal") for a in c.get("author") or []]
    names = [" ".join(x for x in [a.get("given"), a.get("family")] if x) or a.get("literal") for a in c.get("author") or []]
    title = c.get("title")
    if isinstance(title, list):
        title = title[0] if title else None
    venue = c.get("container-title")
    if isinstance(venue, list):
        venue = venue[0] if venue else None
    rec = _record(title=_clean(title), authors=[n for n in names if n], year=issued[0] if issued else None,
                  venue=_clean(venue), doi=c.get("DOI"), abstract=_clean(c.get("abstract")), url=c.get("URL"),
                  source="doi.org")
    rec["author_families"] = [f for f in fams if f]
    rec["type"] = c.get("type")
    return rec


# --------------------------------------------------------------- resolution
def resolve(identifier: str) -> dict:
    """Best-effort metadata for a DOI, arXiv id, or S2 id (tries several services)."""
    ident = identifier.strip()
    if bib.looks_like_doi(ident):
        doi = bib.norm_doi(ident)
        try:
            rec = csl_to_record(doi_csl(doi))
        except HTTPError:
            rec = crossref_work(doi)
        if not rec.get("abstract"):
            try:
                s2 = s2_paper(f"DOI:{doi}")
                rec["abstract"] = s2.get("abstract")
                rec["arxiv"] = rec.get("arxiv") or s2.get("arxiv")
                rec["s2_id"] = s2.get("s2_id")
            except HTTPError:
                pass
        return rec
    if bib.looks_like_arxiv(ident):
        recs = arxiv_get([ident])
        if not recs:
            raise HTTPError(404, ident, "arXiv id not found")
        return recs[0]
    return s2_paper(ident)


def fmt_record(r: dict, width: int = 110) -> str:
    authors = r.get("authors") or []
    au = (authors[0] + (" et al." if len(authors) > 1 else "")) if authors else "?"
    ids = []
    if r.get("doi"):
        ids.append(f"doi:{r['doi']}")
    if r.get("arxiv"):
        ids.append(f"arXiv:{r['arxiv']}")
    if not ids and r.get("s2_id"):
        ids.append(f"s2:{r['s2_id']}")
    cites = f" | cites:{r['citations']}" if r.get("citations") is not None else ""
    title = (r.get("title") or "?")[:width]
    return f"{r.get('year') or '????'} | {title} | {au} | {r.get('venue') or '-'} | {' '.join(ids) or 'no-id'}{cites}"
