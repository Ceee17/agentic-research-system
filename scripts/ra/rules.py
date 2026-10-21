"""Workspace hard rules (set by the human; enforced by hooks and `./ra state complete`).

1. NO FORMULAS IN THE ABSTRACT — no math mode, math macros, Greek/math symbols, operators,
   symbolic fractions, function notation or single-letter variables. Write it in words.
2. REFERENCE AGE — every cited reference is at most MAX_YEARS old; aim for most within
   RECENT_YEARS; a 5-10-year-old reference needs a written justification in
   literature/reference-justifications.md. No exceptions (the age check lives in bibcheck).
3. NO AI SIGNATURE — the agent writes no AI-use / AI-assistance statement in the paper and
   no AI attribution in commits (the author handles any disclosure the journal requires).
"""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from . import core, tex

RECENT_YEARS = 5
MAX_YEARS = 10
TARGET_RECENT_SHARE = 0.8
JUSTIFICATIONS = ("literature", "reference-justifications.md")
MIN_JUSTIFICATION_WORDS = 12


# =================================================================== reference age
def now_year() -> int:
    return _dt.date.today().year


def oldest_allowed() -> int:
    return now_year() - MAX_YEARS


def recent_from() -> int:
    return now_year() - RECENT_YEARS


def parse_year(value) -> int | None:
    m = re.search(r"(1[89]\d\d|20\d\d)", str(value or ""))
    return int(m.group(1)) if m else None


def age_class(year: int | None) -> str:
    """recent (<= 5 y) | justify (6-10 y) | too-old (> 10 y) | unknown."""
    if year is None:
        return "unknown"
    age = now_year() - year
    if age <= RECENT_YEARS:
        return "recent"
    if age <= MAX_YEARS:
        return "justify"
    return "too-old"


def age_note(year: int | None) -> str | None:
    cls = age_class(year)
    if cls == "too-old":
        return (f"{year} is more than {MAX_YEARS} years old: it may NOT be cited (hard rule). "
                "Use it only as background reading.")
    if cls == "justify":
        return (f"{year} is {RECENT_YEARS + 1}-{MAX_YEARS} years old: cite it only if essential, with a justification "
                f"in {'/'.join(JUSTIFICATIONS)}.")
    return None


def justifications() -> dict[str, dict]:
    """Parse `## <key>` sections with `- Essential because:` / `- No recent alternative because:`."""
    text = core.read_text(core.path(*JUSTIFICATIONS)) or ""
    out, key, fields = {}, None, {}
    for line in core.norm_newlines(text).split("\n") + ["## __end__"]:
        m = re.match(r"^##\s+([^\s(]+)", line)
        if m:
            if key:
                out[key] = fields
            key, fields = m.group(1), {}
            continue
        if key:
            m = re.match(r"^\s*[-*]\s*(essential because|no recent alternative because)\s*:\s*(.*)$", line, re.I)
            if m:
                fields["essential" if m.group(1).lower().startswith("essential") else "alternative"] = m.group(2).strip()
    out.pop("__end__", None)
    return out


def justification_problem(key: str, table: dict | None = None) -> str | None:
    j = (table if table is not None else justifications()).get(key)
    if not j:
        return f"no '## {key}' entry in {'/'.join(JUSTIFICATIONS)}"
    for field, label in (("essential", "Essential because"), ("alternative", "No recent alternative because")):
        if len(re.findall(r"\w+", j.get(field, ""))) < MIN_JUSTIFICATION_WORDS:
            return f"'{label}:' for {key} is missing or shorter than {MIN_JUSTIFICATION_WORDS} words"
    return None


# =================================================================== abstract formulas
MATH_ENVS = r"equation|align|alignat|gather|multline|eqnarray|math|displaymath|flalign|split|cases|array|" \
            r"[pbvBV]?matrix|subequations"
