"""Regression test: aliases inside sized-array spellings.

Batch-12 gap: expand_aliases had no sized-array branch, so
the plain "[...]" branch tried to expand "N; 3" as one name
and "[N; 3]" reached later passes unexpanded ("unknown
field type '[N; 3]'"). The fix adds a sized branch that
expands only the element part. Covers struct fields,
function signatures, and let annotations. (Nested sized
literals like [[1, 2], [3, 4]] against [[int; 2]; 2] are a
separate, still-open unification gap — not covered here.)
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = (
    "type N = int;\n"
    "struct S {\n"
    "  vals: [N; 3];\n"
    "}\n"
    "fn sum3(v: [N; 3]) -> int {\n"
    "  return v[0] + v[1] + v[2];\n"
    "}\n"
    "fn main() {\n"
    "  let s = S { vals: [1, 2, 3] };\n"
    "  println(s.vals[1]);\n"
    "  println(sum3(s.vals));\n"
    "  let a: [N; 2] = [4, 5];\n"
    "  println(a[0] + a[1]);\n"
    "}\n"
)
EXPECTED = "2\n6\n9\n"


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
        p = os.path.join(td, "s.fg")
        with open(p, "w") as f:
            f.write(PROG)
        r = run(forge + ["run", p], ROOT)
        if not check("sized alias runs", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("sized alias runs")
        elif not check("sized alias results", r.stdout == EXPECTED,
                       repr(r.stdout)):
            failures.append("sized alias results")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
