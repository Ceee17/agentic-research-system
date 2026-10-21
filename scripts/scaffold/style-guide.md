# Style guide

Read by the drafting, journal-format and revision skills before writing anything.
Lines or sections marked `(human)` are the human's rules: the agent may add rules but can never
change or remove a `(human)` entry (enforced by a hook). Rules learned from repeated human edits
are marked `(learned)` with the evidence count.

## Defaults (agent, may be refined)
- Voice: first-person plural ("we show"), active voice; present tense for what the paper does.
- One claim per sentence. Every claim ends in a citation (`\cite{}`) or points to a result
  (theorem/proposition, table, figure, or a `\res...` macro from `paper/generated/results.tex`).
- No numbers typed by hand in prose: use the generated `\res...` macros.
- Hedging matches evidence: "we prove" only for proofs, "we observe" for simulations,
  "suggests" for partial evidence. Never "clearly", "obviously", "novel" (let reviewers judge).
- Define every symbol at first use; keep notation consistent with `decisions.md`.
- Prefer short paragraphs (3–6 sentences) that open with their point.
- Figures and tables are referenced in the text before they appear; captions are self-contained.
- British/American spelling: follow the journal (see `journal-profile.md`).

## Workspace hard rules (enforced by hooks; listed here for convenience)
- Abstract: no formulas of any kind (no math, symbols, variables, operators, fractions). Say it in words.
- References: cite nothing older than 10 years; aim for >= 80% from the last 5 years; every 6–10-year-old
  reference needs a justification in `literature/reference-justifications.md`.
- No AI-use / AI-assistance statement or AI attribution anywhere in the paper or in commits.
- The manuscript must always export as an Overleaf project (`./ra export`).

## Human rules
<!-- Add rules as lines containing (human), e.g.:
- (human) Never use "utilize"; write "use".
-->

## Learned from human edits
<!-- Filled by the apply-feedback skill from `./ra edits patterns` (only patterns seen >= 2 times). -->
