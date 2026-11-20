#!/usr/bin/env python3
"""Daily-ten 20 Nov 2026 — library track (10 new stdlib modules).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-computed
BEFORE the first run (independent Python replica;
 /tmp/replica_20261120.py), including the float32 GELU /
 softmax / layernorm / quantisation values, the decision-tree
 Gini splits, and the Dijkstra distances.

Usage:
  python3 tests/test_daily_20261120.py
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
    "decisiontree_demo": ("0 3.5 0.2\n0 1.5\n0 5.5\n0 0 1 0\n"),
    "quantv3_demo": ("0.0117647\n85\n0 64 85 106 255\n-0.247059 0.247059\n"
                     "0.0117647 170\n0.0196078 0\n"),
    "visionv3_demo": ("3 2 1 6 5 4\n5 6 8 9\n30 35 40 45 50 55 60 65 70\n"
                      "0 0 255 255 255\n"),
    "nnextv2_demo": ("-0.158808 0 0.841192 1.9546\n0.50648 0.307196 0.186324\n"
                     "-1.34164 -0.447212 0.447212 1.34164\n2 0 6 0\n"),
    "framesext2_demo": ("2 20 200 3 30 300\n2 1 1\n2 3 4\n"),
    "sentencepiece2_demo": "1\nlow\n1\ntest\nlow test\n",
    "csv2_demo": ("4\na\nb,c\nd\"e\nf\na,\"b,c\",\"d\"\"e\",f\n"),
    "pandasv2_demo": "3 1 5\n1 3 2 2 3 1\n1 3 3 3 5\n",
    "numpyv2_demo": "1 3 6 10\n1 2 0\n2 3\n32\n",
    "graphv2_demo": "0 1 2 3\n0 1 3 2\n0 4 1 5\n",
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
    print("daily-ten 20 Nov 2026 — library track (10 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
