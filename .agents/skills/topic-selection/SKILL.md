---
name: topic-selection
description: Stage 2 (ends at GATE 1). Turn the gap analysis into 3-5 concrete research questions (or refine the human's topic), check novelty against the literature with targeted searches, rank by fit/novelty/feasibility, and stop for the human to pick or approve the topic. Use when `./ra state next` says RUN topic-selection, or when a `novelty` change marks it stale.
---

# Topic selection → Gate 1

```bash
./ra state start topic-selection
```
Read `project.json` (topic, constraints), `journal-profile.md`, `literature/topic-fit.md`,
`literature/gap-analysis.md`, the paper notes, `decisions.md` (a `(human)` topic choice or rejection
note is binding — e.g. after `REJECT gate1: ...`, address that note first).

## 1. Candidate questions → `literature/topics.md` (template `templates/topics.md`)
- **Human gave a topic:** sharpen it into 1–3 precise research questions (variants in scope/assumptions);
  do not replace it with your own idea. Add at most one alternative, clearly marked as an alternative.
- **No topic:** 3–5 questions, each from a gap in `gap-analysis.md`.
For each: precise question; expected contribution type (theorem, bound, characterisation, model +
analysis, counter-example); planned theory (key lemma to prove, proof strategy); planned simple
experiments (what the simulation tests, size, runtime < 1 h on a laptop); required tools; risks and the
fallback if the main result fails; fit to the journal (cite recent journal papers as evidence).

## 2. Novelty check → `literature/novelty-check.md` (template `templates/novelty-check.md`)
For every candidate, run **targeted** searches designed to find prior solutions (not just related work):
```bash
./ra lit search "<the exact claim in other words>" --source all --limit 25 --save novelty-<id>
./ra lit cites <closest paper> --limit 100 --save novelty-<id>-cites
```
plus WebSearch (including recent arXiv). For prior-art detection also search all years (`--any-year`): an
old result that already answers the question kills the candidate even though it could not be cited. Prefer
questions whose related work is recent (the paper may cite only the last 10 years, mostly the last 5).
Record queries, the closest prior results (keys; add notes with
`./ra lit note` if new), and a verdict: **novel / partially known (delta: ...) / known → drop**. Be
conservative: "we did not find it" is weaker than "it is new"; say which.

## 3. Rank and recommend
Score each candidate 1–5 on novelty, feasibility (theory + small experiments within the journal's
limits), fit, and significance; justify scores in one line each. Recommend one, but present all.

## 4. Gate 1
Write `gates/gate1_topic.md` (template `templates/gate1_topic.md`), then:
```bash
./ra state complete topic-selection
```
Tell the human: read `gates/gate1_topic.md` (and `literature/topics.md`) and reply e.g.
**`APPROVE gate1 T2`** or **`APPROVE gate1 T1 but only the discrete-time case`** or
**`REJECT gate1: <reason>`**. **Stop.**

## After approval (next run, before theory-experiment)
The approval note is recorded in `decisions.md` as a `(human)` entry. Copy the chosen question into
`project.json.topic` (if it changed) and add an agent decision entry summarising the final research
question, scope, and non-goals, referencing the human decision.
