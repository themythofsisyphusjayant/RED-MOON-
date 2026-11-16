#!/usr/bin/env python3
"""Daily-ten 16 Nov 2026 — library track (10 new stdlib modules).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-computed
BEFORE the first run (independent Python replica for the
xgboost/lightgbm gains, keras softmax, LCG shuffle, attention,
PPM/segmentation traces; /tmp/replica_20261116.py).

Usage:
  python3 tests/test_daily_20261116.py
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
    "xgboost_demo": "2\n1.33333\n-0.666667\n0.666667\n-0.166667\n1.16667\n",
    "lightgbm_demo": ("2 2\n-1 1\n0.5 0.5\n0\n1.33333\n"
                      "0.666667\n-0.666667\n"),
    "keras_demo": "0.35 0.5\n0.46257 0.53743\n0.620957\n1\n",
    "torchdata_demo": "4\n3 6\n1 0 4 2 5 3\n20 10\n",
    "transformers_demo": ("1.66048 2.66048\n2.33952 3.33952\n3 4\n"
                          "0.841471 0.540302 0.00999983 0.99995\n"),
    "imageio_demo": ("P3\n2 2\n255\n"
                     "255 0 0 0 255 0 0 0 255 255 255 255\n\n"
                     "76 149 29 255\n255 0 0 255\n"
                     "0 255 0 255 0 0\n255 255 255 0 0 255\n"),
    "detection_demo": "1\n1\n0\n0.142857\ntrue\n",
    "segmentation_demo": ("0 1 0\n1 1 0\n0 0 1\n0 2 0\n2 2 0\n0 0 9\n"
                          "3\n1\n"),
    "agents_demo": "0.595\n0.6175\n1\n1282168119\n0.595\n",
    "ppo_demo": "1.2214\n1.2\n-0.610701\n-1.22474 0 1.22474\n0.693147\n",
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
    print("daily-ten 16 Nov 2026 — library track (10 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
