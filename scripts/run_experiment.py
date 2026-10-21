"""./ra run — execute an experiment / derivation script and record provenance.

  ./ra run experiments/<name>.py [--id ID] [--seed N] [--timeout S] [--force] [-- extra args]
  ./ra run --verify ID          re-run a recorded run in a temp dir and compare outputs (reproducibility)
  ./ra run --list

Contract for scripts: accept `--seed INT --out DIR`, write every output into DIR (e.g. metrics.json,
data.csv, derivation.json/.tex), seed all RNGs from --seed. The run is recorded in results/manifest.json
with script hash, command, seed, package versions, git commit and SHA-256 of every output.
Nothing else may write into results/ (hooks block it; `complete` rejects unrecorded files).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ra import core, pipeline, results  # noqa: E402

PKGS = ["numpy", "scipy", "sympy", "matplotlib", "pandas", "seaborn", "networkx", "mpmath"]
NONDETERMINISTIC = {"log.txt"}


def pkg_versions() -> dict:
    out = {}
    for p in PKGS:
        try:
            out[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            pass
    return out


def hash_outputs(outdir: Path) -> dict:
    return {core.rel(p): core.sha256_file(p) for p in sorted(outdir.rglob("*")) if p.is_file()}


def execute(script: Path, outdir: Path, seed: int, extra: list[str], timeout: int) -> tuple[int, float]:
    outdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONHASHSEED=str(seed), RA_SEED=str(seed), RA_OUT=str(outdir), MPLBACKEND="Agg",
               OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    cmd = [sys.executable, str(script), "--seed", str(seed), "--out", str(outdir), *extra]
    t0 = time.time()
    with open(outdir / "log.txt", "w", encoding="utf-8") as log:
        try:
            proc = subprocess.run(cmd, cwd=str(core.root()), env=env, stdout=log, stderr=subprocess.STDOUT,
                                  timeout=timeout)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            log.write(f"\n[ra run] TIMEOUT after {timeout}s\n")
            code = 124
    return code, time.time() - t0


def _json_close(a: Path, b: Path) -> bool:
    try:
        ja, jb = json.loads(a.read_text(encoding="utf-8")), json.loads(b.read_text(encoding="utf-8"))
    except Exception:
        return False

    def eq(x, y):
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool):
            return abs(x - y) <= 1e-9 * max(1.0, abs(x), abs(y))
        if isinstance(x, dict) and isinstance(y, dict):
            return x.keys() == y.keys() and all(eq(x[k], y[k]) for k in x)
        if isinstance(x, list) and isinstance(y, list):
            return len(x) == len(y) and all(eq(p, q) for p, q in zip(x, y))
        return x == y
    return eq(ja, jb)


def main() -> int:
    ap = argparse.ArgumentParser(prog="./ra run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", nargs="?")
    ap.add_argument("--id")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--force", action="store_true", help="overwrite (old outputs are archived)")
    ap.add_argument("--verify", metavar="ID")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("extra", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    extra = a.extra[1:] if a.extra[:1] == ["--"] else a.extra

    st = pipeline.load_state()
    if not pipeline.intake_confirmed() or not pipeline.gate_ok(st, "gate1_topic"):
        print("refused: experiments run only after intake confirmation and Gate 1 (topic) approval", file=sys.stderr)
        return 1
    man = results.manifest()

    if a.list:
        for rid, r in man.get("runs", {}).items():
            print(f"{rid:<24} rc={r['returncode']} seed={r['seed']} {r['script']} ({len(r['outputs'])} files, "
                  f"{r['duration_s']}s)")
        return 0

    if a.verify:
        run = man.get("runs", {}).get(a.verify)
        if not run:
            print(f"no recorded run '{a.verify}'", file=sys.stderr)
            return 1
        tmp = Path(tempfile.mkdtemp(prefix="ra-verify-"))
        code, _ = execute(core.path(run["script"]), tmp, run["seed"], run.get("extra_args", []), a.timeout)
        bad = []
        for relf in run["outputs"]:
            name = Path(relf).relative_to(Path("results") / a.verify)
            if name.name in NONDETERMINISTIC:
                continue
            new, old = tmp / name, core.path(relf)
            if not new.exists():
                bad.append(f"{name}: not produced on re-run")
            elif core.sha256_file(new) != core.sha256_file(old) and not (new.suffix == ".json" and _json_close(new, old)):
                bad.append(f"{name}: differs on re-run")
        shutil.rmtree(tmp, ignore_errors=True)
        if code != 0 or bad:
            print(f"NOT reproducible (rc={code}):\n  " + "\n  ".join(bad), file=sys.stderr)
            return 1
        print(f"{a.verify}: reproducible (all deterministic outputs identical)")
        return 0

    if not a.script:
        ap.print_help()
        return 2
    script = core.resolve_arg(a.script)
    rs = core.rel(script)
    if not rs or not rs.startswith("experiments/") or not script.exists():
        print("script must be an existing file under experiments/", file=sys.stderr)
        return 1
    rid = a.id or script.stem
    outdir = core.path("results", rid)
    if outdir.exists():
        if not a.force:
            print(f"results/{rid} exists; use --force to re-run (old outputs are archived)", file=sys.stderr)
            return 1
        arch = core.path("results", "_archive", f"{rid}-{core.stamp()}")
        arch.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(outdir), str(arch))
    started = core.now()
    code, dur = execute(script, outdir, a.seed, extra, a.timeout)
    head = core.git_head()
    dirty = bool(core.is_git_repo() and core.git("status", "--porcelain", "--", rs).stdout.strip())
    man.setdefault("runs", {})[rid] = {
        "script": rs, "script_sha256": core.sha256_file(script), "seed": a.seed, "extra_args": extra,
        "command": f"./ra run {rs} --id {rid} --seed {a.seed}" + (" -- " + " ".join(extra) if extra else ""),
        "started_at": started, "duration_s": round(dur, 2), "returncode": code,
        "python": platform.python_version(), "platform": platform.platform(), "packages": pkg_versions(),
        "git_commit": head, "script_uncommitted": dirty, "outputs": hash_outputs(outdir)}
    core.write_json(core.path(*results.MANIFEST), man)
    tail = (core.read_text(outdir / "log.txt") or "").strip().splitlines()[-15:]
    print("\n".join(tail))
    if code != 0:
        print(f"\nrun '{rid}' FAILED (rc={code}); see results/{rid}/log.txt", file=sys.stderr)
        return 1
    print(f"\nrecorded run '{rid}' -> results/{rid}/ ({len(man['runs'][rid]['outputs'])} files). "
          "Next: `./ra results-tex` to expose numbers to the paper.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
