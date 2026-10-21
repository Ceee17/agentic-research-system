---
name: literature-review
description: Stage 1. Systematic literature search with Semantic Scholar, arXiv, OpenAlex and Crossref (via ./ra lit) plus web search; verified BibTeX for every paper kept; one structured note per paper in literature/papers/; a search log and a gap analysis. Use when `./ra state next` says RUN literature-review.
---

# Literature review

Goal: an honest map of what is known near the topic (or near the journal's themes if no topic was
given), good enough to (a) propose novel, feasible research questions and (b) write related work
without inventing anything.

## Before you start
```bash
./ra state start literature-review
```
Read `project.json`, `journal-profile.md`, `literature/topic-fit.md`, `decisions.md`.

## Citation-age rule (hard, no exceptions)
Only works from the last 10 years may be cited; aim for at least 80% from the last 5 years. `./ra lit search`
searches the last 10 years by default and marks older hits `[NOT CITABLE]` and 6–10-year-old ones `[justify]`.
You may read older classics for understanding (`--any-year`, snowballing), but never build the paper on a
source you cannot cite: find a recent paper that states, uses or extends the result, and cite that. Keep
6–10-year-old sources only when truly essential; each needs an entry in
`literature/reference-justifications.md` before it may be cited.

## 1. Plan the search (write it at the top of `literature/search-log.md`)
- 3–6 query families: core concept, synonyms, adjacent formalisms, application area, known key authors.
- Inclusion: theory/modelling or simulation work relevant to the question; peer-reviewed or well-cited
  preprints. Exclusion: off-topic, no identifier, not accessible.
- Target: 25–60 screened candidates, **≥ 15** papers with full notes (the stage requires 15).
- If no topic was given: seed queries from `literature/journal-scan.json` themes; cover 2–4 themes.

## 2. Search (every query is logged automatically with `--save`)
```bash
./ra lit search "<query>" --source all --limit 25 --save <short-name>          # last 10 years
./ra lit search "<query>" --year <5-years-ago>- --save <short-name>-recent        # prefer these
./ra lit refs  <DOI|arXiv> --limit 60 --save refs-<key>    # backward snowballing from key papers
./ra lit cites <DOI|arXiv> --limit 60 --save cites-<key>   # forward snowballing (who built on it)
./ra lit get   <DOI|arXiv> ...                             # abstract + metadata for screening
```
Use WebSearch for surveys, lecture notes and very recent work; only keep items with a DOI or arXiv id.
Screen by title+abstract; record kept/dropped counts per query in the search log (a line per query is
added automatically; add the screening counts and reasons by hand).

## 3. Keep a paper = verified bib entry + note
```bash
./ra lit note <DOI|arXiv>        # fetches verified BibTeX, creates literature/papers/<key>.md
```
Then fill the note (template `templates/paper-note.md`) **from what you actually read**: the abstract at
minimum; mark notes of sources older than 10 years `relevance: background (not citable)`. Read the full
text (arXiv PDF / open-access version via WebFetch) for the 5–10 most relevant
papers. Mark each note `read-depth: abstract | full-text`. Every claim in the note must be something the
paper says; key equations/assumptions in your own notation; results with their conditions. If you
could not access the text, say so. Never paraphrase from memory.

## 4. Synthesis
Write `literature/gap-analysis.md` (template `templates/gap-analysis.md`):
- taxonomy of approaches (table: paper key → setting, assumptions, method, main result, limitation);
- what is established (with keys), what is contested, what is open;
- **gaps**: 4–8 concrete gaps, each with evidence (keys + note sections) and why it matters to this
  journal's readers; flag gaps that a theory + small-simulation paper can realistically close;
- threats: very recent/concurrent work that might pre-empt a gap.

## 5. Finish
```bash
./ra verify-bib            # every kept paper is verified (entries are only added by ./ra lit note / fetch-bib)
./ra state complete literature-review
```
Required outputs: ≥ 15 `literature/papers/*.md`, `literature/gap-analysis.md`, `literature/search-log.md`,
`paper/references.bib` + ledger. Commit happens automatically. Then continue with topic-selection
(no gate here).
