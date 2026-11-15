"""Trig builtins sin/cos/tan (quant/trig/DESIGN.md).

Lowering is direct libm (sin/cos/tan from math.h, native link
already -lm), following the sqrt/exp/log shape exactly: one float
argument, float result, one-message checker error otherwise.
Gating follows the same precedent per backend: freestanding
rejects at check time, big32 rejects at codegen, WASM rejects
with the generic unsupported-call error (no code change there).
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = ("sin(0) = 0\nsin(pi/6) = 0.5\nsin(pi/4) = 0.707107\n"
            "sin(pi/2) = 1\nsin(-pi/2) = -1\ncos(0) = 1\ncos(pi/3) = 0.5\n"
            "cos(pi/4) = 0.707107\ncos(pi) = -1\ntan(0) = 0\n"
            "tan(pi/4) = 1\ntan(-pi/4) = -1\nsin^2+cos^2 = 1\n")

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("sin known values",
     "fn main() {\n"
     "  let pi: float = 3.141592653589793;\n"
     "  println(sin(0.0));\n"
     "  println(sin(pi / 6.0));\n"
     "  println(sin(pi / 2.0));\n"
     "  println(sin(0.0 - pi / 2.0));\n"
     "}\n",
     "0\n0.5\n1\n-1\n"),
    ("cos known values",
     "fn main() {\n"
     "  let pi: float = 3.141592653589793;\n"
     "  println(cos(0.0));\n"
     "  println(cos(pi / 3.0));\n"
     "  println(cos(pi));\n"
     "}\n",
     "1\n0.5\n-1\n"),
    ("tan known values",
     "fn main() {\n"
     "  let pi: float = 3.141592653589793;\n"
     "  println(tan(0.0));\n"
     "  println(tan(pi / 4.0));\n"
     "  println(tan(0.0 - pi / 4.0));\n"
     "  println(tan(pi / 3.0));\n"
     "}\n",
     "0\n1\n-1\n1.73205\n"),
    ("pythagorean identity",
     "fn main() {\n"
     "  let pi: float = 3.141592653589793;\n"
     "  let a: float = pi / 5.0;\n"
     "  println(sin(a) * sin(a) + cos(a) * cos(a));\n"
     "}\n",
     "1\n"),
    ("libm-exact near-zero values",
     "fn main() {\n"
     "  let pi: float = 3.141592653589793;\n"
     "  println(sin(pi));\n"
     "  println(cos(pi / 2.0));\n"
     "}\n",
     "1.22465e-16\n6.12323e-17\n"),
]

# (name, program, error fragment) — must be rejected at check time.
REJECT_CASES = [
    ("sin int arg",
     "fn main() { let x: float = sin(1); }\n",
     "sin() takes exactly one float argument"),
    ("cos two args",
     "fn main() { let x: float = cos(1.0, 2.0); }\n",
     "cos() takes exactly one float argument"),
    ("tan str arg",
     "fn main() { let x: float = tan(\"x\"); }\n",
     "tan() takes exactly one float argument"),
    ("sin no args",
     "fn main() { let x: float = sin(); }\n",
     "sin() takes exactly one float argument"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "trig_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("trig demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("trig demo runs")
    elif not check("trig demo results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("trig demo results")
    with tempfile.TemporaryDirectory() as td:
        for name, prog, want in OK_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"),
                      "run", p], ROOT)
            ok = rr.returncode == 0 and rr.stdout == want
            if not check(f"{name} runs", ok,
                         repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
        for name, prog, frag in REJECT_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"),
                      "run", p], ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{name} rejected", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
        # Freestanding rejects trig at check time (same as sqrt).
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write("fn main() { let x: float = sin(1.0); }\n")
        rr = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "check", p, "--freestanding"], ROOT)
        ok = rr.returncode != 0 and "needs the hosted runtime" in (rr.stderr + rr.stdout)
        if not check("freestanding rejects sin", ok,
                     (rr.stderr.strip().splitlines() or [""])[-1]):
            failures.append("freestanding rejects sin")
        # big32 and WASM reject trig (same shape as sqrt).
        wasm_prog = ("fn f() -> float { return sin(1.0); }\n"
                     "fn main() -> int { let x: float = f(); return 0; }\n")
        with open(p, "w") as f:
            f.write(wasm_prog)
        for cmd, frag in (("emit-big32", "builtin sin() is not supported on big32 (v1)"),
                          ("emit-wasm", "wasm: call to 'sin' is not supported in v1")):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), cmd, p],
                     ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{cmd} rejects sin", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(cmd)
    rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", demo],
             ROOT)
    if not check("fmt runs", rf.returncode == 0, rf.stderr.strip()):
        failures.append("fmt runs")
    else:
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                   "fmt", "--check", demo], ROOT)
        if not check("fmt idempotent", rf2.returncode == 0, rf2.stderr.strip()):
            failures.append("fmt idempotent")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
