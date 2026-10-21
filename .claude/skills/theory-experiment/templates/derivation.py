"""Symbolic checks for <result>. Every algebraic step used in a proof gets a check here.

Run via:  ./ra run experiments/derive_<name>.py --seed 0
Writes into --out: derivation.json (all checks, verified true/false), <name>.tex snippets, metrics.json.
"""
import argparse
import json
from pathlib import Path

import sympy as sp

CHECKS = []


def check(name: str, statement: str, expr_is_zero, method: str = "simplify") -> bool:
    """Record whether `expr_is_zero` simplifies to 0 (i.e. the claimed identity holds)."""
    ok = sp.simplify(expr_is_zero) == 0
    CHECKS.append({"name": name, "statement": statement, "verified": bool(ok), "method": method})
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)  # unused, kept for the ./ra run contract
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    x, r = sp.symbols("x r", positive=True)
    f = r * x * (1 - x)                                   # example model
    fixed = sp.solve(sp.Eq(f, x), x)                      # fixed points
    x_star = [s for s in fixed if s != 0][0]
    check("fixed_point", "x* = 1 - 1/r solves f(x) = x", x_star - (1 - 1 / r))
    slope = sp.diff(f, x).subs(x, x_star)
    check("slope_at_fixed_point", "f'(x*) = 2 - r", slope - (2 - r))

    (a.out / "derivation.json").write_text(json.dumps({"checks": CHECKS}, indent=2), encoding="utf-8")
    (a.out / "fixed_point.tex").write_text(f"x^* = {sp.latex(x_star)}\n", encoding="utf-8")
    n_ok = sum(c["verified"] for c in CHECKS)
    (a.out / "metrics.json").write_text(json.dumps({"checks_total": len(CHECKS), "checks_verified": n_ok}),
                                        encoding="utf-8")
    for c in CHECKS:
        print(("OK   " if c["verified"] else "FAIL ") + c["name"] + ": " + c["statement"])
    if n_ok != len(CHECKS):
        raise SystemExit("some symbolic checks failed")


if __name__ == "__main__":
    main()
