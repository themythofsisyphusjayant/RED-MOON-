#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 2 (20 new stdlib modules).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-computed
BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch2/replica_20261121b.py),
including the alphabet-hash map, the LCS-table unified diff, the
base-1e9 big-integer product, the float64 Adam steps in exact op
order, and the UTF-8 encode/decode round-trip.

Usage:
  python3 tests/test_daily_20261121b.py
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
    "hashmap_demo": "9\n7\n3\n-1\nfalse\n3\n2\n-1\n",
    "setops_demo": "1 2 3 4 5 6\n3 4\n1 2\n1 2 5 6\ntrue\nfalse\n3\n1\n1\n",
    "ordmap_demo": "b\na\nc\n10\n3\na\nc\n-1\n",
    "persist_demo": "1\n2\n3\n30\ntrue\n3\n30\n1\n2\n-1\n2\n",
    "ringbuf_demo": "true\nfalse\n1\ntrue\n2\n3\n4\nfalse\n-1\n0\ntrue\n",
    "ndarray_demo": "6\n6\n2\n2\n20\n6\n8\n8\n",
    "strbuild_demo": "hello world=42:3.14\n19\n0\n\n",
    "caseconv_demo": "helloWorldFoo\nhello_world_foo\nhello-world\nhello_world\nhello-world\na\n",
    "utf8_demo": "72 195 169 226 130 172 240 159 152 128\n72 233 8364 128512\n2\n3\n4\n1\n4\ntrue\nfalse\n",
    "unidiff_demo": "  alpha\n- beta\n+ beta2\n  gamma\n+ epsilon\n  delta\n2\n1\n",
    "bigint_demo": ("111111111011111111100\n86419753208641975320\n"
                    "37037036703703703670\n1219326311370217952237463801111263526900\n-1\n42\n"),
    "decimal_demo": "14.8456\n9.8456\n30.8640\n4.9382\n2.5000\n1\n",
    "vecmath_demo": "32\n3.74166\n-3 6 -3\n5.19615\n0.974632\n5 7 9\n2 4 6\n",
    "errwrap_demo": "while starting server: while reading config: file not found\nfile not found\n2\nboom\n",
    "multierr_demo": "3\ntrue\nbad age\nbad age; bad name; bad email\n0\nfalse\n",
    "resultx_demo": "15\n15\n11\nfalse\nwrap: boom\n5\n",
    "valerr_demo": "3\ntrue\nfalse\nage: must be >= 0; name: required; age: must be <= 150\n2\n",
    "structpack_demo": "171 52 18 120 86 52 18\n171\n4660\n305419896\nfalse\n249 255 255 255\n-7\n",
    "optimizers_demo": "1.464\n-0.488\n0.299618\n-0.298414\n",
    "junit_demo": ("1\n1\n1\n3\n<testsuite name=\"math\" tests=\"3\" failures=\"1\" skipped=\"1\">"
                   "<testcase name=\"add\" time=\"12\"/>"
                   "<testcase name=\"sub\" time=\"5\"><failure message=\"expected 3 got 2\"/></testcase>"
                   "<testcase name=\"skipme\" time=\"0\"><skipped/></testcase></testsuite>\n"),
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
    print("daily-ten 21 Nov 2026 — library sprint batch 2 (20 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
