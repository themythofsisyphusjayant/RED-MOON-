#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 3 (20 new stdlib modules).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-computed
BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch3/replica_20261121c.py),
including the glob star-backtrack matcher, the LEB128 varints,
zlib.crc32 for the checksum file, the plural rule table, and the
fixed-decimal float formatting.

Usage:
  python3 tests/test_daily_20261121c.py
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
    "fmtstr_demo": "3.14\n2.500\n-2.50\n1.00\n42\n-123\n   42\nhi...\n00x\n",
    "lines_demo": "3\nalpha\nbeta\ngamma\n2\none\ntwo\n0\ntrue\nx\nfalse\n",
    "plural_demo": "cats\nboxes\nbabies\nchildren\nleaves\nsheep\nchurches\ndays\nknives\nbuses\nwolves\ncities\n",
    "bufio_demo": "abc\ndefg\n3\nhij\n0\n\n10\nfoobar!\n3\n",
    "glob_demo": "true\nfalse\ntrue\nfalse\ntrue\nfalse\ntrue\ntrue\ntrue\nfalse\ntrue\nfalse\n",
    "config2_demo": "localhost\n9090\ntrue\n3\nnone\n",
    "logrot_demo": "0\n3\n3\na\nc\n1\nd\n2\ne\n",
    "checkread_demo": "222957957\ntrue\nhello world\n222957957\ntrue\nfalse\n222957957\n",
    "journal_demo": "3\n3\nopen\nsave\nclose\n",
    "protobuf_demo": "2\n172\n2\n300\n2\n2\n8\n42\n4\n18\n2\n104\n105\n1\n0\n1\n2\n2\n1\n",
    "sqlbuild_demo": ("SELECT id, name FROM users\n"
                      "SELECT id, name FROM users WHERE name = 'O''Brien'\n"
                      "INSERT INTO users (id, name) VALUES ('1', 'ann')\n"
                      "DELETE FROM users WHERE id = '7'\n"
                      "it''s\n"),
    "valid_demo": "true\n0\nfalse\n2\nage: out of range\nname: required\nfalse\n1\nname: required\n",
    "migrate_demo": "3\n2\n2\n3\n2\n3\n0\n3\n",
    "audit_demo": "3\n1000|alice|login|console\n3000|alice|write|config\n2\n1000|alice|login|console\n3000|alice|write|config\n1\n",
    "timeout_demo": "1500000\n300000\n0\ntrue\nfalse\n250000\ntrue\n",
    "throttle_demo": "true\nfalse\ntrue\nfalse\ntrue\nfalse\nfalse\nfalse\ntrue\n",
    "snap_demo": "true\n-1\nfalse\n1\nb\nB\nfalse\n2\n\nc\nfalse\n0\nx\ny\n",
    "faketime_demo": "1000000\n1250000\n250000\n5000000\n1000000\n",
    "lockfile_demo": ("2\n2.1.0\ntrue\nfalse\n\n3\n1.14.0\n"
                      "numpy==2.1.0 #a1b2\npandas==2.2.0 #c3d4\nscipy==1.14.0 #e5f6\n\n"),
    "trace_demo": "500\n600\n-1\n2\nparse: 500 us\nrender: 600 us\n",
}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_one(name, expected, env_extra):
    path = os.path.join(ROOT, "examples", name + ".fg")
    env = dict(os.environ)
    env.update(env_extra)
    try:
        r = subprocess.run(FORGE + ["run", path], capture_output=True,
                           text=True, cwd=ROOT, env=env, timeout=180)
    except subprocess.TimeoutExpired:
        check(f"{name} runs", False, "TIMEOUT after 180s")
        return
    check(f"{name} runs rc=0", r.returncode == 0, r.stderr[-300:])
    check(f"{name} exact stdout", r.stdout == expected,
          "" if r.stdout == expected else f"got: {r.stdout!r}")


def main():
    print("daily-ten 21 Nov 2026 — library sprint batch 3 (20 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
