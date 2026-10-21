---
name: self-review
description: Stage 8 (ends at GATE 2). Delegate a harsh, fresh-context journal review to the `reviewer` subagent, fix clear small issues, route structural ones to the human, and stop at Gate 2 so the human reads the draft before submission. Use when `./ra state next` says RUN self-review.
---

# Self-review → Gate 2

```bash
./ra state start self-review
```

## 1. Independent review (round 1)
Invoke the `reviewer` subagent (Agent tool, `subagent_type: reviewer`) with a **neutral** prompt that does
not contain your own opinions or summaries, e.g.:
> Review the manuscript in paper/ for <journal> (<article type>) as a harsh referee, following your
> instructions. Save the report to reviews/internal/.

Do not tell it what you think is strong or weak. Wait for the report path.

## 2. Triage the report → `reviews/internal/response-to-internal-review-<n>.md`
For each issue: agree / partly / disagree (with evidence), scope (wording | claims | novelty | figures |
template | journal), and action.
- **Wording / clarity / small correctness fixes** (typos, undefined symbol, missing citation for an
  existing claim, caption fixes): apply now, following the drafting rules; hooks check every edit.
- **Anything structural** (weaken/strengthen a claim, new experiment, new figure, reframing novelty,
  changing the journal): do **not** do it now. List it for the human at Gate 2 with your recommendation.
- Issues that conflict with a `(human)` decision: never act; list them for the human.

## 3. Optional second round
If round 1 fixes were substantial, run the reviewer again, asking it to check whether the round-1 issues
(give the report path) were addressed. Maximum two rounds.

## 4. Gate 2
Make sure the paper compiles (`./ra compile --strict`) and limits pass (`./ra limits`). Write
`gates/gate2_draft.md` (template `templates/gate2_draft.md`): where the PDF is, the reviewer's
recommendation and scores, what you fixed, the open structural issues with recommendations, every
`[AUTHOR TO PROVIDE]` placeholder, the journal's AI-use policy as information for the author (the agent
writes no AI statement), the export paths (`exports/<paper>-overleaf.zip`, `exports/<paper>.pdf`) and the
submission checklist.
```bash
./ra state complete self-review
```
Tell the human to read `exports/<paper>.pdf` (or upload `exports/<paper>-overleaf.zip` to Overleaf) and
`gates/gate2_draft.md`, give feedback through any channel
(edit the .tex, `% @agent:` comments, feedback files), and when satisfied type **`APPROVE gate2`**.
**Stop.** After approval the human submits; revision starts when reviews arrive in
`reviews/external/round-1/`.
