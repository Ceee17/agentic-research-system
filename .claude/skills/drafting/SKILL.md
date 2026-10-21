---
name: drafting
description: Stage 5. Write the paper in LaTeX section by section (paper/main.tex + paper/sections/*.tex), always following style-guide.md, decisions.md and journal-profile.md; every claim tied to a verified citation or a results macro/theorem/figure. Use when `./ra state next` says RUN drafting or a wording/claims/novelty/figures change marks it stale.
---

# Drafting

```bash
./ra state start drafting
```
**Always read first:** `style-guide.md`, `decisions.md`, `journal-profile.md`, `experiments/theory.md`,
`paper/generated/results.tex`, `figures/manifest.json`, `literature/gap-analysis.md`, the paper notes you
will cite. On a re-run: `./ra state show drafting` (stale reason) and the approved `gates/impact-*.md`.

## Skeleton (first run only)
If `paper/main.tex` does not exist, create it from `templates/main.tex` (generic article; journal-format
converts it to the official template later). Write the paper plan as a "Paper plan" section in
`experiments/theory.md`: section list, one-sentence purpose each, word budget from the journal's limit,
which claims/figures go where. Sections (adapt to article type):
`abstract.tex`, `introduction.tex`, `related.tex` (or inside intro for letters), `model.tex`,
`results.tex` (theory), `experiments.tex`, `discussion.tex`, `conclusion.tex`, `appendix.tex` (proofs).

## Writing rules (hooks back several of these)
- **Claims:** each factual sentence ends with `\cite{key}` (a key from `paper/references.bib`, cited only
  for what its note's "Citable statements" support) or points to our evidence (`Theorem~\ref{}`,
  `Fig.~\ref{}`, `Table~\ref{}`, or a `\res...` macro). No claim without one of these.
- **Numbers:** never type a result; use `\resXxx` macros from `paper/generated/results.tex` (loaded in the
  preamble). `./ra check-numbers` must pass. Parameters also come from results/config files.
- **New citation needed?** Find it (`./ra lit search`), read it, `./ra lit note <DOI|arXiv>`, then cite.
  The post-edit hook runs verify_bib after every edit and reports unknown keys immediately.
- **Theorems:** statements match `experiments/theory.md` exactly, including status (a conjecture stays a
  conjecture); proofs or sketches in the appendix; assumptions referenced by label.
- **Human edits:** if a hook says a file has unregistered human edits, stop and run apply-feedback. Never
  rewrite text the human wrote unless asked; never touch `% LOCKED-START`…`% LOCKED-END`.
- **Abstract (hard rule):** no formulas of any kind: no `$...$`, symbols, Greek letters, variables,
  operators, fractions (N/M), big-O, or macros that typeset math. Describe results in words ("grows with the
  square root of the number of items"); plain-number `\res...` macros are fine. Hooks reject violations;
  `./ra check-abstract` shows them.
- **References (hard rule):** cite only works from the last 10 years, mostly the last 5; a 6–10-year-old
  source needs a justification in `literature/reference-justifications.md`. Attribute classic results through
  recent sources that present or extend them.
- **No AI signature (hard rule):** no AI-use / AI-assistance statement or AI attribution anywhere in the
  paper, cover page, biographies or acknowledgements.
- **Overleaf:** standard CTAN packages only, relative paths, no shell-escape; figures referenced through
  `\graphicspath{{../figures/}}` are copied into the export automatically.
- **Unknown facts** (authors, affiliations, funding, acknowledgements, data-availability URL):
  `\textbf{[AUTHOR TO PROVIDE: ...]}` — never invent.
- Follow `style-guide.md` voice and terminology; respect `(human)` decisions on framing and notation.

## Order and loop
Write in this order: model/setting → results (theory) → experiments → discussion → introduction →
related work → conclusion → abstract (last, ≤ journal limit, no overclaiming). After each section:
1. the post-edit hook compiles and verifies citations — fix anything it reports before moving on;
2. re-read the section against `style-guide.md` and the claims table in `experiments/theory.md`;
3. update the claims table "where in paper" column.

## Finish
```bash
./ra check-numbers && ./ra verify-bib && ./ra check-abstract && ./ra compile
./ra state complete drafting   # main.tex, >= 4 sections, bib (+ age), numbers, integrity, abstract, no AI
                               # statement, and a working Overleaf export (exports/<paper>-overleaf.zip + PDF)
```
