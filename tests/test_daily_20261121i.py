#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 9 (20 flips + triple advance).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly: 21 demos x 2 compilers x 2 checks
= 84 checks. The 20 flips are the catalog items below; the 21st
demo (triple) verifies triple.fg, which advances #326 (triples
landed) without closing it — sysroots are still missing, so
#326 stays PARTIAL. Expected values were hand-derived
BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch9/replica_20261121i.py),
including builder text, specialization names, the recursive
type-level evaluator, pass violations from line lengths and
substring hits, AST nodes and whole-word rename, trait
registries, extract-function text, coverage percents, the
mock-lite call count, harness summary, the one-operator
evaluator with mutants, load-plan arithmetic, golden diffs,
doctest extraction, workspace edges, profile flags, triple
splits, FNV-1a staleness, cache ops and vendor paths. No demo
writes files; every demo runs with stdin as /dev/null so no
demo can block.

Usage:
  python3 tests/test_daily_20261121i.py
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
    'srcgen_demo': 'PointBuilder\n2\nx\nint\nstruct PointBuilder {\n    x: int;\n    y: int;\n}\nPointBuilder__with_x\nfn PointBuilder__build(b: PointBuilder) -> Point\n',
    'genspec_demo': '3\nmax_int\nmax_float\nmax_str\ntrue\nfalse\nspecialized\ngeneric\n',
    'typemeta_demo': '5\n20\n6\n4\nint\nstr\n10\ntrue\nfalse\n',
    'ccpass_demo': '3\nerror max-len: line 1: line too long\nwarn no-println: line 2: println in library code\nerror max-len: line 3: line too long\n2\n1\n',
    'astapi_demo': '3\nfn main @ 1\nlet x @ 2\nstruct Tensor @ 5\n0\n2\n-1\nlet x = sum(2, 3);\n',
    'typehier_demo': '2\nPoint\nUser\ntrue\nfalse\n2\nDisplay\nClone\n0\n',
    'extractfn_demo': '2\nfn sum2(a: int, b: int) -> int {\n    let s = a + b;\n    return s;\n}\nsum2(a, b)\n',
    'cov_demo': '40\n50\ntrue\nfalse\ntrue\nfalse\n',
    'mock_demo': '0\n2\n42\n',
    'itharness_demo': '2\n2\n120\n2 passed, 2 failed, 120ms\n',
    'muttest_demo': '7\na-b\ntrue\ntrue\nfalse\n66\n',
    'loadtest_demo': '12000\n200\n50\n100\n',
    'golden_demo': '0\ntrue\n1\nline 1: expected \'mov rax, 1\' got \'mov rax, 2\'\nfalse\n1\nline 2: missing \'ret\'\n',
    'doctest_demo': '2\na+b\na*b\ntrue\ntrue\nfalse\n2\n',
    'workspace_demo': 'crates/cli\nfalse\ntrue\nfalse\n2\ncli\nweb\n',
    'buildprof_demo': '-O0 -g --checks\n-O3\ntrue\n0\n3\n',
    'triple_demo': 'aarch64\nunknown\nlinux-gnu\ntrue\nfalse\nwasm32\nunknown\ntrue\nfalse\n',
    'incr_demo': 'false\ntrue\ntrue\n1\nb.fg\n',
    'buildcache_demo': 'true\nfalse\n3\n2\n2\n75\n',
    'vendor_demo': 'vendor/foo-1.0\nfalse\n1\nbaz-0.9\n2\n',
    'unused_demo': '4\n1\nw\ntrue\nfalse\n',
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
    print("daily-ten 21 Nov 2026 — library sprint batch 9 (21 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
