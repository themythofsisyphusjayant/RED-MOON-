"""Regression test: nested arrays as struct fields.

Fix-track gap: a struct field of type `[[int]]` (or
`[Point]`) failed in C with "unknown type name
'ForgeArray_ForgeIntArray'". Collection was fine —
collect_nested_array_types already walks struct fields —
but ORDER was wrong: struct bodies hold array fields BY
VALUE, so their typedefs must precede the body, and the
old order emitted them after the bodies (the comment
claiming "arrays hold pointers, so they never force an
order" is wrong for array-typed fields). The fix emits
per-struct array typedefs, then nested array typedefs
innermost-first, right after all forward declarations
and before composite bodies; only the typedef lines
moved, the per-struct helpers still follow the bodies.
Residual, documented: enum payload structs with
nested-array payloads still need their typedef before
the enum section, which precedes this block.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = (
    "struct Point {\n"
    "  x: int;\n"
    "  y: int;\n"
    "}\n"
    "struct S {\n"
    "  vals: [[int]];\n"
    "  pts: [Point];\n"
    "  flat: [int];\n"
    "}\n"
    "struct T {\n"
    "  s: S;\n"
    "}\n"
    "fn main() {\n"
    "  let p = Point { x: 3, y: 4 };\n"
    "  let s = S { vals: [[1, 2], [3]], pts: [p], flat: [7] };\n"
    "  println(len(s.vals));\n"
    "  println(len(s.vals[0]));\n"
    "  println(s.vals[1][0]);\n"
    "  println(len(s.pts));\n"
    "  println(s.pts[0].x);\n"
    "  println(s.flat[0]);\n"
    "  let t = T { s: s };\n"
    "  println(len(t.s.vals));\n"
    "}\n"
)
EXPECTED = "2\n2\n3\n1\n3\n7\n2\n"


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
        if not check("struct nested runs", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("struct nested runs")
        elif not check("struct nested results", r.stdout == EXPECTED,
                       repr(r.stdout)):
            failures.append("struct nested results")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
