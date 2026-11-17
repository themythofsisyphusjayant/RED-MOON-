#!/usr/bin/env python3
"""Daily-ten 17 Nov 2026 — library track (10 new stdlib modules).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-computed
BEFORE the first run (independent Python replica;
 /tmp/replica_20261117.py), including the LCG random-search draws,
EMA trace, quant zero-point, and the bert-finetune SGD step.

Usage:
  python3 tests/test_daily_20261117.py
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
    "tensorboard_demo": ("1 0.9 0.9 0.75 0.725 0.6125 0.50625 0.478125\n"
                         "0.4 1 0.66875\n"
                         "1 0.9 0.7 0.4\n"),
    "optuna_demo": "1.74579 1.06462\n2 1\n2.09706\n",
    "explain_demo": ("0\n20 1\n0.231224 0.628532 0.140244\n1\n"),
    "onnx_demo": "58\n5\n512\nMatMul,Add,Relu,MatMul,Add\n",
    "quant_demo": ("0.00784314 128\n128 192 255 64\n0.00392157\n"
                   "0.00196078 0\n"),
    "multiagent_demo": "1 3\n-4\n2 2 -2\n2 2 -2\n",
    "bertfinetune_demo": ("0 0.666667\n0.339244 0.660756\n0.41437\n"
                          "0.321909\n"),
    "datasetsext_demo": ("9 12\n4\n0 0.5 1\n10 40\n1\n1 3\n"),
    "autogradext_demo": ("0.16 -0.1 -0.06\n5 6 7 8 1 3 2 4\n"
                         "5.43656 0.5\n20\n4 0 2\n"),
    "nnext_demo": ("-2 -2\n12 16 24 28\n0.3 0.4\n2 0 6 0\n"
                   "-1.22474 0 1.22474\n0.731059\n"),
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
    print("daily-ten 17 Nov 2026 — library track (10 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
