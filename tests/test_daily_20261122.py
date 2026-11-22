#!/usr/bin/env python3
"""Daily-ten 22 Nov 2026 — sprint day 2, #393 live reload.

Runs livereload_demo.fg under `forge.py run` with BOTH compilers
(hosted default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-derived from
the independent Python replica
(~/workspace/blackmoon-iso/daily-20261122-batch1/replica_20261122.py)
BEFORE the first run; the replica output was cross-checked against
the demo transcript line by line.

Note: the cron run's #393 scratch copy was lost when a VM restart
wiped /tmp (22 Nov ~09:40 IST). This file rebuilds the module from
the surviving LANDING_NOTES.md + replica, re-verified in-tree against
the then-current hosted binary (build 4, md5 db234d82).

Usage:
  python3 tests/test_daily_20261122.py
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
    "livereload_demo": ("false\nhello v1:/hi\n1\nhello v2:/hi\n2\n2\n1\n2\n"
                        "hello v1:/hi\n1\nhello v2:/hi\nhello v2 fixed:/hi\n2\n"
                        "\nfalse\nbye:/x\nbye:/x\nfalse\n\n-1\n"),
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
                           text=True, cwd=ROOT, env=env, timeout=180,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        check(f"{name} runs", False, "TIMEOUT after 180s")
        return
    check(f"{name} runs rc=0", r.returncode == 0, r.stderr[-300:])
    check(f"{name} exact stdout", r.stdout == expected,
          "" if r.stdout == expected else f"got: {r.stdout!r}")


def main():
    print("daily-ten 22 Nov 2026 — sprint day 2 (#393 live reload)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
