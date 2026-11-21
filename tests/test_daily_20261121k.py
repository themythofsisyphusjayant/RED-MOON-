#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 11 (20 flips).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly: 20 demos x 2 compilers x 2 checks
= 80 checks. The 20 flips are the catalog items below (20 GAP
-> HAVE, no PARTIAL closes). Expected values were hand-derived
BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch11/replica_20261121k.py)
and cross-checked programmatically against the replica output,
including threat-model worst risks, reflection field counts,
annotation lookups, cfg predicates, alias conflicts,
re-export chains, template substitution, dedent, raw/cooked
round-trips, memo hits/misses, depth-guard overflows,
NaN/Infinity classification, pool eviction, future states,
latch counts, event-loop results, observable deliveries,
task-group counts, zero-copy reads and the coverage-guided
fuzzer (LCG seed 42, 60 steps, edges 1/0/2/3 found). No demo
writes files; every demo runs with stdin as /dev/null so no
demo can block.

Usage:
  python3 tests/test_daily_20261121k.py
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
    'threat_demo': '2\n2\nhigh\nhigh\n2\nbrute-force\ncredential-stuffing\ntrue\nfalse\n',
    'reflect_demo': 'struct\n3\nx,y\ntrue\nfalse\nfalse\n3\n',
    'annot_demo': 'Debug,Clone\nrename_all=snake\n/api/users\n\n2\nderive\nserde\nfalse\n',
    'cfg_demo': 'true\nfalse\ntrue\ntrue\nfalse\ntrue\nfalse\ntrue\ntrue\ntrue\n',
    'alias_demo': 'stdlib/json.fg\nstdlib/http.fg\n\ntrue\nfalse\n1\n2\n',
    'reexport_demo': 'math::max\ncore::len\njson::to_json\n\n3\n1\nmax\nlen\npush\ntrue\nfalse\n',
    'strinterp_demo': 'hello Ada, you have 5 messages\nfrom Paris with love\nunknown {zz} stays\nbrace {name} literal\nno placeholders\ntrue\nfalse\n',
    'mlstr_demo': '3\nfn main() {\n    let x = 1;\n}\nfn main() {\n    let x = 1;\n}\n',
    'rawstr_demo': 'a\nb\n3\na\\nb\n4\nx\ty\np\\\\q\n4\n',
    'memo_demo': '49\n49\n14\n55\n55\n2\n3\n3\n',
    'recdepth_demo': 'true\n1\ntrue\n2\ntrue\n3\nfalse\n3\n1\n2\n1\n3\n',
    'naninf_demo': 'true\ntrue\ntrue\ntrue\nfalse\nfalse\n1\n-1\n0\ninf\n-inf\nnan\nfinite\n',
    'connpool_demo': 'true\n1\ntrue\n2\nfalse\n1\ntrue\n1\ntrue\n2\nfalse\ntrue\n2\n',
    'future_demo': 'pending\n-1\nready\n42\nfalse\nfalse\ntrue\n2\n7\n',
    'latch_demo': '3\n2\n1\nfalse\n0\ntrue\n3\n0\n3\n',
    'evloop_demo': '4\n0\n4\n42\n25\n-9\n42\n5\n6\n',
    'observ_demo': '0\n1\n2\n2\n5\n-1\n3\n7\n5\n1\n1\n',
    'taskgroup_demo': '3\n3\n2\ntrue\n1\nfalse\n0\ntrue\n3\n0\n',
    'zerocopy_demo': '4\n42\n7\n99\n13\n-1\n2\n0\n',
    'covfuzz_demo': '2\n60\n4\n4\n1\n0\n2\n3\n',
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
    print("daily-ten 21 Nov 2026 — library sprint batch 11 (20 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
