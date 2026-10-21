---
name: journal-format
description: Stage 7. Move the manuscript into the journal's official LaTeX template and reference style, add the required sections/files, enforce the journal's limits, and compile with latexmk in a fix-errors loop until the PDF builds cleanly. Use when `./ra state next` says RUN journal-format or a `template`/`journal` change marks it stale.
---

# Journal formatting

```bash
./ra state start journal-format
```
Read `journal-profile.md` (template, reference style, limits, required sections/files, AI policy),
`templates/SOURCES.md`, `style-guide.md`, `decisions.md`.

## 1. Apply the official template
```bash
./ra template install <name>      # copies .cls/.bst/.sty into paper/; example .tex stays in templates/<name>/
```
Read the template's example `.tex` and restructure `paper/main.tex` (Edit/Write tool) to follow it: document
class and options (review/preprint mode as the journal wants for submission), front matter (title, authors
with `[AUTHOR TO PROVIDE]` placeholders if unknown, abstract, keywords, highlights if in-document),
bibliography style (`\bibliographystyle{<journal bst>}` or biblatex style), theorem environments the class
provides. Keep `\input{generated/results.tex}` and all `\input{sections/...}`. Do not modify
`templates/` (hook-enforced). Keep `paper/references.bib` as the only bibliography file.
If the journal has no template, keep the generic article and apply the formatting rules from the guidelines.

## 2. Required sections, statements and files
From the profile: data/code availability (point to this repository's `experiments/` + `results/` only if the
human agreed — otherwise placeholder), competing interests, funding (`[AUTHOR TO PROVIDE]`), CRediT
statement (placeholder), highlights (`paper/highlights.tex` or `.txt` per journal), graphical abstract
(only if required — built by `./ra figs`, never AI-generated).

## 3. No AI signature (hard rule)
Write no AI-use / AI-assistance statement and no AI attribution anywhere (acknowledgements included). If the
journal's policy asks for one, only mention the policy to the author at Gate 2; the decision is theirs.

## 4. Compile loop (and Overleaf)
```bash
./ra compile --strict       # latexmk; undefined refs/cites count as failures here
```
Fix errors one at a time (read the reported file:line), re-run until clean. Then `./ra export`: it builds
`exports/<paper>-overleaf.zip` (the upload-ready Overleaf project) and compiles the PDF *from the zip*, which
proves the project is self-contained. Also fix: overfull boxes that
spill into margins, float placement problems, bad breaks in equations. `latexmk` must be installed — if it
is not, stop and tell the human (this stage cannot complete without a PDF).

## 5. Limits
```bash
./ra limits --report reviews/internal/format-report.md
```
If over a limit: shorten by tightening prose (not by removing evidence), move proofs/details to an
appendix or supplementary material if the journal allows, merge figures. Never change claims or numbers
to fit. Re-run until PASS, then append "Agent notes" (what was cut/moved) to the report.

## 6. Finish
```bash
./ra state complete journal-format   # paper/build/main.pdf, format report, strict compile, abstract rule,
                                     # no AI statement, and the Overleaf export (zip + PDF compiled from it)
```
