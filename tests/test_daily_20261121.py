#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint day 1 (20 new stdlib modules).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-computed
BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121/replica_20261121.py),
including the float64 Nelder-Mead simplex path, the Box-Muller /
exponential draws from the rand.fg LCG, the exact-Fraction
linalg solve/inverse, the Thomas-solved cubic spline, and the
gzip CRC32/ISIZE + fixed-Huffman member cross-checked with
Python's zlib.

Usage:
  python3 tests/test_daily_20261121.py
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
    "binsearch_demo": "3\n-1\n2\n4\n6\n7\n0\n7\n2\n2\n3\n",
    "zipenum_demo": "10 1\n20 2\n30 3\n0 7\n1 8\n2 9\n",
    "groupby_demo": "5 4 3\n1 2\n1 2\n10 30 50 20 40\n0 3 5\n",
    "sparse_demo": "3\n0\n1.5 0 3 0 -2\n1.5 0 5 4 -2\n6\n",
    "windows_demo": "6 9 12\n4 6 8\n3 7 5\n7.5 10\n",
    "json2_demo": ("5\nAda\n36\n3.14\ntrue\n2\nb\n2.5\n0\n"
                   "{\"name\":\"Ada\",\"age\":36,\"pi\":3.14,\"ok\":true,"
                   "\"tags\":[\"a\",\"b\"],\"nested\":{\"x\":2.5},\"none\":null}\n"
                   "4\nx\nfalse\n[1,2.5,\"x\",false]\n"),
    "linalg_demo": ("-1\n2\n3\n-1\n4\n3\n-1\n-2\n-2\n1\n5\n4\n-1\n1\n1\n1\n"),
    "interp_demo": "0.5\n4.5\n17.5\n0\n27\n4.8\n16.8\n0.2\n3.15\n16.45\n",
    "calculus_demo": "2.75\n2.66667\n0.5\n1\n2\n3\n3.5\n",
    "fixedpoint_demo": "3.7500\n0.7500\n3.0000\n1.5000\n3\n3\n-2.2500\n-4.0000\n",
    "rounding_demo": ("3\n4\n3\n-4\n-3\n-3\n2\n4\n4\n-2\n3.14\n2.718\n0.12\n0.38\n"),
    "binio_demo": "12\ntrue\n12\n4660\n2309737967\n255\n16909060\n",
    "bincode_demo": "36\n42\n3.141\nhi\ntrue\n-7\n",
    "yaml_demo": ("qasida\n3\ntrue\nlocalhost\n8080\nsmall\n"
                  "name: qasida\nversion: 3\ndebug: true\nserver:\n"
                  "  host: localhost\n  port: 8080\ntags:\n"
                  "  - fast\n  - small\n  - typed\n8080\ntyped\n"),
    "msgpack_demo": ("42\n200\n-5\ntrue\nfalse\nhi\n"
                     "0123456789012345678901234567890123456789\n"
                     "2\n3\n19\n2\ntrue\n"),
    "htmlparse_demo": ("5\ndiv\nmain\nh1\nTitle\np\nHello\nb\nWorld\nSecond\n"
                       "1\n3\n0\n2\n2\n2\n4\n3\n1\n2\n4\n\nlead\n"),
    "gzip2_demo": ("1\n1\n1\n907060870\n5\n5\n104\n101\n108\n108\n111\n"
                   "1\n1\n1\n1\n1144563373\n24\n24\n1\n0\n"),
    "randdist_demo": ("5.82308\n6.10197\n7.55556\n1622543901\n-0.800481\n"
                      "0.0388443\n-1.17004\n926495101\n0.436505\n0.471057\n"
                      "0.704384\n1622543901\n"),
    "dist_demo": ("0.398942\n0.241971\n0.5\n0.841345\n0.158655\n0.135335\n"
                  "0.180447\n0.857123\n0.0758163\n0.985612\n"),
    "neldermead_demo": "3\n-1\n8.5752e-17\n1\n1\n0\n",
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
    print("daily-ten 21 Nov 2026 — library sprint day 1 (20 demos x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
