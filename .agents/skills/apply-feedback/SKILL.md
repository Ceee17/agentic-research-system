---
name: apply-feedback
description: Runs before EVERY stage. Collects human input from the four channels (direct edits to paper/*.tex, `% @agent:` comments, feedback/*.md files, LOCKED regions), classifies each item by scope, applies small wording items directly, turns structural items into an impact plan that marks affected stages stale and waits for human approval, records lasting preferences/decisions, archives processed items and commits.
---

# Apply feedback (before every stage)

## 1. Collect
```bash
./ra feedback collect --diff
./ra edits patterns
```
If nothing is pending and no approved impact plan awaits execution, say so in one line and return to the
stage. Also read new `(human)` entries in `decisions.md` and `style-guide.md` (humans may edit these directly).

## 2. Register direct human edits first (channel 1)
Read every diff. The human's text is now authoritative — **never revert or overwrite it**. Then:
```bash
./ra edits accept --note "<one-line summary>"
```
(until you do, hooks block your edits to those files). Classify what the edit implies: pure wording →
nothing else to do except learn from it; a changed claim, number, theorem, citation or figure reference →
a structural item (below), because theory/results/other sections may now be inconsistent. A human-typed
number that is not in results/ is a structural `claims` item — ask, never "fix" it silently.

## 3. Classify every item by scope
| scope | examples | stages made stale |
|---|---|---|
| wording | rephrase, shorten, tone, typos, reorder sentences | drafting |
| claims | weaken/strengthen a claim, new assumption, change a result | theory-experiment, drafting |
| novelty | reframe contribution, different research question | topic-selection, theory-experiment, drafting |
| figures | new/changed figure, different plot | figures, drafting |
| template | formatting, class options, section order required by journal | journal-format |
| journal | change of target journal or article type | intake, topic-fit-check, journal-format |
Feedback files declare `scope:`; `% @agent[claims]:` tags are hints; untagged comments default to wording
unless the request clearly changes content. When unsure, treat as structural.

## 4. Small items (wording) — apply directly
Edit the text (respecting LOCKED regions and `keep:`), then log and commit per item:
```bash
./ra comments resolve <c:id> --note "what you changed"          # @agent comments
./ra feedback done <file>.md --resolution "what you changed"     # feedback files
./ra feedback log --item <id> --summary "..." --scope wording     # anything else
```
Wording changes to an already-finished draft do not require re-running drafting as a whole; if the whole
draft needs rewording, `./ra state stale --scope wording --reason "..."`.

## 5. Structural items — plan, mark stale, STOP
```bash
./ra feedback plan --scope claims[,figures] --items fb:x.md,c:1a2b3c4d,e:paper/sections/results.tex --title "..."
```
Fill `gates/impact-Pnnn.md`: what will change in each stale stage, what stays (`keep:`), risks, effort, open
questions. Then tell the human to read it and type **`APPROVE Pnnn`** or **`REJECT Pnnn: why`**, and **stop**
— do not rewrite anything before approval. Structural `@agent` comments stay in the file until the plan is
executed; resolve them (`./ra comments resolve`) when the change is done.
After approval, `./ra state next` routes to the first stale stage; each re-run stage reads the plan.
When the plan's stages are done it is marked executed; then archive its feedback files (`./ra feedback done`).

## 6. Record lasting knowledge
- Preferences → `style-guide.md` under "Learned from human edits" as `(learned, seen Nx)` lines — only
  patterns from `./ra edits patterns` seen ≥ 2 times, or explicit style requests. Do not add `(human)` to
  your own lines; only transcribe the human's explicit rules as `(human)` when they state them in feedback.
- Decisions (scope, framing, notation, what not to do) → `decisions.md`: the human's explicit decisions as
  `## D-NNN (human) date — title`, your own as `(agent)`. Existing `(human)` entries are immutable.

## Hard rules win
If a human edit or request would put a formula in the abstract, a reference older than 10 years, or an AI-use
statement into the paper, register it, then fix it to comply and say so at the next stop (the hard rules are
the human's standing instructions and are not overridden by later edits).

## 7. Done
`./ra feedback collect` shows nothing pending (or only items inside an awaiting plan). Continue with the stage.
