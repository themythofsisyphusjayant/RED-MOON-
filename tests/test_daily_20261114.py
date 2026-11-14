#!/usr/bin/env python3
"""Daily-ten 14 Nov 2026 — library track (10 new stdlib modules).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-computed
BEFORE the first run (Python replicas for the LCG sequences and
the tar checksum; hand traces for the rest).

Usage:
  python3 tests/test_daily_20261114.py
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
    "strutils_demo": "00042\nab***\nQASIDA\nmoon\nHello World\n3\n",
    "regexfull_demo": "4\ndog\n0\n4\n",
    "apimock_demo": "200\nuser-list\n201\n404\n3\n",
    "workerpool_demo": "25\n27\n14\n3\n",
    "unittest_demo": "3\n1\n4\n",
    "propgen_demo": "6\ntrue\na\n",
    "feedreader_demo": "First Post\n/first\nSecond Post\n/second\n2\n1\n",
    "randext_demo": "10\ngreen\n3\n2\n1\n4\n5\n",
    "mdhtml_demo": ("<h1>Hello</h1>\n<p>This is <b>bold</b> text</p>\n"
                    "<p>plain line</p>\n3\n"),
    "tarball_demo": "3345\n2048\ntrue\n5\ntrue\ntrue\n2048\n",
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
    print("daily-ten 14 Nov 2026 — library track (10 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
