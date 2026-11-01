"""Regression test: nested empty array literals.

Fix-track gap: `let x: [[int]] = [[]];` failed with
"declared [[int]] but initialised with [[?]]" — the flat
`[]` carve-out did not recurse. The fix has two halves:
(1) the checker accepts value types that match the expected
type up to `[?]` holes (dynamic-array/tuple positions only,
never sized — `[[int; 2]]` still rejects); array-literal
elements unify the same way, so `[[], [1]]` works;
(2) infer fills literal types from context (let/assign/
return/struct-field/call-arg) so codegen never sees a
`[?]` hole. Bare holes still error, genuine mismatches
still error.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = (
    "fn takes(v: [[int]]) -> int {\n"
    "  return len(v);\n"
    "}\n"
    "fn main() {\n"
    "  let x: [[int]] = [[]];\n"
    "  println(len(x));\n"
    "  println(len(x[0]));\n"
    "  let y: [[int]] = [[], [1]];\n"
    "  println(len(y));\n"
    "  println(len(y[1]));\n"
    "  let z: [[int]] = [[1], []];\n"
    "  println(len(z[0]));\n"
    "  println(takes([[]]));\n"
    "  let mut w: [[int]] = [[9]];\n"
    "  w = [[]];\n"
    "  println(len(w));\n"
    "  let t: (int, [int]) = (1, []);\n"
    "  println(t.0);\n"
    "  println(len(t.1));\n"
    "}\n"
)
EXPECTED = "1\n0\n2\n1\n1\n1\n1\n1\n0\n"

SIZED_NEG = (
    "fn main() {\n"
    "  let x: [[int; 2]] = [[]];\n"
    "  println(len(x));\n"
    "}\n"
)

MISMATCH_NEG = (
    "fn main() {\n"
    "  let x = [[1], [\"a\"]];\n"
    "  println(len(x));\n"
    "}\n"
)

BARE_NEG = (
    "fn main() {\n"
    "  let x = [[]];\n"
    "  println(len(x));\n"
    "}\n"
)


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          timeout=30)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    forge = [sys.executable, os.path.join(ROOT, "forge.py")]
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "n.fg")
        with open(p, "w") as f:
            f.write(PROG)
        r = run(forge + ["run", p], ROOT)
        if not check("nested empty runs", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("nested empty runs")
        elif not check("nested empty results", r.stdout == EXPECTED,
                       repr(r.stdout)):
            failures.append("nested empty results")
        for name, prog in (("sized still rejects", SIZED_NEG),
                           ("mismatch still rejects", MISMATCH_NEG),
                           ("bare hole still rejects", BARE_NEG)):
            q = os.path.join(td, "neg.fg")
            with open(q, "w") as f:
                f.write(prog)
            rr = run(forge + ["run", q], ROOT)
            if not check(name, rr.returncode != 0,
                         (rr.stdout + rr.stderr)[-200:]):
                failures.append(name)
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
