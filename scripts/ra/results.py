"""results/ manifest integrity and the pool of traceable numbers."""
from __future__ import annotations

import json
import re

from . import core

MANIFEST = ("results", "manifest.json")
NUM_TOKEN = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
TEXT_EXT = {".json", ".csv", ".tsv", ".txt", ".md", ".tex", ".dat", ".log", ".yaml", ".yml"}


def manifest() -> dict:
    return core.read_json(core.path(*MANIFEST), {"runs": {}}) or {"runs": {}}


def integrity_problems() -> list[str]:
    """Every file under results/ must come from a recorded run and be unmodified."""
    rdir = core.path("results")
    runs = manifest().get("runs", {})
    problems, recorded = [], set()
    for rid, run in runs.items():
        if run.get("returncode") not in (0, None):
            problems.append(f"results/{rid}: run failed (returncode {run.get('returncode')}); rerun it")
        for relf, digest in (run.get("outputs") or {}).items():
            recorded.add(relf)
            p = core.path(relf)
            if not p.exists():
                problems.append(f"{relf}: listed in manifest but missing")
            elif core.sha256_file(p) != digest:
                problems.append(f"{relf}: modified after the run that produced it (hash mismatch)")
    if rdir.exists():
        for p in rdir.rglob("*"):
            r = core.rel(p)
            if p.is_file() and r not in recorded and not r.startswith("results/_archive/") \
                    and r not in ("results/manifest.json", "results/.gitkeep", "results/INDEX.md"):
                problems.append(f"{r}: not produced by a recorded `./ra run` (no manifest entry)")
    return problems


FIG_MANIFEST = ("figures", "manifest.json")
FIG_EXT = {".pdf", ".png", ".svg", ".eps", ".jpg", ".jpeg"}


def figures_integrity() -> list[str]:
    """Every figure must be built by `./ra figs` from a saved source, from current results."""
    man = (core.read_json(core.path(*FIG_MANIFEST), {}) or {}).get("figures", {})
    problems = []
    fdir = core.path("figures")
    if fdir.exists():
        for p in sorted(fdir.iterdir()):
            if p.is_file() and p.suffix.lower() in FIG_EXT:
                r = core.rel(p)
                ent = man.get(r)
                if not ent:
                    problems.append(f"{r}: no manifest entry (figures must be built by `./ra figs` from a script)")
                elif ent.get("output_sha256") != core.sha256_file(p):
                    problems.append(f"{r}: modified after it was built; rebuild with `./ra figs`")
    for out, ent in man.items():
        src = core.path(ent.get("source", ""))
        if not src.exists():
            problems.append(f"{out}: source {ent.get('source')} is missing (figures must be regenerable)")
        elif core.sha256_file(src) != ent.get("source_sha256"):
            problems.append(f"{out}: source {ent.get('source')} changed since the build; run `./ra figs`")
        for inp, digest in (ent.get("inputs") or {}).items():
            ip = core.path(inp)
            if not ip.exists() or core.sha256_file(ip) != digest:
                problems.append(f"{out}: input {inp} changed since the build; run `./ra figs`")
    return problems


def _walk_json(obj, out: set):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        for t in NUM_TOKEN.findall(obj):
            try:
                out.add(float(t))
            except ValueError:
                pass
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_json(v, out)
    elif isinstance(obj, list):
        for v in obj[:200000]:
            _walk_json(v, out)


def numeric_values(max_bytes: int = 20_000_000) -> set[float]:
    """All numbers appearing in results/ text files (JSON parsed, others tokenised)."""
    vals: set[float] = set()
    rdir = core.path("results")
    if not rdir.exists():
        return vals
    budget = max_bytes
    for p in sorted(rdir.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXT or "_archive" in p.parts:
            continue
        size = p.stat().st_size
        if size > budget:
            continue
        budget -= size
        text = core.read_text(p) or ""
        if p.suffix.lower() == ".json":
            try:
                _walk_json(json.loads(text), vals)
                continue
            except json.JSONDecodeError:
                pass
        for t in NUM_TOKEN.findall(text):
            try:
                vals.add(float(t))
            except ValueError:
                pass
    return vals
