#!/usr/bin/env python3
"""Cost-of-safety benchmarks: Qasida safe mode vs fast mode.

Same program, same inputs, self-timed (clock_micros), 3 runs, median.
Two comparisons per task:
  shipped: `forge.py build` (safe: -O2, checks on) vs
           `forge.py build --mode fast` (fast: -O3 -march=native,
           checks off). This is what a user actually pays, but it
           mixes check removal with optimizer differences.
  matched: C emitted in safe mode and in fast mode, both compiled
           with identical flags (-O2, no -march=native). The ONLY
           difference is the emitted checks, so this ratio is the
           pure cost of safety.
Safe and fast results must agree (exact for ints, rel < 1e-4 for
floats); a benchmark that computes different answers is not a
benchmark.

Tasks and what they stress in safe mode:
  fib           int overflow checks only (no indexing)
  array_sum     array bounds + int overflow + modulo checks
  matmul        array bounds checks (float arithmetic unchecked)
  str_index     string bounds checks
  nested_matmul double (nested) bounds checks
  float_loop    control: loop-counter int checks only

Run from the repo root: python3 tools/bench_vs/run_safety_bench.py
"""
import os
import re
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
WORKDIR = "/tmp/bench_safety_bin"
TASKS = ["fib", "array_sum", "matmul", "str_index", "nested_matmul", "float_loop"]
FLOAT_TASKS = {"matmul", "nested_matmul", "float_loop"}


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=300)


def build_shipped(task, mode):
    out = os.path.join(WORKDIR, f"{task}_{mode}")
    args = [sys.executable, os.path.join(ROOT, "forge.py"), "build",
            os.path.join(HERE, f"{task}.fg"), "-o", out]
    if mode == "fast":
        args += ["--mode", "fast"]
    r = run(args)
    if r.returncode != 0:
        print(f"  BUILD FAILED shipped/{mode}/{task}:\n{r.stderr[-500:]}")
        return None
    return [out]


def build_matched(task, mode):
    c_path = os.path.join(WORKDIR, f"{task}_{mode}.c")
    out = os.path.join(WORKDIR, f"{task}_{mode}_m")
    args = [sys.executable, os.path.join(ROOT, "forge.py"), "build",
            os.path.join(HERE, f"{task}.fg"), "-o", out + ".bin",
            "--keep-c", c_path]
    if mode == "fast":
        args += ["--mode", "fast"]
    r = run(args)
    if r.returncode != 0:
        print(f"  BUILD FAILED emit/{mode}/{task}:\n{r.stderr[-500:]}")
        return None
    r = subprocess.run(["cc", "-O2", "-std=gnu11", "-pthread", "-o", out,
                        c_path, "-lm", "-lssl", "-lcrypto"],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"  BUILD FAILED cc/{mode}/{task}:\n{r.stderr[-500:]}")
        return None
    return [out]


def run_once(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    m = re.search(r"us = (\d+)", r.stdout)
    mm = re.search(r"=\s*([-.\d.eE+]+)\s+us", r.stdout)
    return (int(m.group(1)) if m else None,
            mm.group(1) if mm else None)


def median_of(cmd):
    times, results = [], []
    for _ in range(3):
        us, res = run_once(cmd)
        if us is None:
            return None, None
        times.append(us)
        results.append(res)
    return int(statistics.median(times)), results[0]


def agree(a, b, task):
    if a is None or b is None:
        return ""
    if task in FLOAT_TASKS:
        try:
            rel = abs(float(a) - float(b)) / max(1.0, abs(float(a)))
            return " OK" if rel < 1e-4 else f" MISMATCH ({a} vs {b})"
        except ValueError:
            return ""
    return " OK" if a == b else f" MISMATCH ({a} vs {b})"


def main():
    os.makedirs(WORKDIR, exist_ok=True)
    print("task, shipped_safe_us, shipped_fast_us, shipped_ratio, "
          "matched_safe_us, matched_fast_us, pure_ratio, result_check")
    for task in TASKS:
        row = {}
        for mode in ("safe", "fast"):
            cmd = build_shipped(task, mode)
            row[f"shipped_{mode}"] = median_of(cmd) if cmd else (None, None)
            cmd = build_matched(task, mode)
            row[f"matched_{mode}"] = median_of(cmd) if cmd else (None, None)
        ss, _ = row["shipped_safe"]
        sf, _ = row["shipped_fast"]
        ms, _ = row["matched_safe"]
        mf, _ = row["matched_fast"]
        sr = f"{ss / sf:.2f}" if ss and sf else "-"
        pr = f"{ms / mf:.2f}" if ms and mf else "-"
        ok = agree(row["shipped_safe"][1], row["shipped_fast"][1], task)
        ok2 = agree(row["matched_safe"][1], row["matched_fast"][1], task)
        check = (ok + ok2).strip() or "-"
        print(f"{task}, {ss}, {sf}, {sr}, {ms}, {mf}, {pr}, {check}")


if __name__ == "__main__":
    main()
