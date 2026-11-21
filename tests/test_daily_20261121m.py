#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 13 (20 flips).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly: 20 demos x 2 compilers x 2 checks
= 80 checks. The 20 flips are the catalog items below (6
PARTIAL -> HAVE + 14 GAP -> HAVE). Expected values were
hand-derived BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch13/replica_20261121m.py)
and cross-checked programmatically against the replica output,
including sysroot lookup, numeric-trait dispatch, round-robin
scheduling, clock-driven timers, bounds proofs, LSP formatting
edits, condvar wait/notify, STM commit/abort, RCU grace
periods, lockset race detection, interleaving outcomes,
channel select, sample aggregation, heap reachability,
reverse stepping, crash symbolication, REPL eval, publish
validation, FNV-1a shell hashes and LCG fuzz counts.
No demo writes files; every demo runs with stdin as /dev/null
so no demo can block.

Usage:
  python3 tests/test_daily_20261121m.py
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
    'triple_demo': 'aarch64\nunknown\nlinux-gnu\ntrue\nfalse\nwasm32\nunknown\ntrue\nfalse\n/opt/sysroot/aarch64\n\ntrue\nfalse\n/opt/sysroot/x86_64\n3\n',
    'numtrait_demo': '13\n42\n-1\n0\n-6\n6\n3\n1.25\n5\n2\nint\nfloat\n',
    'mntask_demo': 'fetch\nparse\nwrite\nfetch\nwrite\nwrite\n3\n0\ndone\ndone\n',
    'rtimer_demo': '1\na\n1\n2\n2000\n1\n1\n1\n0\n',
    'bce_demo': 'true\nfalse\nfalse\ntrue\nfalse\ntrue\nfalse\nfalse\n1\n1\n',
    'lspfmt_demo': 'fn main() {\n    let x = 1;\n    println(x);\n}\n3\nfalse\ntrue\n7\nabc\n',
    'condvar_demo': '2\n1\nt1\n1\n1\n0\nt3\n0\n\n',
    'stm_demo': 'true\nfalse\n20\n1\ntrue\n25\n2\n1\n1\n',
    'rcu_demo': '2\n2\n0\n2\n0\n0\n2\n0\n1\n3\n2\n',
    'racedet_demo': '2\nfalse\ntrue\nfalse\ntrue\nfalse\n8\n',
    'loom_demo': '2\n0\n5\ntrue\nfalse\n1\n4\n2\n0\n5\n',
    'select_demo': '2\na\n10\n1\nc\n30\n0\n\nfalse\n-1\n',
    'sampleprof_demo': '10\nparse\n5\n3\n50\n20\n3\n0\n',
    'heapdump_demo': '480\n4\n256\ntrue\ntrue\nfalse\n256\n1\n',
    'revdbg_demo': '3\nx\n3\n2\ny\n10\n1\nx\n2\n2\ny\n10\n0\nx\n1\n4\n10\nx\n',
    'crashrep_demo': '3\nrender\nparse\n???\ntrue\nSIGSEGV\nfalse\n',
    'repldbg_demo': '10\nfalse\n15\n40\n0\n-1\n2\n3\n',
    'publish_demo': '4\n2\npublished\nrejected\nabsent\nretracted\n1\ntrue\nfalse\nfalse\n',
    'devshell_demo': '3\n2\ntrue\nfalse\ngcc\n\n1291821686\n1291821686\ntrue\nfalse\n',
    'stdlibfuzz_demo': '18\n0\n9\ntrue\nfalse\n-42\ntrue\ntrue\nfalse\n',
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
    print("daily-ten 21 Nov 2026 — library sprint batch 13 (20 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
