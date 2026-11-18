#!/usr/bin/env python3
"""Daily-ten 18 Nov 2026 — library track (10 new stdlib modules).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-computed
BEFORE the first run (independent Python replica;
 /tmp/replica_20261118.py), including the float32 RMSNorm /
SwiGLU / RoPE values, the gzip stored-block bytes (asserted
byte-exact against Python gzip.compress(mtime=0,
compresslevel=0)), and the tar header checksum field.

Usage:
  python3 tests/test_daily_20261118.py
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
    "translation_demo": ("bonjour\nmerci\nxyzzy\n2\n3 3\n"),
    "inferenceserver_demo": ("POST\n/predict\n4.75\n"
                             "{\"prediction\": 4.75}\n"
                             "4.75 -2.75 1.75\n"),
    "wordpiece_demo": ("2\nplay\n##ing\nplaying\n1\nhello\nhello\n"
                       "2\nun\n##known\nunknown\n"),
    "llamablock_demo": ("0.365148 0.730297 1.09545 1.46059\n1.46212\n"
                        "-0.0812685 2.23459\n1\n"),
    "gzip_demo": ("31\n139\n8\n0\n0\n0\n0\n0\n4\n3\n1\n5\n0\n250\n255\n"
                  "104\n101\n108\n108\n111\n134\n166\n16\n54\n5\n0\n0\n0\n"
                  "28\n907060870\n"),
    "parallel_demo": "3 5 7 9\n10\n2 4 6\n",
    "vision2_demo": "80\n50\n1\n5\n",
    "augmentimg_demo": ("3 2 1 6 5 4\n4 5 6 1 2 3\n2 3\n"
                        "11 12 13 14 15 16\n255 2 3 4 5 255\n"),
    "docgen_demo": ("# add\n\n`add(a: int, b: int) -> int`\n\n"
                    "Adds two numbers.\n- add(a: int, b: int) -> int\n"
                    "add: Adds two numbers.\n# greet\n\n"
                    "`greet(name: str) -> str`\n\n"
                    "Greets a person by name.\n"
                    "- greet(name: str) -> str\n"
                    "greet: Greets a person by name.\n"),
    "tardata_demo": "007304\n1\n104 101 108 108 111\n0\n1\n1\n2\n",
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
    print("daily-ten 18 Nov 2026 — library track (10 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
