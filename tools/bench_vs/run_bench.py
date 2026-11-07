#!/usr/bin/env python3
"""Cross-language benchmarks: Qasida vs Python vs Go vs Rust vs C.

Same algorithm in every language, same inputs, self-timed programs.
Each program prints `us = <microseconds>` and a result; this runner
builds everything, runs each 3x, reports the MEDIAN time, and checks
that all languages agree on the result (a benchmark that computes
different answers is not a benchmark).

Run from the repo root: python3 tools/bench_vs/run_bench.py
Optional env: GO_BIN, RUSTC_BIN (defaults: go, rustc on PATH, else
/tmp/go/bin/go and /tmp/cargo/bin/rustc from a local install).
Languages whose compiler is missing are skipped, not faked.
"""
import os
import re
import shutil
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TASKS = ["fib", "array_sum", "matmul"]
EXPECTED = {
    "fib": "9227465",
    "array_sum": "3218943598110137",
    # matmul checksum: every entry is 128 * 1.0 * 2.0 = 256, 16384 entries
    "matmul": "4194304",
}


def find_tool(env_name, names, extra):
    v = os.environ.get(env_name)
    if v and os.path.exists(v):
        return v
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for p in extra:
        if os.path.exists(p):
            return p
    return None


def build(lang, task, workdir):
    src = os.path.join(HERE, f"{task}.{lang if lang != 'qasida' else 'fg'}")
    out = os.path.join(workdir, f"{task}_{lang}")
    if lang == "qasida":
        r = subprocess.run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                            src, "-o", out], capture_output=True, text=True, cwd=ROOT)
    elif lang == "py":
        return ["python3", src]
    elif lang == "go":
        go = find_tool("GO_BIN", ["go"], ["/tmp/go/bin/go"])
        if not go:
            return None
        r = subprocess.run([go, "build", "-o", out, src], capture_output=True, text=True)
    elif lang == "rs":
        rustc = find_tool("RUSTC_BIN", ["rustc"],
                          ["/tmp/cargo/bin/rustc", os.path.expanduser("~/cargo/bin/rustc")])
        if not rustc:
            return None
        r = subprocess.run([rustc, "-O", "-o", out, src], capture_output=True, text=True)
    elif lang == "c":
        r = subprocess.run(["cc", "-O2", "-o", out, src], capture_output=True, text=True)
    else:
        return None
    if r.returncode != 0:
        print(f"  BUILD FAILED {lang}/{task}:\n{r.stderr[-500:]}")
        return None
    return [out]


def run_once(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    m = re.search(r"us = (\d+)", r.stdout)
    result = None
    mm = re.search(r"=\s*([-\d.eE+]+)\s+us", r.stdout)
    if mm:
        result = mm.group(1)
    return (int(m.group(1)) if m else None, result, r.stdout.strip())


def main():
    workdir = "/tmp/bench_vs_bin"
    os.makedirs(workdir, exist_ok=True)
    langs = ["qasida", "py", "go", "rs", "c"]
    print("task, language, median_us, result")
    for task in TASKS:
        for lang in langs:
            cmd = build(lang, task, workdir)
            if cmd is None:
                print(f"{task}, {lang}, SKIPPED (compiler missing or build failed), -")
                continue
            times, results = [], []
            for _ in range(3):
                us, res, _out = run_once(cmd)
                if us is None:
                    print(f"{task}, {lang}, RUN FAILED, -")
                    break
                times.append(us)
                results.append(res)
            else:
                med = int(statistics.median(times))
                res = results[0]
                ok = ""
                if res is not None and task in EXPECTED:
                    want = EXPECTED[task]
                    # matmul checksum prints as float; compare numerically
                    try:
                        # Relative tolerance: Qasida prints floats at 6
                        # significant digits (%g), so its displayed value is
                        # rounded (4.1943e+06 for 4194304). The check is that
                        # the computation agrees, not the display.
                        rel = abs(float(res) - float(want)) / max(1.0, abs(float(want)))
                        ok = " OK" if rel < 1e-4 else f" MISMATCH (want {want})"
                    except ValueError:
                        ok = "" if res == want else f" MISMATCH (want {want})"
                print(f"{task}, {lang}, {med}, {res}{ok}")


if __name__ == "__main__":
    main()
