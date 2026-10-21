---
name: ra-init
description: One-line start of a NEW research paper in this workspace. Creates papers/<name>/ (own git repository), checks the toolchain, takes any journal/topic details given on the same line, then runs the whole pipeline autonomously (intake → literature → topic → theory → figures → drafting → citations → formatting → self-review), stopping only at the human gates. Usage: /ra-init [name] [journal, guidelines URL, article type, topic, ... all optional]
argument-hint: "[paper-name] [journal | guidelines URL | article type | topic | constraints]"
disable-model-invocation: true
---

# /ra-init — start a new paper with one line

Text the human typed after `/ra-init` (may be empty): **$ARGUMENTS**
(If the line above shows a literal `$ARGUMENTS`, use the arguments of the human's `/ra-init` message.)

Examples of what the human may type:
- `/ra-init`
- `/ra-init ai-tutors`
- `/ra-init APJITM https://www.ukm.my/apjitm/guidelines full paper, topic: LLM tutors for programming courses`

## 1. Create the paper — FIRST action, before reading or running anything else
A conversation that has already worked on another paper may not create a new one (papers must never mix),
so do this before touching anything paper-related.

1. Choose the name:
   - the first argument, if it is already a valid name (lowercase letters, digits, hyphens; not a URL);
   - else 2–4 meaningful words of the topic, lowercase, joined by hyphens (e.g. `llm-programming-tutors`);
   - else `paper-<n>`, with `<n>` one more than the number of papers listed by `./ra paper list`.
2. Run exactly this command, alone (the guard accepts only this form):
   ```bash
   ./ra paper new <name>
   ```
   - "already exists" → use `<name>-2` (then `-3`, ...) and run it again.
   - refused because this conversation already worked on another paper → tell the human, in one line:
     "Type /clear, then send the same /ra-init line again." and stop.
3. From now on every file you touch is under `papers/<name>/`. Never read another paper's folder.

## 2. Bootstrap check (quick, non-blocking)
```bash
./ra doctor
```
Summarise problems in at most three bullets: missing Python packages → `bash scripts/setup.sh` (do not install
anything without asking); no TeX → PDFs come from Overleaf, the zip is still produced; no latexdiff → only
needed for revision rounds (TinyTeX: run its `tlmgr install latexdiff`). Stop only if git is missing (every paper
needs its own repository).

## 3. Intake from the line the human typed
Read the arguments for: journal name, author-guidelines URL, article type (full paper / letter / short
communication / review), topic, keywords, constraints (open access, indexing, deadline, maximum APC), author
names and affiliations. Write exactly what was given into `papers/<name>/project.json` (Edit tool); never guess
or choose a journal, and never fill a field the human did not give.

If journal name, guidelines URL or article type is still missing, ask for them in ONE short message (list only
the missing required fields, then the optional ones) and stop. When the human answers, fill them in and go on.

## 4. Run the pipeline
Follow `CLAUDE.md` → "How you run": loop `./ra state next`, run apply-feedback before every stage, run each stage
skill end to end, and continue without asking between stages. Stop only at a gate, an impact plan, a genuine
blocker, or missing human input. The first stop is Gate 0 (journal profile + topic fit): tell the human to read
`papers/<name>/gates/gate0_intake.md` and reply `APPROVE intake` (then "continue").

At every stop, end with the exact line the human should type (e.g. `APPROVE gate1 T2`), and where to read the
draft once it exists: `papers/<name>/exports/<name>.pdf` and `papers/<name>/exports/<name>-overleaf.zip`.
