#!/usr/bin/env python3
"""Daily-ten 12 Nov 2026 — OS apps (forge run).

Ten new native OS apps under examples/os/app_*.fg, each run with
`forge.py run` and its stdout compared exactly against the
hand-computed transcript in EXPECTED:
- head: first 3 of 6 lines; tail: last 3 of 6 lines.
- sort: lexicographic bubble sort (no '<' on strings in Qasida,
  so comparison ranks characters by alphabet index).
- uniq: adjacent duplicates dropped; seq: 2..20 step 3, count + sum.
- rev: each string reversed char by char; nl: 1-based line numbers.
- tac: lines in reverse order; du: per-directory size totals.
- df: percent used + free per mount, integer division.
Each app is run under BOTH compilers: the Python reference
(QASIDA_COMPILER=python) and the hosted default. All expectations
were hand-computed before the first run.
Verified 12 Nov 2026: 10/10 under Python AND 10/10 under hosted,
byte-identical stdout.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
FAILURES = []

EXPECTED = {
    "app_head": "alpha\nbeta\ngamma\n3\n",
    "app_tail": "delta\nepsilon\nzeta\n3\n",
    "app_sort": "apple\nbanana\nfig\nkiwi\npear\nplum\n6\n",
    "app_uniq": "red\nblue\ngreen\nred\n4\n",
    "app_seq": "2\n5\n8\n11\n14\n17\n20\n7\n77\n",
    "app_rev": "adisaq\nolleh\ncba\n",
    "app_nl": "1 boot ok\n2 disk mounted\n3 net up\n4 ready\n4\n",
    "app_tac": "four\nthree\ntwo\none\n4\n",
    "app_du": "src 2000\ndocs 3000\n5000\n",
    "app_df": "/ 65 3500\n/home 40 12000\n/tmp 25 3750\n35000\n15750\n",
}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_one(name, expected, env):
    path = os.path.join("examples", "os", name + ".fg")
    r = subprocess.run(FORGE + ["run", path],
                       capture_output=True, text=True, cwd=ROOT, env=env)
    check(name + " runs", r.returncode == 0, r.stderr[-200:])
    check(name + " exact output", r.stdout == expected,
          repr(r.stdout))


def main():
    print("daily-ten 12 Nov 2026 OS apps (forge run, both compilers)")
    py_env = dict(os.environ, QASIDA_COMPILER="python")
    hosted_env = dict(os.environ)
    hosted_env.pop("QASIDA_COMPILER", None)
    for name, expected in EXPECTED.items():
        print(f"-- {name} (python) --")
        run_one(name, expected, py_env)
        print(f"-- {name} (hosted) --")
        run_one(name, expected, hosted_env)
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
