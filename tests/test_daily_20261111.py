#!/usr/bin/env python3
"""Daily-ten 11 Nov 2026 — library demos (forge run).

Ten new pure-Qasida library demos under examples/*_demo.fg. Each is run
with `forge.py run` and its stdout must match the expected transcript
exactly.
- Libraries: csv (#15), json (#16), log (#53), metrics, option,
  result, stats, collections, cli (#54), dataset — modules that had
  no demo; expectations computed independently (float32, %g).
Verified 11 Nov 2026: 20/20 under the Python reference compiler AND
20/20 under the hosted compiler (with the OS half below).
Note: csv.fg's header claims a non-numeric field becomes 0.0 in `data`,
but parse_float raises instead — only the label column may hold strings
(fix candidate).

OS half REMOVED 12 Nov 2026: the ten native OS apps under
examples/os/app_*.fg (termwin, env, echo, pwd, ls, cat, cp, grep, wc,
date) moved with the OS to MOON-OS
(https://github.com/themythofsisyphusjayant/MOON-OS); this file now
covers the library demos only (10/10).
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
FAILURES = []

EXPECTED = {
    "csv_demo": "2\n2\n1\n20\n2\n19\ngorakhpur\nkanpur\nid\nage\ncity\n0\n1\n",
    "json_demo": "qasida\n2.0.0\nmissing=[  ]\n{\"lang\": \"qasida\"}\n",
    "log_demo": ("[DEBUG] boot\n0\n[INFO] ready\n0\n[WARN] low disk\n0\n"
                 "[ERROR] disk full\n0\n0\n0\n[WARN] warn shown\n0\n"
                 "[ERROR] error shown\n0\n"),
    "metrics_demo": ("0.8\n2\n1\n0\n2\n1\n0.666667\n0.666667\n1\n0.8\n0.8\n"
                     "0.333333\n0.333333\n0.785714\n2.71828\n"),
    "option_demo": "true\n42\n7\n42\nqasida\n",
    "result_demo": "true\n5\nfalse\ndiv by zero\n99\n5\n",
    "stats_demo": "33\n1\n6\n2.66667\n1.63299\n4\n",
    "collections_demo": "3\n30\n20\n2\n2\ntrue\nfalse\ntrue\n2\n",
    "cli_demo": "true\nfalse\n0.05\n10\n0.05\n10\nprog\n0.05\ntrain.fg\n",
    "dataset_demo": "3\n20\n30\n40\n50\n2\n1\n2\n",
}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def main():
    print("daily-ten 11 Nov 2026 library demos (forge run)")
    for name, expected in EXPECTED.items():
        path = os.path.join("examples", name + ".fg")
        r = subprocess.run(FORGE + ["run", path],
                           capture_output=True, text=True, cwd=ROOT)
        check(name + " runs", r.returncode == 0, r.stderr[-200:])
        check(name + " exact output", r.stdout == expected,
              repr(r.stdout))
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
