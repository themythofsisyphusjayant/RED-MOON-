#!/usr/bin/env python3
"""Daily-ten 12 Nov 2026 — library demos (forge run).

Ten new pure-Qasida demos under examples/*_demo.fg, each for a
stdlib module that had no demo (plus one new stdlib module,
version_info.fg, roadmap #120). Each is run with `forge.py run`
and its stdout must match the expected transcript exactly.
- dates: leap years, month lengths, days_from_civil, days_between.
- map: MapStrInt put/get/has, fallback, overwrite, key count.
- rand: deterministic LCG outputs + rand_float for fixed seeds.
- preprocess: col_stats, standardize, minmax_scale, one_hot,
  split_indices, vocab_build / vocab_encode.
- ml: dot, mean, relu, sigmoid, 2x2 matmul.
- test: check / check_eq_int / check_close / check_eq_str, all pass.
- gpt: param count 776, LCG, init_params(7) spot values.
- gpt2: block size / param count / offsets + init spot values
  (V=12, d=8, S=8, H=16, L=1).
- tgt: block size / param count / size+shape tables + init spot
  values (same tiny config).
- version_info: Qasida 2.1.0, version_code 20100, at_least
  answers, WASM/GC/freestanding/self-hosted flags.
Expectations were hand-computed before running (Python
datetime.date for the calendar values, exact integer LCG
math, float32 struct 'f' + %g for floats).
Verified 12 Nov 2026: 10/10 under the Python reference
compiler, 9/10 under the hosted compiler. tgt_demo segfaults
UNDER THE HOSTED COMPILER ITSELF (exit 139, 0 bytes emitted
on `forge.py emit`; the Python emit is 311,954 bytes of C) —
the known step-4 hosted-binary segfault on large emits, not
a demo bug; the Python-passing version is kept and the
hosted check for tgt is skipped until the hosted binary is
fixed. map_put's push(m.keys, ...) inside map.fg passes the
hosted checker (unlike the index-assignment-through-param
case from 11 Nov).
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
FAILURES = []

EXPECTED = {
    "dates_demo": ("true\nfalse\ntrue\nfalse\n29\n28\n30\n0\n10957\n"
                   "20769\n315\n9812\n"),
    "map_demo": "208001\n-1\ntrue\nfalse\n208002\n3\n",
    "rand_demo": ("1103527590\n944465040\n1250496048\n0.51387\n0.439801\n"
                  "0.78941\n0.582308\n"),
    "preprocess_demo": ("2\n3\n1\n1\n-1\n-1\n1\n1\n0\n0\n1\n1\n1\n2\n3\n4\n"
                        "0\n0\n1\n0\n2\n3\n0\n1\n4\nthe\ncat\nsat\n1\n2\n-1\n"),
    "ml_demo": ("32\n2.5\n0\n2.5\n0.5\n0.731059\n0.119203\n19\n22\n43\n50\n"),
    "test_demo": "0\n0\n0\n0\n0\n",
    "gpt_demo": ("776\n1103527590\n1282168119\n0.0970561\n0.238494\n"
                 "0.0504394\n1\n0\n"),
    "gpt2_demo": ("600\n776\n160\n760\n1103527590\n0.0970561\n0.0504394\n1\n0\n"
                  "0.333559\n"),
    "tgt_demo": ("600\n776\n96\n64\n8\n192\n8\n8\n16\n12\n8\n8\n0\n8\n24\n32\n"
                 "1103527590\n0.0194112\n0.0100879\n1\n0\n"),
    "version_info_demo": ("2\n1\n0\n2.1.0\n20100\ntrue\ntrue\nfalse\nfalse\n"
                          "true\ntrue\ntrue\ntrue\n"),
}

# Demos the hosted compiler currently handles; tgt_demo is
# excluded — hosted segfaults emitting it (see docstring).
HOSTED_OK = [n for n in EXPECTED if n != "tgt_demo"]


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_demo(name, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(FORGE + ["run", os.path.join("examples", name + ".fg")],
                          capture_output=True, text=True, cwd=ROOT, env=env)


def main():
    print("daily-ten 12 Nov 2026 library demos (forge run)")
    for name, expected in EXPECTED.items():
        r = run_demo(name, {"QASIDA_COMPILER": "python"})
        check(name + " runs (python)", r.returncode == 0, r.stderr[-200:])
        check(name + " exact output (python)", r.stdout == expected,
              repr(r.stdout))
    for name in HOSTED_OK:
        r = run_demo(name)
        check(name + " runs (hosted)", r.returncode == 0, r.stderr[-200:])
        check(name + " exact output (hosted)", r.stdout == EXPECTED[name],
              repr(r.stdout))
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
