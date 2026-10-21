# Research Paper Agent — Antigravity & Gemini Workspace Instructions

This workspace turns theory-heavy research papers into submission-ready manuscripts using an autonomous 11-stage pipeline.

The authoritative operational guidelines and stage definitions live in:
- [`CLAUDE.md`](CLAUDE.md) — Complete operating manual, pipeline lifecycle, and hard constraints.
- [`AGENTS.md`](AGENTS.md) — Multi-harness architecture and shared rules.

---

## Antigravity Integration & Configuration

1. **Skills**:
   - Registered under `.agents/skills/` (mirrored from `.claude/skills/`) and declared in `.agents/skills.json`.
   - Each stage corresponds to an on-demand skill: `intake`, `literature-review`, `topic-selection`, `theory-experiment`, `figures`, `drafting`, `citation-verify`, `journal-format`, `self-review`, `revision`, and `apply-feedback`.

2. **Subagents**:
   - The independent referee persona for the `self-review` stage is defined at [`.agents/agents/reviewer.md`](.agents/agents/reviewer.md).

3. **Lifecycle Hooks & Guardrails**:
   - Configured in [`.agents/hooks.json`](.agents/hooks.json).
   - Antigravity's `PreToolUse` and `PostToolUse` events trigger `./ra agy-hook ...` to enforce paper isolation, protected file rules, abstract formula bans, reference recency checks, and LaTeX compilation tests.

---

## Workflow Quick Reference

Always operate on the active paper (`./ra paper current`):
```bash
bash ./ra state next            # Step 1: Check what to do next
bash ./ra state start <stage>   # Step 2: Begin the stage
# Step 3: Follow stage's SKILL.md under .agents/skills/<stage>/SKILL.md
bash ./ra state complete <stage># Step 4: Validate and finish stage
```

Stop at gates for human approval (`APPROVE <gate>`).
