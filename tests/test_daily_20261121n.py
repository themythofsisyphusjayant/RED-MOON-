#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 14 (15 flips).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly: 15 demos x 2 compilers x 2 checks
= 60 checks. The 15 flips are the catalog items below (14
GAP -> HAVE + 1 PARTIAL -> HAVE, #352). Expected values were
hand-derived BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch14/replica_20261121n.py)
and cross-checked programmatically against the replica output,
including chunk splits, LCG case generation and shrink chains,
template substitution, the CI fmt gate, inline/unroll/vectorize/
escape/PGO decisions, linear-scan register allocation, list
scheduling, bench verdicts, cross-language hover, LTO dead/
inline sets and alloc-free loop counts.
No demo writes files; every demo runs with stdin as /dev/null
so no demo can block.

Usage:
  python3 tests/test_daily_20261121n.py
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
    'pariter_demo': '3\n3\n2\n2\n0\n3\n5\n2\n4\n6\n8\n10\n12\n14\n4\n9\n5\n3\n',
    'proptest_demo': '100\n60\n10\n79\n47\n83\n93\n97\n3\n93\n46\n23\n11\n5\n2\n1\n0\n1\n1\n',
    'buildgen_demo': 'getter_count.fg\n3\nfn get_count() -> int {\n    return self.count;\n}\n// generated\na x b x\n',
    'cigate_demo': 'false\nutil.fg\nnet.fg\n2\ntrue\n0\n0\n',
    'inlinean_demo': 'true\nfalse\ntrue\nfalse\nfalse\ntrue\n3\ntiny\nhot8\nhot3\n',
    'unroll_demo': '4\n0\n4\n4\n2\n2\n4\n3\n1\n2\n0\n6\n4\n1\n2\n2\n1\n2\n1\n0\n3\n',
    'loopvec_demo': 'true\n4\n4\n0\ntrue\n4\n2\n2\nfalse\n1\n3\n0\nfalse\n1\n8\n0\nfalse\n1\n8\n0\ntrue\n4\n1\n0\n',
    'escape_demo': 'heap\nheap\nstack\nstack\nheap\n3\n2\n',
    'pgo_demo': 'true\ntrue\nfalse\nfalse\ntrue\nfalse\ninline\nkeep\noutline\nkeep\ninline\noutline\n3\n',
    'regalloc_demo': '0\n1\n2\n1\n1\n0\n0\n0\n1\n2\n3\n-1\n1\n',
    'sched_demo': '0\n2\n3\n6\n2\n2\n3\n6\n7\n4\n7\n',
    'benchtune_demo': 'stable\nregress\nimprove\nstable\nregress\n2\n1\n',
    'xhover_demo': 'parse: fn(str) -> int - parse a number\nunknown\nmemcpy: void* memcpy(void*, const void*, size_t)\nunknown\nparse -> strlen: size_t strlen(const char*)\nrender -> memcpy: void* memcpy(void*, const void*, size_t)\nunknown\n',
    'lto_demo': 'unused\ndead2\nhelper\n2\n1\n',
    'allocfree_demo': 'true\nfalse\ntrue\nfalse\n2\n3\n',
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
    print("daily-ten 21 Nov 2026 — library sprint batch 14 (15 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
