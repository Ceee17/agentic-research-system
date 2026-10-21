---
name: figures
description: Stage 4. Produce every figure from a saved, re-runnable source - matplotlib/seaborn scripts that read results/ for data plots, TikZ/Graphviz/Mermaid for diagrams - built with ./ra figs into figures/*.pdf with a manifest. No AI image generation. Use when `./ra state next` says RUN figures or a `figures` change marks it stale.
---

# Figures

```bash
./ra state start figures
```
Read `experiments/theory.md` (Results table), `results/manifest.json`, `journal-profile.md` (figure limits,
column width, colour/format rules), `style-guide.md`, `decisions.md`.

## Plan (add a "Figures" section to `experiments/theory.md`)
For each figure: the single message it conveys, which claim it supports, data source (run ids), type.
Respect the journal's figure limit; prefer 3–6 strong figures. Typical set for theory papers: a model /
setting diagram, theory vs simulation, parameter sweep / phase diagram, a robustness or failure-case plot.

## Data plots — `figures/scripts/<stem>.py` (template `templates/figure.py`)
- Contract: `python figures/scripts/<stem>.py --out figures/<stem>.pdf` (called by `./ra figs`).
- Read data **only** from `results/<run>/...` (write the path literally in the script so the manifest
  records the inputs). No numbers typed into plotting code except styling.
- Use `templates/paper.mplstyle` (vector PDF, readable fonts at column width, colour-blind-safe palette,
  no titles inside the figure — the caption carries the message). Show uncertainty (error bars/bands)
  and theory predictions as lines against simulation markers.

## Diagrams
- TikZ: `figures/tikz/<stem>.tex` as a `standalone` document (template `templates/diagram-tikz.tex`).
- Graphviz: `figures/diagrams/<stem>.dot`; Mermaid: `figures/diagrams/<stem>.mmd`.
- Never generate images with AI tools and never hand-draw/edit PDFs (hook-enforced: figure outputs can only
  be written by `./ra figs`).

## Build and check
```bash
./ra figs            # builds everything, records figures/manifest.json (sources + input hashes)
./ra figs --only <stem>
```
Look at every PDF (Read the file) and check: axis labels with units, legible fonts, legend not covering
data, consistent colours/notation with the paper, no clipped text. Draft a caption for each in
`experiments/theory.md` (drafting uses them).

## Finish
```bash
./ra state complete figures     # fails if a figure has no source, was modified, or its data changed
```
If results change later, `./ra figs` must be re-run (the integrity check detects stale inputs).
