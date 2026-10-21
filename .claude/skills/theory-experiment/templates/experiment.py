"""Experiment: <what hypothesis / prediction this tests>.

Run via:  ./ra run experiments/<name>.py --id <name> --seed 0 [-- --n 1000 --reps 20]
Writes into --out: metrics.json (numbers for the paper), data.csv (raw results).
"""
import argparse
import json
from pathlib import Path

import numpy as np


def simulate(rng: np.random.Generator, n: int) -> float:
    """One replicate. Replace with the model from experiments/theory.md."""
    x = rng.standard_normal(n)
    return float(np.mean(x ** 2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--reps", type=int, default=20)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(a.seed)
    values = np.array([simulate(rng, a.n) for _ in range(a.reps)])

    # raw data
    with open(a.out / "data.csv", "w", encoding="utf-8") as f:
        f.write("rep,value\n")
        for i, v in enumerate(values):
            f.write(f"{i},{v!r}\n")

    # numbers for the paper (become \res<Id>... macros via ./ra results-tex)
    metrics = {
        "n": a.n,
        "reps": a.reps,
        "mean": float(values.mean()),
        "std": float(values.std(ddof=1)),
        "theory_prediction": 1.0,  # from the proposition in theory.md
        "_format": {"mean": ".3f", "std": ".3f"},
    }
    (a.out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"mean={metrics['mean']:.4f} std={metrics['std']:.4f} (prediction {metrics['theory_prediction']})")


if __name__ == "__main__":
    main()