MATH_CMDS = set("""frac dfrac tfrac cfrac sqrt sum prod coprod int iint oint lim limsup liminf sup inf max min
log ln lg exp sin cos tan cot sec csc arcsin arccos arctan sinh cosh tanh arg det dim ker Pr mathrm mathbf mathit
mathcal mathbb mathsf mathfrak mathtt boldsymbol bm operatorname left right big Big bigg Bigg bigl bigr Bigl Bigr
cdot cdots ldotp times div pm mp le leq ge geq ll gg neq ne approx sim simeq equiv cong propto infty partial nabla
in notin ni subset subseteq supset supseteq cup cap setminus to rightarrow leftarrow Rightarrow Leftarrow
leftrightarrow Leftrightarrow mapsto implies iff forall exists nexists neg lnot land lor wedge vee oplus otimes
langle rangle lceil rceil lfloor rfloor lvert rvert lVert rVert mid vert Vert hat bar tilde vec dot ddot overline
widehat widetilde overrightarrow binom tbinom dbinom choose ast star circ prime emptyset varnothing ell hbar Re Im
deg top perp parallel angle triangle square Box approxeq lesssim gtrsim preceq succeq
alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa varkappa lambda mu nu xi pi varpi rho
varrho sigma varsigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi
Omega""".split())
TEXT_CMDS = set("""emph textit textbf textsc textrm textsf texttt textup textmd textnormal underline cite citet
citep citealt citealp citeauthor citeyear citeyearpar parencite textcite autocite nocite ref eqref cref Cref
autoref pageref label url href input include keywords noindent par newline linebreak ldots dots textellipsis
textendash textemdash textquoteleft textquoteright textquotedblleft textquotedblright S P copyright
textregistered texttrademark ss o O ae AE oe OE aa AA l L i j relax ignorespaces medskip smallskip bigskip
hspace vspace mbox hbox footnote thanks item textsuperscript textsubscript""".split())
ACCENTS = re.compile(r"\\[`'^\"~=.]\s*(\{[A-Za-z\\]*\}|[A-Za-z])|\\[uvHcdbtkr]\s*\{[A-Za-z\\]*\}")
ABBREV = re.compile(r"\b(i\.\s?e|e\.\s?g|cf|vs|et al|etc|approx|resp|viz)\.", re.I)
ENUM = re.compile(r"\((?:[ivx]{1,4}|[a-h])\)")
SLASH_OK = {"i/o", "a/b", "and/or", "w/o", "n/a", "tcp/ip", "input/output", "read/write", "client/server"}
UNICODE_MATH = re.compile("[\u0370-\u03ff\u1f00-\u1fff\u2190-\u21ff\u2200-\u22ff\u2a00-\u2aff\u27c0-\u27ef"
                          "\u27f0-\u27ff\u2980-\u29ff\u2070-\u209f\u00b1\u00b2\u00b3\u00b9\u00d7\u00f7\u2032\u2033"
                          "\u2102\u2115\u2119\u211a\u211d\u2124\u210f\U0001d400-\U0001d7ff]")


def _balanced(text: str, i: int) -> tuple[str, int]:
    """Content of the {...} group starting at text[i] == '{', and the index after it."""
    depth, j = 0, i
    while j < len(text):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    return text[i + 1:], len(text)


def _read(r: str, overrides: dict | None) -> str | None:
    if overrides and r in overrides:
        return overrides[r]
    return core.read_text(core.path(r))


def flatten(r: str, overrides: dict | None = None, depth: int = 0, seen: set | None = None) -> str:
    """Comment-free text of a paper .tex file with \\input/\\include expanded (paths as LaTeX resolves
    them from paper/)."""
    seen = seen if seen is not None else set()
    text = _read(r, overrides)
    if text is None or depth > 12 or r in seen:
        return ""
    seen.add(r)
    text = tex.strip_comments(core.norm_newlines(text))

    def repl(m):
        name = m.group(1).strip()
        target = "paper/" + (name if name.endswith(".tex") else name + ".tex")
        return flatten(target, overrides, depth + 1, seen)
    return re.sub(r"\\(?:input|include)\s*\{([^}]+)\}", repl, text)


def user_macros(text: str) -> dict[str, str]:
    """Argument-free macros defined with \\newcommand/\\renewcommand/\\providecommand/\\def."""
    out = {}
    for m in re.finditer(r"\\(?:re)?(?:new|provide)command\*?\s*\{?\\([A-Za-z]+)\}?\s*(\[\d\])?\s*\{", text):
        if m.group(2):
            continue
        body, _ = _balanced(text, m.end() - 1)
        out[m.group(1)] = body
    for m in re.finditer(r"\\def\\([A-Za-z]+)\s*\{", text):
        body, _ = _balanced(text, m.end() - 1)
        out.setdefault(m.group(1), body)
    for m in re.finditer(r"\\DeclareMathOperator\*?\s*\{\\([A-Za-z]+)\}", text):
        out[m.group(1)] = "\\operatorname{x}"
    return out


