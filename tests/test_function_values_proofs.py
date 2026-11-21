#!/usr/bin/env python3
"""Function-values slice 21 Nov 2026 — library proofs #102 / #129 / #273.

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly: 3 demos x 2 compilers x 2 checks
= 12 checks. Expected values were hand-derived BEFORE the first
run (independent Python replica;
~/workspace/blackmoon-iso/function-values-slice/replica_proofs.py)
and cross-checked against the replica output.
No demo writes files; every demo runs with stdin as /dev/null
so no demo can block.

Usage:
  python3 tests/test_function_values_proofs.py
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
    'hof_demo': '2\n4\n6\na!\nb!\n2\n2\n4\n2\n2\n4\n10\n24\n16\n',
    'sortby_demo': '1\n2\n3\n3\n2\n1\n0\n1\n-2\n-3\n3\n',
    'emitter_demo': '5\n10\n2\n100\n1\n0\n7\n1\n7\n14\n2\n',
}

INPUT = {}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_one(name, expected, env_extra):
    path = os.path.join(ROOT, "examples", name + ".fg")
    env = dict(os.environ)
    env.update(env_extra)
    kwargs = {"capture_output": True, "text": True, "cwd": ROOT,
              "env": env, "timeout": 180}
    if name in INPUT:
        kwargs["input"] = INPUT[name]
    else:
        kwargs["stdin"] = subprocess.DEVNULL
    try:
        r = subprocess.run(FORGE + ["run", path], **kwargs)
    except subprocess.TimeoutExpired:
        check(f"{name} runs", False, "TIMEOUT after 180s")
        return
    check(f"{name} runs rc=0", r.returncode == 0, r.stderr[-300:])
    check(f"{name} exact stdout", r.stdout == expected,
          "" if r.stdout == expected else f"got: {r.stdout!r}")


def main():
    print("function-values slice — proofs #102/#129/#273 (3 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
