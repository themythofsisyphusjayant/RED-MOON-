#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 12 (20 flips).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly: 20 demos x 2 compilers x 2 checks
= 80 checks. The 20 flips are the catalog items below (19 GAP
-> HAVE + 1 PARTIAL -> HAVE, #177 units). Expected values were
hand-derived BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch12/replica_20261121l.py)
and cross-checked programmatically against the replica output,
including cache-aware field reordering, chained comparisons,
derive registries, capability tokens, promise all/race, unit
dimensions, service discovery, mutex/rw-lock rules, atomic
CAS, pool makespans, work-stealing, actor mailboxes, LPT test
sharding, release manifests, container layers, reproducible
builds, renames, code actions, DAP sessions and watchpoints.
No demo writes files; every demo runs with stdin as /dev/null
so no demo can block.

Usage:
  python3 tests/test_daily_20261121l.py
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
    'cachelay_demo': '33\n11\n1\n22\n0\n1\nid\ncount\nflags\ntag\nok\n0\n8\n16\n20\n21\n',
    'chaincmp_demo': 'true\nfalse\ntrue\ntrue\ntrue\ntrue\ntrue\n1\n-1\ntrue\nfalse\n',
    'derive_demo': 'true\nfalse\ntrue\nDebug\nClone\nPartialEq\n2\n2\n',
    'cap_demo': '1000\n1001\ntrue\nfalse\nfalse\nfalse\nuart0\n\n2\ntrue\nfalse\nfalse\n',
    'promise_demo': 'ready\n35\npending\n-1\nready\n20\npending\n-1\nready\n0\npending\n-1\n',
    'units_demo': 'c_to_f = 32 f_to_c = 0\nkm_to_mi = 6.21371\nkg_to_lb = 2.20462\n1\n0\n-1\n1\n1\n-2\ntrue\nfalse\ntrue\n',
    'svcdisc_demo': '10.0.0.1\n8080\n2\n1\n0\nfalse\ntrue\n10.0.0.9\n3\n',
    'mutex_demo': 'true\nalice\ntrue\nalice\ntrue\nfalse\n1\n2\nfalse\n1\n0\ntrue\ncarol\n',
    'atomic_demo': '1\n6\n6\n16\ntrue\n100\nfalse\n100\n99\n',
    'threadpool_demo': '5\n5\n15\n15\n5\n8\n8\n',
    'worksteal_demo': 'c\na\nb\n\nfalse\nd\n0\n0\n2\n',
    'actor_demo': '3\n1\ninc\n1\n2\ninc\n2\nhello\n1\ndec\n3\n0\n\n3\n',
    'testpar_demo': '40\n20\n2\n20\n20\n0\n1\n9\n',
    'relbin_demo': 'qasida-linux-x86_64.tar.gz\n47123456\ntrue\nfalse\n3\n145481408\na1b2\n',
    'container_demo': '3\n60000000\nbase\ntrue\nfalse\nsha256:bb\n',
    'repro_demo': 'false\ntrue\nfalse\n3\n2\nout-cccc\n',
    'rename_demo': '3\nfalse\ntrue\nmain.fg\n10\n1\n1\ntrue\n',
    'codeact_demo': 'remove-import\nprefix-underscore\ntrue\n2\n1\nfalse\ntrue\n2\n1\n',
    'dap_demo': '3\n3\ntrue\nfalse\n1\npaused\nrunning\n',
    'watchpt_demo': 'true\n1\nfalse\n0\ntrue\n1\nfalse\n2\n2\n',
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
    print("daily-ten 21 Nov 2026 — library sprint batch 12 (20 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
