#!/usr/bin/env python3
"""Daily-ten 11 Nov 2026 — OS apps + library demos (forge run).

Ten native OS apps under examples/os/app_*.fg and ten new pure-Qasida
library demos under examples/*_demo.fg. Each is run with `forge.py
run` and its stdout must match the expected transcript exactly.
- OS: termwin (Terminal in a window, native form — scroll-on-overflow
  buffer drawn in an ASCII window), env, echo, pwd, ls (size-sorted),
  cat, cp, grep, wc, date (day-of-year arithmetic).
- Libraries: csv (#15), json (#16), log (#53), metrics, option,
  result, stats, collections, cli (#54), dataset — modules that had
  no demo; expectations computed independently (float32, %g).
Verified 11 Nov 2026: 20/20 under the Python reference compiler AND
20/20 under the hosted compiler. Note: csv.fg's header claims a
non-numeric field becomes 0.0 in `data`, but parse_float raises
instead — only the label column may hold strings (fix candidate).
app_termwin first shipped with index assignment through a function
parameter; the hosted checker rejects that (params are immutable)
while Python's checker accepts it — the demo now returns the new
buffer, the collections.fg pattern.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
FAILURES = []


def pad_to(s, w):
    return s + " " * max(0, w - len(s))


BORDER = "+" + "-" * 30 + "+"
ROWS = ["h f c", "> f", "a.txt b.txt", "> c", "(cleared)", "> _"]
TERMTEXT = "6\n" + BORDER + "\n"
TERMTEXT += "| " + pad_to("Terminal - jalos", 28) + " |\n"
TERMTEXT += BORDER + "\n"
for _r in ROWS:
    TERMTEXT += "| " + pad_to(_r, 28) + " |\n"
TERMTEXT += BORDER + "\n"

EXPECTED = {
    "app_termwin": TERMTEXT,
    "app_env": "/home/jayant\n/bin/sh\n/bin:/usr/bin\n4\n",
    "app_echo": "hello qasida world\n3\nhello\nworld\n",
    "app_pwd": "/home/jayant/forge-v2\n3\n/home/jayant\n",
    "app_ls": "forge.py 8400\ntodo.fg 1500\nREADME.md 1200\nnotes.txt 300\n11400\n",
    "app_cat": "line one\nline two\nline three\n3\n26\n",
    "app_cp": "hello world\ntrue\n11\n",
    "app_grep": "1 error: disk full\n3 error: net down\n2\n",
    "app_wc": "3\n6\n30\n",
    "app_date": "2026-11-11\nWed\n315\n50\nfalse\n30\n",
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
    print("daily-ten 11 Nov 2026 OS apps + library demos (forge run)")
    for name, expected in EXPECTED.items():
        if name.startswith("app_"):
            path = os.path.join("examples", "os", name + ".fg")
        else:
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
