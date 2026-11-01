"""Regression test: inline nested-array push realloc (fix track).

Batch-18 gap: push on a shared scalar array copies-on-write, but
the INLINE nested-array push path (pushing an array value into an
array of arrays, emitted inline in codegen because the element
type varies) realloced the shared buffer in place. The other
holders dangled on the freed pointer, and scope exit double-freed
(reproduced before the fix: "free(): double free detected in
tcache 2", exit 250, on the two-sided program below).

The fix detaches first, mirroring FORGE_ARRAY_HELPERS: fresh
buffer, copy slots gaining an inner reference each (the nested
free path decrements one per slot, so the inc keeps the counts
exact), drop this holder's count on the old buffer without
freeing it. Inner arrays stay shared by reference, as elsewhere
(struct_own_code gains refs, it does not deep-copy), so only the
outer structure is private after the push.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = (
    "fn main() {\n"
    "  let mut a: [[int]] = [[1, 2], [3]];\n"
    "  let b = a;\n"
    "  push(a, [4, 5]);\n"
    "  push(b, [9]);\n"
    "  println(len(a));\n"
    "  println(len(b));\n"
    "  println(a[2][0]);\n"
    "  println(b[2][0]);\n"
    "  println(b[0][0]);\n"
    "  println(b[1][0]);\n"
    "  println(a[0][0]);\n"
    "  println(a[1][0]);\n"
    "}\n"
)
EXPECTED = "3\n3\n4\n9\n1\n3\n1\n3\n"

GROW_PROG = (
    "fn main() {\n"
    "  let mut a: [[int]] = [[1], [2]];\n"
    "  let b = a;\n"
    "  push(a, [3]);\n"
    "  push(a, [4]);\n"
    "  push(a, [5]);\n"
    "  push(a, [6]);\n"
    "  push(a, [7]);\n"
    "  push(a, [8]);\n"
    "  println(len(a));\n"
    "  println(len(b));\n"
    "  println(a[7][0]);\n"
    "  println(b[0][0]);\n"
    "  println(b[1][0]);\n"
    "}\n"
)
GROW_EXPECTED = "8\n2\n8\n1\n2\n"

TRIPLE_PROG = (
    "fn main() {\n"
    "  let mut a: [[[int]]] = [[[1, 2]], [[3]]];\n"
    "  let b = a;\n"
    "  push(a, [[4]]);\n"
    "  println(len(a));\n"
    "  println(len(b));\n"
    "  println(a[2][0][0]);\n"
    "  println(b[0][0][0]);\n"
    "  println(b[1][0][0]);\n"
    "}\n"
)
TRIPLE_EXPECTED = "3\n2\n4\n1\n3\n"

FIELD_PROG = (
    "struct M { rows: [[int]]; }\n"
    "fn main() {\n"
    "  let mut m: M = M { rows: [[1], [2]] };\n"
    "  let n = m;\n"
    "  push(m.rows, [3]);\n"
    "  println(len(m.rows));\n"
    "  println(len(n.rows));\n"
    "  println(m.rows[2][0]);\n"
    "  println(n.rows[0][0]);\n"
    "  println(n.rows[1][0]);\n"
    "}\n"
)
FIELD_EXPECTED = "3\n2\n3\n1\n2\n"


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          timeout=60)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    forge = [sys.executable, os.path.join(ROOT, "forge.py")]
    cases = [
        ("two-sided shared push", PROG, EXPECTED),
        ("growth loop past two reallocs", GROW_PROG, GROW_EXPECTED),
        ("triple-nested shared push", TRIPLE_PROG, TRIPLE_EXPECTED),
        ("field-target shared push", FIELD_PROG, FIELD_EXPECTED),
    ]
    with tempfile.TemporaryDirectory() as td:
        for name, prog, expected in cases:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            r = run(forge + ["run", p], ROOT)
            detail = repr(r.stdout)
            if r.stderr:
                detail += " " + r.stderr.strip().splitlines()[-1]
            if not check(name, r.returncode == 0 and r.stdout == expected,
                         detail):
                failures.append(name)
        fmt = os.path.join(td, "f.fg")
        with open(fmt, "w") as f:
            f.write(PROG)
        rf = run(forge + ["fmt", fmt], ROOT)
        if not check("fmt runs", rf.returncode == 0, rf.stderr.strip()):
            failures.append("fmt runs")
        else:
            rf2 = run(forge + ["fmt", "--check", fmt], ROOT)
            if not check("fmt idempotent", rf2.returncode == 0,
                         rf2.stderr.strip()):
                failures.append("fmt idempotent")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
