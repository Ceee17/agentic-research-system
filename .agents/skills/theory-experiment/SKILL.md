---
name: theory-experiment
description: Stage 3. Develop the theory (definitions, assumptions, propositions, proofs) in experiments/theory.md, check every algebraic step with SymPy, and run small reproducible Python experiments with fixed seeds via ./ra run so every number lives in results/. Use when `./ra state next` says RUN theory-experiment or a `claims`/`novelty` change marks it stale.
---

# Theory and experiments

```bash
./ra state start theory-experiment
```
Read `decisions.md` (the approved topic and any `(human)` constraints), `literature/topics.md` (the chosen
T), `literature/novelty-check.md`, relevant paper notes, and — if re-running — the stale reason
(`./ra state show theory-experiment`) and the approved impact plan in `gates/`.

## Principles
- Theory first; experiments **test** the theory (predictions, boundary cases, where assumptions fail),
  they do not decorate it.
- Every step is either proved, checked symbolically, or explicitly labelled a conjecture supported by
  simulation. Never present a conjecture as a theorem.
- Small and reproducible: laptop runtime (minutes, < 1 h total), fixed seeds, no hidden state.
- **Every number** that will appear in the paper is written by a script into `results/` via `./ra run`.
  You cannot write `results/` by hand (hook-enforced).

## 1. `experiments/theory.md` (template `templates/theory.md`)
Setting & notation, assumptions (numbered A1..), definitions, main results (Proposition/Theorem with
status: `proved` | `proof sketch` | `checked symbolically` | `numerically supported conjecture`), full
proofs or proof sketches with gaps listed, and a claims table mapping each claim → evidence
(proof section / SymPy check id / results run id). Record notation choices in `decisions.md` (agent entry).

## 2. Symbolic checks — `experiments/derive_<name>.py` (template `templates/derivation.py`)
Use SymPy to verify algebra, derivatives, limits, series, fixed points, stability conditions, closed forms.
Each check writes an entry `{name, statement, verified: true/false, method}` to `derivation.json`, and
LaTeX of key expressions to `.tex` snippets (for `\input` in the paper). Run:
```bash
./ra run experiments/derive_<name>.py --seed 0
```
A failed check (`verified: false`) must be fixed or the claim downgraded — never dropped silently.

## 3. Experiments — `experiments/<name>.py` (template `templates/experiment.py`)
Contract: `--seed INT --out DIR`; seed all RNGs (`np.random.default_rng(seed)`); write `metrics.json`
(flat or nested numbers; add `"_format": {"key": ".3f"}` for display precision) and raw data (`.csv`)
into `--out`. Report uncertainty: multiple seeds (e.g. `--seed 0..9` as separate runs, or an internal
replicate loop with the seed as base) and mean ± std / CI.
```bash
./ra run experiments/<name>.py --id <name> --seed 0 [-- --n 1000]
./ra run --verify <name>            # re-run and compare: must be reproducible
./ra run --list
```

## 4. Expose numbers to the paper
```bash
./ra results-tex      # writes paper/generated/results.tex with \res<Id><Key> macros
```
Summarise findings in `experiments/theory.md` ("Results" section: run id → what it shows, with the macro
names). Negative or surprising results are reported, not hidden.

## 5. Finish
```bash
./ra state complete theory-experiment     # checks outputs + results integrity (no hand-made files)
```
If a `claims` change triggered this re-run, list in `experiments/theory.md` which claims changed so drafting
can update the text.
