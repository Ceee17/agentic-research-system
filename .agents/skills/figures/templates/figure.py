"""Figure: <the one message this figure conveys>. Data: results/<run>/data.csv, results/<run>/metrics.json.

Built by `./ra figs` as:  python figures/scripts/<stem>.py --out figures/<stem>.pdf
"""
import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]            # papers/<slug>/
STYLE = ROOT.parents[1] / ".claude" / "skills" / "figures" / "templates" / "paper.mplstyle"  # workspace
DATA = ROOT / "results/example_run/data.csv"          # literal results/ paths -> recorded as inputs
METRICS = ROOT / "results/example_run/metrics.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    plt.style.use(str(STYLE))

    with open(DATA, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    xs = [int(r["rep"]) for r in rows]
    ys = [float(r["value"]) for r in rows]
    pred = json.loads(METRICS.read_text(encoding="utf-8"))["theory_prediction"]

    fig, ax = plt.subplots()
    ax.plot(xs, ys, "o", label="simulation")
    ax.axhline(pred, linestyle="--", label="theory")
    ax.set_xlabel("replicate")
    ax.set_ylabel(r"$\hat{m}_2$")
    ax.legend()
    fig.savefig(a.out)
    fig.savefig(a.out.with_suffix(".png"), dpi=200)   # preview for quick inspection


if __name__ == "__main__":
    main()
