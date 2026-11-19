#!/usr/bin/env python3
"""Daily-ten 19 Nov 2026 — library track (10 new stdlib modules).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-computed
BEFORE the first run (independent Python replica;
 /tmp/replica_20261119.py), including the float32 sigmoid /
 scaling values, the zlib stored-block bytes (asserted byte-exact
 against Python zlib.compress(level=0)), and the PNG round-trip
 (encode via png.fg, decode via pngdec.fg, Adler-32 verified).

Usage:
  python3 tests/test_daily_20261119.py
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
    "sentencepiece_demo": ("2\n_hello\n_world\nhello world\n2\n_play\ning\n"
                           "playing\n2\n_un\nknown\nunknown\n2\n_test\ns\n"
                           "tests\n"),
    "sklearnv2_demo": ("3.5 0\n3 1.41421\n-1.41421 -0.707107 0 0.707107 "
                       "1.41421\n0 1\n7 3\n"),
    "beamsearch_demo": "1 1 0\n-0.7\n0 0 0\n-3.7\n",
    "zlib_demo": ("120\n1\n1\n5\n0\n250\n255\n104\n101\n108\n108\n111\n6\n"
                  "44\n2\n21\n1\n103547413\n"),
    "pngdec_demo": "1\n1\n200\n100\n50\n1\n0\n",
    "framesext_demo": "40 60 50\n3\n150\n",
    "docgenhtml_demo": ("<h1>add</h1>\n<pre>add(a: int, b: int) -> int</pre>\n"
                        "<p>Adds two numbers.</p>\n"
                        "<li><code>add(a: int, b: int) -> int</code></li>\n"
                        "<html>\n<head><title>API</title></head>\n<body>\n"
                        "<h1>add</h1>\n<pre>add(a: int, b: int) -> int</pre>\n"
                        "<p>Adds two numbers.</p>\n</body>\n</html>\n"),
    "quantv2_demo": "0.00787402\n0 64 -64 127 -127\n0.503937\n1 1 1 2\n",
    "autogradextv2_demo": ("0 4\n1\n0.393224\n2.5 2.5 2.5\n0.5 0.5 0.5 0.5\n"
                           "17 23 39 53\n"),
    "visionv2_demo": ("10 10 20 20 10 10 20 20 30 30 40 40 30 30 40 40\n"
                      "4 1 5 2 6 3\n85 85 85 150\n0 0.498039 1\n"),
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
    print("daily-ten 19 Nov 2026 — library track (10 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
