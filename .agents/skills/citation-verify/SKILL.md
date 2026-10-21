---
name: citation-verify
description: Stage 6. Prove every citation is real and appropriate - all \cite keys resolve to entries fetched by DOI/arXiv (never from memory), identifiers re-resolve online with matching title/authors/year and no retractions, and every citing sentence is actually supported by the cited source. Produces reviews/internal/citation-report.md. Use when `./ra state next` says RUN citation-verify.
---

# Citation verification

```bash
./ra state start citation-verify
```

## 1. Integrity (automatic)
```bash
./ra verify-bib --online --claims --report reviews/internal/citation-check-auto.md
```
- Reference age (hard rule): REF-TOO-OLD (more than 10 years) must be removed or replaced by a recent
  source that presents the same result; REF-UNJUSTIFIED (6–10 years) needs a strict entry in
  `literature/reference-justifications.md` or a replacement. Review every justification critically and prefer
  replacing. Aim for at least 80% of citations from the last 5 years (RECENCY warning below that).
- Errors (MISSING, UNVERIFIED, TAMPERED, NO-ID, FOREIGN-BIB, TITLE-MISMATCH, NOT-FOUND, RETRACTED) must be
  zero. Fix by re-fetching (`./ra fetch-bib add --force <id>`), replacing the source, or removing the
  claim. A RETRACTED source is removed or discussed explicitly as retracted.
- Warnings (YEAR-/AUTHOR-MISMATCH, UNREACHABLE, DUPLICATE-DOI): investigate each; preprint vs published
  year differences are fine if the DOI is the published version.
- Never edit `paper/references.bib` or the ledger by hand (hook-enforced).

## 2. Claim support (judgment — the core of this stage)
The `--claims` triage flags citing sentences with low lexical overlap with the cited abstract, numbers
not found in the abstract, and sources without abstracts. For **every flagged item and every citation
of a specific result** (a theorem, a number, "X showed Y"):
1. open the paper note (`literature/papers/<key>.md`, "Citable statements"); if needed read the source
   itself (arXiv / open-access PDF via WebFetch) — abstracts are not enough for specific results;
2. verdict: **SUPPORTED** (location in source), **PARTIAL** (what is overstated), **NOT SUPPORTED**;
3. fix PARTIAL/NOT SUPPORTED: rephrase to what the source says, cite the right source, or drop the claim.
   Edits to wording in the paper are normal edits (hooks check them).
Also check: self-plagiarism-like reuse of abstract text (rephrase), citations clustered without purpose
("[1-7]"), missing obvious citations (closest prior work from `novelty-check.md` must be cited and
fairly described).

## 3. Report → `reviews/internal/citation-report.md` (template `templates/citation-report.md`)
Totals, integrity result, a table of every citation context with verdict and location in the source,
changes made, and anything the human should know (e.g. a key claim relies on a single preprint).

## 4. Finish
```bash
./ra verify-bib && ./ra state complete citation-verify
```
