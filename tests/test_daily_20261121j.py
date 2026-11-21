#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 10 (20 flips).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly: 20 demos x 2 compilers x 2 checks
= 80 checks. The 20 flips are the catalog items below (18 GAP
+ 2 PARTIAL: #363 go to definition, #379 REPL history).
Expected values were hand-derived BEFORE the first run
(independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch10/replica_20261121j.py),
including straight-line reachability, definition/reference
indexes, prefix completions, signature params, token
classes, inlay hints, history blocks, notebook exec
numbers, breakpoint hits, C field offsets, ASCII byte
values, plugin loads, header lines, hover info, BFS
reachability, intern ids, SSO capacities, const folds
and determinism conflicts. No demo writes files; every
demo runs with stdin as /dev/null so no demo can block.

Usage:
  python3 tests/test_daily_20261121j.py
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
    'unreach_demo': '4\n4\n5\n6\n7\ntrue\nfalse\n',
    'godef_demo': '3\nmath.fg:12\ngeom.fg:3\ntrue\nfalse\n',
    'findrefs_demo': '3\nmath.fg:20\nmain.fg:5\nmath.fg:31\n1\n0\n',
    'complete_demo': '3\nmap\nmax\nmatch\n1\nPoint\n0\n',
    'sighelp_demo': 'max(a: int, b: int) -> int\n2\nb\nlen(s: str) -> int\nfalse\n',
    'semhl_demo': 'keyword\ntype\nnumber\nstring\nfunction\nvariable\ncomment\n',
    'inlay_demo': 'x: int\nname: str\npts: [int]\nfalse\n3\n',
    'replhist_demo': '5\n3\n2\n3\nlet x = 1\n3\n1\n',
    'notebook_demo': '3\n3\n4\n1\n2\nmd\n',
    'bp_demo': 'true\nfalse\ntrue\n2\n10\n-1\n',
    'clayout_demo': '0\n4\n8\n16\n24\n4\n',
    'marshal_demo': '72\n105\n33\nHi!\ntrue\n3\n',
    'plugin_demo': 'true\nfalse\ntrue\nfalse\n1\n0\n',
    'cheader_demo': '5\n#ifndef MATH_H\n#define MATH_H\nint max(int a, int b);\nint min(int a, int b);\n#endif\n',
    'hover_demo': 'max: fn(int, int) -> int - returns the larger value\nPoint: struct { x: int, y: int }\nfalse\n2\n',
    'dce_demo': '4\nmain\nhelper\nrender\nutil\n2\norphan\ndead2\n',
    'intern_demo': '0\n1\n0\n2\n3\nworld\n-1\n',
    'sso_demo': '2\ntrue\n15\n15\ntrue\n16\nfalse\n16\n',
    'consteval_demo': '5\n20\n3\n1\n-9\n20\n0\n',
    'determin_demo': 'true\n3\nfalse\n4\n',
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
    print("daily-ten 21 Nov 2026 — library sprint batch 10 (20 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