def abstract_text(overrides: dict | None = None) -> str | None:
    """The abstract as submitted (macros from results.tex and the preamble expanded), or None."""
    main = flatten("paper/main.tex", overrides)
    parts = []
    for m in re.finditer(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", main, re.S):
        parts.append(m.group(1))
    for m in re.finditer(r"\\abstract\s*\{", main):
        body, _ = _balanced(main, m.end() - 1)
        parts.append(body)
    if not parts:
        solo = flatten("paper/sections/abstract.tex", overrides)
        if not solo.strip():
            return None
        parts.append(solo)
    text = "\n".join(parts)
    macros = user_macros(flatten("paper/generated/results.tex", overrides) + "\n" + main)
    for _ in range(3):
        new = re.sub(r"\\([A-Za-z]+)(?![A-Za-z])", lambda mm: macros.get(mm.group(1), mm.group(0)), text)
        if new == text:
            break
        text = new
    return text


def formula_violations(text: str | None) -> list[str]:
    """Every formula-like element in an abstract (empty list = compliant)."""
    if not text:
        return []
    found: list[str] = []

    def add(kind, snippet):
        item = f"{kind}: {' '.join(str(snippet).split())[:60]}"
        if item not in found:
            found.append(item)

    t = text
    for m in re.finditer(r"\$[^$]*\$?|\\\(|\\\[|\\ensuremath", t):
        add("math mode", m.group(0))
    for m in re.finditer(r"\\begin\{(" + MATH_ENVS + r")\*?\}", t):
        add("math environment", m.group(0))
    for m in re.finditer(r"\\text(super|sub)script\s*\{([^}]*)\}", t):
        if m.group(1) == "sub" or m.group(2).strip().lower() not in ("st", "nd", "rd", "th"):
            add("super/subscript", m.group(0))
    for m in UNICODE_MATH.finditer(t):
        add("math/Greek symbol", m.group(0))
    t = ACCENTS.sub("x", t)
    t = re.sub(r"\{?\\(?:o|O|ae|AE|oe|OE|aa|AA|l|L|ss|i|j)\}?(?![A-Za-z])", "x", t)   # text letters like H{\o}yer
    t = re.sub(r"\\(?:[A-Za-z]*cite[A-Za-z]*|ref|eqref|cref|Cref|autoref|label|url|input|include)\*?"
               r"\s*(\[[^\]]*\]\s*)*\{[^}]*\}", " ", t)
    t = re.sub(r"\\href\s*\{[^}]*\}", " ", t)
    for m in re.finditer(r"\\([A-Za-z]+)", t):
        name = m.group(1)
        if name in MATH_CMDS:
            add("math command", "\\" + name)
        elif name not in TEXT_CMDS:
            add("unknown macro (may typeset math)", "\\" + name)
    t = re.sub(r"\\[A-Za-z]+\*?", " ", t)
    t = re.sub(r"\\[%&#_${}]", " ", t)          # escaped characters are text
    t = re.sub(r"\\[,;:! ]|\\\\", " ", t)
    t = ABBREV.sub(" ", t)
    t = ENUM.sub(" ", t)
    t = t.replace("~", " ").replace("{", "").replace("}", "")
    for m in re.finditer(r"[=<>^_|]", t):
        add("operator/symbol", t[max(0, m.start() - 12):m.end() + 12])
    for m in re.finditer(r"[\w)\]]\s*[+*]\s*[\w(\[]", t):
        add("arithmetic", m.group(0))
    for m in re.finditer(r"\b[A-Za-z]{1,6}/[A-Za-z0-9]{1,6}\b|\b\d+(?:\.\d+)?\s*/\s*[A-Za-z0-9]+\b", t):
        tok = m.group(0).replace(" ", "").lower()
        a, _, b = tok.partition("/")
        if tok in SLASH_OK or (len(a) > 2 and len(b) > 2 and a.isalpha() and b.isalpha()):
            continue
        add("symbolic fraction", m.group(0))
    for m in re.finditer(r"\b[A-Za-z]\(|\b(?:sqrt|log|ln|exp|sin|cos|tan|max|min|argmax|argmin|lim)\s*\(", t):
        add("function notation", t[m.start():m.end() + 10])
    for m in re.finditer(r"\b\d+(?:\.\d+)?[eE][-+]?\d+\b", t):
        add("scientific notation", m.group(0))
    for m in re.finditer(r"(?<![\w'\u2019\-+#./])([B-HJ-QS-Zb-z])(?![\w'\u2019\-+#])", t):
        add("single-letter variable", m.group(0))
    return found


def abstract_violations(overrides: dict | None = None) -> list[str]:
    return formula_violations(abstract_text(overrides))


# =================================================================== AI statements
AI_TERMS = (r"(?:claude(?: code)?|chatgpt|gpt-?\d(?:\.\d)?|gemini|copilot|large language models?|llms?|"
            r"generative ai|genai|ai[- ](?:tools?|assistants?|models?|agents?|chatbots?|systems?|technolog\w+)|"
            r"an ai\b|artificial intelligence(?: tools?)?)")
# Self-disclosure patterns: the MANUSCRIPT / its AUTHORS are the subject and AI is the instrument.
# (A paper *about* AI tools, e.g. "we used ChatGPT to generate tutoring dialogues", does not match.)
_OWN = r"(?:this|the|our) (?:work|manuscript|paper|article|text|study)(?: text)?"
AI_SELF = [re.compile(p) for p in (
    rf"\b{_OWN} (?:was|is|has been|were|have been) (?:\w+ ){{0,3}}(?:prepared|written|drafted|generated|produced|"
    rf"edited|created|developed|revised|polished|translated|proofread)\b[^.]{{0,80}}\b(?:with|using|by|through|via)\b"
    rf"[^.]{{0,60}}{AI_TERMS}",
    r"\b(?:this|the|our) (?:manuscript|paper|article)(?: text)? (?:is|was|has been) (?:\w+ ){0,2}(?:ai|machine|llm)"
    r"[- ]generated",
    rf"\b(?:the )?authors? (?:has |have )?(?:used|employed|utili[sz]ed|relied on|consulted)\b[^.]{{0,40}}{AI_TERMS}",
    rf"\b(?:we|i) (?:have )?(?:used|employed|utili[sz]ed)\b[^.]{{0,40}}{AI_TERMS}[^.]{{0,60}}\b(?:to|for)\b[^.]{{0,30}}"
    r"(?:writ|draft|edit|polish|proofread|prepar|improv)\w*[^.]{0,40}\b(?:manuscript|paper|article|text)\b",
    rf"\bwith (?:the )?(?:\w+ )?(?:assistance|help|support) (?:of|from) {AI_TERMS}[^.]*"
    r"|\b(?:assisted|aided|supported) by " + AI_TERMS,
    rf"{AI_TERMS}[^.]{{0,30}}\b(?:is|was|are|were) not (?:an? |listed as an? )?(?:co-?)?authors?\b",
)]
AI_OWN_CONTEXT = re.compile(r"\b(?:this|the|our) (?:work|manuscript|paper|article|text)\b|\bauthors?\b|\bwe\b")
AI_HEADING = re.compile(r"\\(?:section|subsection|subsubsection|paragraph|subparagraph)\*?\s*\{([^}]*)\}")
_SENT = re.compile(r"(?<=[.!?])\s+|\n\s*\n")


def ai_statement_hits(text: str | None) -> list[str]:
    """Headings/sentences that disclose or attribute AI assistance with the manuscript itself."""
    if not text:
        return []
    clean = tex.strip_comments(core.norm_newlines(text))
    hits = []
    for m in AI_HEADING.finditer(clean):
        head = m.group(1).lower()
        if re.search(AI_TERMS, head) and re.search(r"declaration|disclosure|statement", head):
            hits.append(m.group(0))
    for s in _SENT.split(re.sub(r"\\item\b", ". ", clean)):
        low = " ".join(s.lower().split())
        for i, rx in enumerate(AI_SELF):
            if rx.search(low) and (i != 4 or AI_OWN_CONTEXT.search(low)):
                hits.append(low)
                break
    return [" ".join(h.split())[:140] for h in hits]


def paper_tex_files() -> list[Path]:
    return tex.tex_files("paper", exclude=("paper/build/", "paper/export/", "paper/generated/"))


def ai_statement_violations() -> list[str]:
    out = []
    for p in paper_tex_files():
        for h in ai_statement_hits(core.read_text(p)):
            out.append(f"{core.rel(p)}: \"{h}\"")
    return out


# =================================================================== reporting
def format_abstract_report(v: list[str]) -> str:
    if not v:
        return "check-abstract: OK (no formulas in the abstract)"
    lines = [f"check-abstract: {len(v)} formula element(s) in the abstract (hard rule: no formulas, strictly):"]
    lines += [f"  - {x}" for x in v]
    lines.append("Fix: say it in words (e.g. 'scales with the square root of the number of items'), move symbols and "
                 "equations to the introduction/results, and use only plain-number results macros.")
    return "\n".join(lines)
