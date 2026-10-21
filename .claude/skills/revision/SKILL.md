---
name: revision
description: Stage 9 (ends at GATE 3). Respond to REAL reviewer comments placed by the human in reviews/external/round-N/ - split them into atomic points, make point-by-point changes (routing structural ones through the scope system), write a response letter, and produce a latexdiff tracked-changes PDF. Use when `./ra state next` says RUN revision.
---

# Revision → Gate 3

Only real reviewer/editor comments count. Never invent, paraphrase away, or omit a reviewer point.
Files in `reviews/external/` are read-only (hook-enforced).

```bash
./ra state start revision
./ra state status          # shows the round being processed
```

## 1. Parse comments → `reviews/response/round-N/points.md`
Read every file in `reviews/external/round-N/` (use the pdf skill / Read for PDFs). Split into atomic
points `R1.1, R1.2, …, R2.1, …, E.1` (editor). Quote each point **verbatim**. For each: type (error,
missing analysis, clarity, citation request, scope/novelty challenge, typo), scope (wording | claims |
novelty | figures | template | journal), and planned action.

## 2. Plan and route
- Wording/clarity/typos/citation additions: do them in this stage.
- **claims / figures / new experiment / new theory**: these re-open earlier stages. Write an impact plan
  (`./ra feedback plan --scope <scope> --items R1.3,R2.1 --title "..."`), which marks stages stale and waits
  for the human's `APPROVE Pnnn`; then those stages re-run (theory-experiment → figures → drafting ...)
  before revision continues. Record the link in `points.md`.
- **Disagreeing with a reviewer** is allowed only with evidence (proof, result, citation) and a polite,
  specific rebuttal; flag every disagreement at Gate 3.
- `(human)` decisions: if a reviewer asks to change one, propose options at Gate 3; do not act.
- New citations requested by reviewers: verify them like any other (`./ra lit note`), and check the
  suggested work is real and relevant before citing.

## 3. Edit the paper
Normal drafting rules (numbers via macros, citations verified, human edits and locks respected). Keep a
change list per point (section, what changed). Workspace rules may be stricter than when the paper was
submitted: run `./ra check-abstract` and `./ra verify-bib` and fix every violation (formulas in the abstract,
references older than 10 years, unjustified 6–10-year-old ones, any AI-use statement) as part of this round,
and list those changes in the gate file. No AI signature in the response letter either.

## 4. Response letter → `reviews/response/round-N/response-letter.tex`
From `templates/response-letter.tex`: thank briefly, then for every point: verbatim quote, response, what
changed and where (section/page/line in the revised PDF), with quoted new text where helpful. No
sycophancy, no promises not kept in the manuscript.

## 5. Tracked changes
```bash
BASE=$(./ra state commit-of self-review)       # the submitted version (or a tag the human made)
./ra diff --base "$BASE" --round N             # -> reviews/response/round-N/diff.pdf
./ra compile --strict && ./ra limits && ./ra export   # Overleaf zip incl. response letter + PDFs
```

## 6. Gate 3
Write `gates/gate3_response.md` (template `templates/gate3_response.md`), then
```bash
./ra state complete revision
```
Tell the human to read the response letter, `diff.pdf` and the gate file; reply **`APPROVE gate3`** or
**`REJECT gate3: <what to change>`**. **Stop.** Further rounds: the human adds `reviews/external/round-<N+1>/`.
