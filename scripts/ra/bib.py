"""Minimal, dependency-free BibTeX parsing/serialising plus citation extraction."""
from __future__ import annotations

import hashlib
import re
import unicodedata

from . import tex

SKIP_TYPES = {"comment", "preamble", "string"}
CITE_RE = re.compile(r"\\[A-Za-z]*cite[A-Za-z]*\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}")
BIBFILE_RE = re.compile(r"\\(?:bibliography|addbibresource)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
FIELD_ORDER = ["author", "title", "journal", "booktitle", "year", "volume", "number", "pages",
               "publisher", "doi", "eprint", "archiveprefix", "primaryclass", "url", "note"]
TITLE_STOPWORDS = {"a", "an", "the", "on", "of", "in", "for", "to", "and", "with", "towards", "toward",
                   "via", "from", "is", "are", "do", "does", "what", "how", "why", "when", "using", "at", "by"}


# ------------------------------------------------------------------- parsing
def _match_close(s: str, i: int, open_ch: str) -> int:
    """Index just past the delimiter closing the entry body that starts at s[i]."""
    close_ch = "}" if open_ch == "{" else ")"
    depth, j, n = 0, i, len(s)
    while j < n:
        c = s[j]
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0 and close_ch == "}":
                return j + 1
            depth -= 1
        elif c == close_ch and depth == 0:
            return j + 1
        j += 1
    return n


def _parse_fields(s: str) -> dict:
    fields, i, n = {}, 0, len(s)
    while i < n:
        while i < n and s[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        m = re.match(r"([A-Za-z0-9_\-:.+]+)\s*=\s*", s[i:])
        if not m:
            nxt = s.find(",", i)
            if nxt < 0:
                break
            i = nxt + 1
            continue
        name = m.group(1).lower()
        i += m.end()
        parts = []
        while i < n:
            if s[i] == "{":
                depth, j = 1, i + 1
                while j < n and depth:
                    if s[j] == "{":
                        depth += 1
                    elif s[j] == "}":
                        depth -= 1
                    j += 1
                parts.append(s[i + 1:j - 1])
                i = j
            elif s[i] == '"':
                depth, j = 0, i + 1
                while j < n and not (s[j] == '"' and depth == 0):
                    if s[j] == "{":
                        depth += 1
                    elif s[j] == "}":
                        depth -= 1
                    j += 1
                parts.append(s[i + 1:j])
                i = j + 1
            else:
                m2 = re.match(r"[A-Za-z0-9_\-:./]+", s[i:])
                if not m2:
                    break
                parts.append(m2.group(0))
                i += m2.end()
            while i < n and s[i] in " \t\r\n":
                i += 1
            if i < n and s[i] == "#":
                i += 1
                while i < n and s[i] in " \t\r\n":
                    i += 1
                continue
            break
        fields[name] = " ".join("".join(parts).split())
    return fields


def parse(text: str) -> list[dict]:
    """Parse BibTeX into [{type, key, fields, raw, start, end}] (skips @comment/@string/@preamble)."""
    entries, i = [], 0
    while True:
        at = text.find("@", i)
        if at < 0:
            break
        m = re.match(r"@\s*([A-Za-z]+)\s*([{(])", text[at:])
        if not m:
            i = at + 1
            continue
        etype = m.group(1).lower()
        body_start = at + m.end()
        end = _match_close(text, body_start, m.group(2))
        body = text[body_start:end - 1]
        i = end
        if etype in SKIP_TYPES:
            continue
        comma = body.find(",")
        key = (body if comma < 0 else body[:comma]).strip()
        fields = _parse_fields(body[comma + 1:]) if comma >= 0 else {}
        entries.append({"type": etype, "key": key, "fields": fields,
                        "raw": text[at:end], "start": at, "end": end})
    return entries


def by_key(entries: list[dict]) -> dict:
    out = {}
    for e in entries:
        out.setdefault(e["key"], e)
    return out


def fingerprint(entry: dict) -> str:
    """Formatting-insensitive hash of an entry's content (detects any hand edit)."""
    parts = [entry["type"].lower(), entry["key"]]
    for k in sorted(entry["fields"]):
        parts.append(f"{k}={' '.join(str(entry['fields'][k]).split())}")
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def format_entry(etype: str, key: str, fields: dict) -> str:
    keys = [k for k in FIELD_ORDER if k in fields] + sorted(k for k in fields if k not in FIELD_ORDER)
    lines = [f"@{etype}{{{key},"]
    for k in keys:
        v = str(fields[k]).strip()
        if v:
            lines.append(f"  {k} = {{{v}}},")
    lines.append("}")
    return "\n".join(lines)


# ------------------------------------------------------------------ identifiers
def norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = doi.strip()
    d = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", d, flags=re.I)
    d = re.sub(r"^doi:\s*", "", d, flags=re.I)
    return d.strip().rstrip(".") or None


def norm_arxiv(aid: str | None) -> str | None:
    if not aid:
        return None
    a = aid.strip()
    a = re.sub(r"^(https?://)?(www\.)?arxiv\.org/(abs|pdf)/", "", a, flags=re.I)
    a = re.sub(r"^arxiv:\s*", "", a, flags=re.I)
    a = re.sub(r"\.pdf$", "", a)
    return a or None


def strip_version(aid: str) -> str:
    return re.sub(r"v\d+$", "", aid)


def looks_like_arxiv(s: str) -> bool:
    s = norm_arxiv(s) or ""
    return bool(re.match(r"^(\d{4}\.\d{4,5}(v\d+)?|[a-z\-]+(\.[A-Z]{2})?/\d{7}(v\d+)?)$", s))


def looks_like_doi(s: str) -> bool:
    return bool(re.match(r"^10\.\d{4,9}/\S+$", norm_doi(s) or ""))


# ------------------------------------------------------------------- keys
def ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def make_key(family: str, year, title: str, existing: set[str]) -> str:
    fam = re.sub(r"[^a-z]", "", ascii_fold(family or "anon").lower()) or "anon"
    words = [w for w in re.findall(r"[a-z0-9]+", ascii_fold(title or "").lower()) if w not in TITLE_STOPWORDS]
    base = f"{fam}{year or 'nd'}{words[0] if words else ''}"
    key, n = base, 0
    while key in existing:
        n += 1
        key = base + "abcdefghijklmnopqrstuvwxyz"[(n - 1) % 26] * (1 + (n - 1) // 26)
    return key


# --------------------------------------------------------------- citations
def cites_in_tex(text: str) -> list[tuple[str, int]]:
    """[(key, line)] for every citation outside comments."""
    clean = tex.strip_comments(text)
    out = []
    for m in CITE_RE.finditer(clean):
        line = clean.count("\n", 0, m.start()) + 1
        for key in m.group(1).split(","):
            key = key.strip()
            if key:
                out.append((key, line))
    return out


def bib_files_in_tex(text: str) -> list[str]:
    clean = tex.strip_comments(text)
    files = []
    for m in BIBFILE_RE.finditer(clean):
        for f in m.group(1).split(","):
            f = f.strip()
            if f:
                files.append(f if f.endswith(".bib") else f + ".bib")
    return files


def latex_to_plain(s: str) -> str:
    """Rough LaTeX→text for titles/abstracts (for similarity checks only)."""
    s = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", s)
    s = s.replace("{", "").replace("}", "").replace("~", " ").replace("$", "")
    return " ".join(s.split())
