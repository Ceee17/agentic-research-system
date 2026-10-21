---
name: intake
description: Stage 0 (mandatory, blocking). Collect the target journal from the human, research it into journal-profile.md, download the official LaTeX template, check topic fit (stage topic-fit-check), and stop at gate0 for the human's confirmation. Use whenever project.json is missing or incomplete, when intake/topic-fit-check is pending or stale, or when the human changes the target journal.
---

# Intake (stages `intake` + `topic-fit-check`, gate0)

The agent **never** chooses, guesses or suggests-and-assumes a journal. Until the human has given the
three required fields, the only thing you do is ask for them.

## 0. Check what is missing
```bash
./ra state check-intake
```
If anything is missing, ask the human in one message (below) listing exactly the missing fields, and stop.
Do nothing else — no literature search, no topic ideas, no files other than `project.json`.

Question to ask (adapt wording, keep all items):
> To start I need the target journal:
> 1. **Journal name** (required)
> 2. **Author-guidelines URL** or publisher page (required)
> 3. **Article type**: full paper, letter, short communication, or review (required)
> Optional: topic (if you have one), keywords/field, constraints (open access, indexing e.g. Scopus/WoS,
> deadline, max APC), author names + affiliations + ORCID for the title page.

## 1. Record the answers — `intake`
`./ra state start intake`, then write the answers into the active paper's `project.json`
(`papers/<active>/project.json`, Edit tool) exactly as given:
`journal.name`, `journal.guidelines_url`, `journal.article_type` (normalise to one of `full paper`,
`letter`, `short communication`, `review`; if the human used another term, keep theirs and note it),
`topic` (or `null`), `keywords`, `constraints`, `authors` (`[{name, affiliation, orcid, email, corresponding}]`
only if given). Never set `intake_confirmed` (a hook blocks it). Record the human's choices in
`decisions.md` as a `(human)` entry ("Target journal: ...").

## 2. Research the journal
Sources, in order: the guidelines URL (WebFetch), the publisher's LaTeX-template page, then
`./ra lit journal "<journal name or ISSN>" --save` (OpenAlex: publisher, ISSN, OA status, APC, topics and
recent papers) and WebSearch for anything still unknown. Quote nothing you did not read; mark unknowns
as `UNKNOWN (checked: <where>)` rather than guessing.

Write `journal-profile.md` from `.claude/skills/intake/templates/journal-profile.md` (remove the
`STATUS: NOT RESEARCHED` line). It must include:
- aims & scope (paraphrased, with source URL), article types and what the chosen type requires;
- official LaTeX template: name/class, download URL, reference style (numbered/author-year, `.bst`/biblatex style);
- limits: words, abstract words, pages, figures/tables, references, keywords, title length;
- required sections/files: highlights, graphical abstract, data/code availability, CRediT author
  statement, competing interests, funding, ethics, cover letter;
- **AI-use disclosure policy** (information for the author only): exact requirement and where a statement
  would go (quote ≤ 1 sentence, give the URL). By workspace rule the agent never writes an AI-use statement;
  the author decides;
- constraint check against `project.json.constraints` (OA, indexing, APC, deadline) — flag conflicts;
- the ```json block (keys exactly as in the template) — `./ra limits` reads it. Use `null` for unknown.

## 3. Download the template
```bash
./ra template fetch <direct .zip/.cls URL>     # or: ./ra template fetch ctan:<classname>
```
If only an HTML page exists, find the direct link; if the class is in TeX Live/CTAN (elsarticle, revtex4-2,
IEEEtran, svjour3, sn-jnl, amsart, llncs, ...), use `ctan:<name>`. If the journal has no LaTeX template,
say so in the profile ("generic article class; follow formatting rules in guidelines").
Then `./ra state complete intake`.

## 4. Topic fit — `topic-fit-check`
`./ra state start topic-fit-check`, then write `literature/topic-fit.md`
(template: `.claude/skills/intake/templates/topic-fit.md`):
- **Topic given:** compare it with the aims & scope and with the recent papers from `./ra lit journal`
  (`literature/journal-scan.json`): which recent papers are closest, is this kind of theory+simulation
  paper published there, fit rating strong / moderate / weak with reasons. **Warn clearly if weak** and
  suggest what would improve fit (never switch journal yourself).
- **No topic given:** summarise the recurring themes, methods and problem types in recent papers
  (these are the signal for later topic proposals); state that topics will be proposed at Gate 1.

## 5. Gate 0
Write `gates/gate0_intake.md` from `.claude/skills/intake/templates/gate0_intake.md` — one screen:
journal facts, template, key limits, AI policy, constraint conflicts, topic fit verdict, open questions,
and the reply to type. Then:
```bash
./ra state complete topic-fit-check
```
Tell the human to read `gates/gate0_intake.md` and type **`APPROVE intake`** (or `REJECT intake: <what's wrong>`).
**Stop.** The human's approval sets `intake_confirmed: true`; nothing else may start before that.

## Journal change later (scope `journal`)
apply-feedback runs `./ra state stale --scope journal` (resets confirmation). Re-run steps 1–5 for the new
journal, keep the old profile's facts in `decisions.md` only if relevant, and at Gate 0 list what changes
downstream (template, limits, framing).
