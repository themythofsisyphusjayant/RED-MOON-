#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 7 (20 items).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-derived
BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch7/replica_20261121g.py),
including iterator walks, FSM steps, scheduler picks and the
seeded lottery, ELF header fields, IPv6 parse/expand/compress,
CRC32 file-format records, cancellation, semaphore permits,
wait-for-graph cycle detection, backpressure policies, timer
wheel firing, parameterized-test counting, spy calls, flaky
history, contract checks, dependency audit, license policy,
task ordering, feature flags and lint counts.

flaky_demo writes /tmp/flaky_demo_g.txt with write_file
(overwrite, so repeated runs are deterministic). Every other
demo runs with stdin as /dev/null so no demo can block.

Usage:
  python3 tests/test_daily_20261121g.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE_PY = os.environ.get(
    "FORGE_PY", os.path.expanduser("~/workspace/forge-v2/forge.py"))
FORGE = [sys.executable, FORGE_PY]
FAILURES = []

EXPECTED = {'iter_demo': 'true\n3\n1\n14\n3\n1\n4\n5\n4\nfalse\n',
 'fsm_demo': '0\n1\n2\n0\ntrue\nfalse\n0\n',
 'schedpol_demo': '2\n3\n1\n-1\n-1\n',
 'elf_demo': 'true\n2\n1\n2\n243\n65536\nfalse\n',
 'ipv6_demo': '8193\n'
              '3512\n'
              '1\n'
              '2001:0db8:0000:0000:0000:0000:0000:0001\n'
              '2001:db8::1\n'
              'true\n'
              'false\n'
              'false\n',
 'fmtcrc_demo': '5:hello:907060870\n5:world:980881731\ntrue\nhello\nworld\nfalse\n',
 'cancel_demo': 'false\ntrue\n5\n0\n10\n0\n',
 'sema_demo': '2\ntrue\n1\ntrue\n0\nfalse\n0\n1\n2\n',
 'deadlock_demo': '3\ntrue\n2\nfalse\n1\ntrue\n',
 'bpstrat_demo': 'true\ntrue\n2\nfalse\n2\n1\ntrue\n2\n2\ntrue\n1\n4\n',
 'timerwheel_demo': '1\n1\n2\n2\n2\n3\n0\n',
 'paramtest_demo': '2\n1\nneg\n3\n0\n',
 'doubles_demo': '3\ntrue\nfalse\n2\ny\n',
 'flaky_demo': '5\ntrue\nfalse\nfalse\n1\na\n',
 'contract_demo': 'true\n0\nfalse\n1\nname\nfalse\n',
 'depcheck_demo': '1\nzlib\n1.3.0\n0\n',
 'license_demo': '2\nb\nd\ntrue\nfalse\n',
 'tasks_demo': 'test\nlint\nbuild\ndeploy\nbuild\nlint\n',
 'flags_demo': 'true\nfalse\nfalse\n1\ndark\n',
 'lint_demo': '2\n1\n1\n1\n'}

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
    print("daily-ten 21 Nov 2026 — library sprint batch 7 (20 items x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
