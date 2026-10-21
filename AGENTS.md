# Research Paper Agent — Harness-Agnostic Workspace Entry Point

This folder is a **shared framework** for turning theory-heavy research papers (formal
proofs + small reproducible simulations) from journal intake to peer-reviewed submission.
Every paper lives in `papers/<name>/` with its own git repository, its own state, and its own bibliography.

**The authoritative operating manual is [`CLAUDE.md`](CLAUDE.md) in this folder. Read it in
full before doing anything in this workspace** — it defines the complete 11-stage pipeline,
the four human approval gates, scope-routing rules, and hard constraints.

---

## Agent Harness Parity: Universal Multi-Agent Support

This repository is designed to be **agent-agnostic and harness-agnostic**. Any assistant or model
can run this pipeline with identical capabilities, skills, rules, and guardrails:

| Harness | Configuration & Entry Point | Skills Directory | Reviewer Subagent | Guardrails / Hooks |
|---|---|---|---|---|
| **Claude Code** | `CLAUDE.md` | `.claude/skills/*/SKILL.md` | `.claude/agents/reviewer.md` | `.claude/settings.json` (`./ra hook ...`) |
| **OpenCode** | `opencode.json` + `AGENTS.md` | `.claude/skills/*/SKILL.md` | `.opencode/agents/reviewer.md` | `.opencode/plugins/ra-guard` |
| **Google Antigravity** | `AGENTS.md` + `GEMINI.md` | `.agents/skills/` & `skills.json` | `.agents/agents/reviewer.md` | `.agents/hooks.json` (`./ra agy-hook ...`) |
| **Cursor / Roo / Cline / Others** | `AGENTS.md` | `.claude/skills/` or `.agents/skills/` | `.claude/agents/` / `.agents/` | Static rules via `AGENTS.md` + CLI verification |

The underlying CLI engine (`./ra`) is completely tool-agnostic. Where instructions mention "hooks", all harnesses route through the same Python verification engine in `scripts/ra/`.

---

## Non-Negotiable Hard Rules (Never Violate)

1. **No formulas in the abstract** — words and plain concepts only; no math mode, symbols, Greek letters, variables, or big-O.
2. **References at most 10 years old**; $\ge 80\%$ from the last 5 years. Any 6–10-year-old reference strictly requires written justification in `literature/reference-justifications.md`.
3. **No AI-use statement or AI attribution** anywhere in the manuscript, cover letters, or git commit messages.
4. **No number without a results file** — all numerical values enter LaTeX text strictly through `\res...` macros backed by `results/manifest.json`.
5. **No citation without a verified DOI / arXiv id** — fetched solely with `./ra fetch-bib add <id>`.
6. **Strict paper isolation** — one conversation works on one paper; never read, search, reuse, or cite another paper's folder.
7. **Human ownership of gates** — only the human can approve or reject gates (`APPROVE` / `REJECT`); framework changes require explicit `MAINTENANCE ON`.

---

## Running the Pipeline

Loop autonomously across stages, stopping only when human input or gate approval is required:

```bash
./ra state next        # Determine next action: RUN <stage> | GATE | PLAN | WAIT | INTAKE | DONE
./ra state status      # View current paper progress and completed stages
./ra paper list        # List all papers (* = currently active paper)
./ra export            # Build Overleaf zip + PDF in exports/
./ra doctor            # Toolchain diagnostic check
```

- When `RUN <stage>`: run `./ra state start <stage>`, follow that stage's `SKILL.md`, then run `./ra state complete <stage>`.
- When `GATE`: summarize work, point to `gates/<gate>.md` and export files, then stop and wait for human approval.

---

## Execution Environment & Paths

- **WSL2 Runtime**: The Python virtual environment (`.venv`), toolchain, and `ra` launcher live in Linux/WSL2. Commands can be run directly in WSL or via `bash -c` / `cmd /c` on Windows.
- **Starting Directory**: Always run from the workspace root (`Research Agent/`), never inside `papers/<name>/`.
- **One Conversation = One Paper**: Stay focused on the active paper. If switching is needed, the human switches via chat or `/clear`.
