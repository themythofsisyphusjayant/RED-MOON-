#!/usr/bin/env python3
"""Daily-ten 15 Nov 2026 — library track (10 new stdlib modules).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-computed
BEFORE the first run (Python replicas for the LCG sequences,
the UCB/BLEU/SGD/SVM traces and the TextRank step; hand traces
for the rest).

Usage:
  python3 tests/test_daily_20261115.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE_PY = os.environ.get(
    "FORGE_PY", os.path.expanduser("~/workspace/forge-v2/forge.py"))
FORGE = [sys.executable, FORGE_PY]
FAILURES = []

EXPECTED = {
    "bandits_demo": "1\n0\n1\n1282168119\n2\n",
    "gym_demo": ("1\n1282168119\n0\n4 1 1\n0 0 0\n"
                 "0 0.02 0.1 -0.0004\n-0.49525 0.00475\n"),
    "metricstext_demo": "0.513417\n0.6\n1\n1\n",
    "tracking_demo": ("true\nrun1|lr=0.01|acc=850\n"
                      "run2|lr=0.02|acc=910\n2\ntrue\n"),
    "linearmodels_demo": "1.86667\n2\n2\n-2\n0\n1.8\n1.67111\n0.693333\n",
    "svm_demo": "0\n0.5\n2\n0.5\n0.12\n0\n1\n1\n",
    "clustering_demo": "0\n0\n0\n1\n1\n-1\n1\n2\n3\n",
    "modelselect_demo": "8\n2\n4\n6\n1\n3\n1401261805\n",
    "summarize_demo": "3\n0\n1\n1\n0.15\n0\n",
    "ner_demo": ("PERSON\nO\nO\nPLACE\nO\nO\nO\nORG\n3\n"
                 "Jayant\nDelhi\nQasida\n"),
}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_one(name, expected, env_extra):
    path = os.path.join(ROOT, "examples", name + ".fg")
    env = dict(os.environ)
    env.update(env_extra)
    try:
        r = subprocess.run(FORGE + ["run", path], capture_output=True,
                           text=True, cwd=ROOT, env=env, timeout=180)
    except subprocess.TimeoutExpired:
        check(f"{name} runs", False, "TIMEOUT after 180s")
        return
    check(f"{name} runs rc=0", r.returncode == 0, r.stderr[-300:])
    check(f"{name} exact stdout", r.stdout == expected,
          "" if r.stdout == expected else f"got: {r.stdout!r}")


def main():
    print("daily-ten 15 Nov 2026 — library track (10 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
