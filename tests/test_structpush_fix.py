"""Regression test: struct-array push copy-on-write
(fix track, tests/test_structpush_fix.py).

Batch-18 gap, same missing-CoW shape as the inline
nested-array push: the scalar helpers (FORGE_ARRAY_
HELPERS) detach a shared buffer before growing it,
but the per-struct forge_<T>_push helper realloced
the shared buffer in place. The other holders
dangled on the freed pointer, and the two-sided
program below double-freed in realloc (ASan) while
a[2].x read 9 where 4 was expected.

The fix detaches first, mirroring the scalar
helpers: fresh buffer, copy slots gaining
ownership of their fields each (struct_own_code —
str fields deep-copied, array fields inc'd, nested
structs recursed; the struct free path frees one
hold per slot, so the inc keeps the counts exact),
drop this holder's count on the old buffer without
freeing it. Inner arrays stay shared by reference,
as elsewhere, so only the outer structure is
private after the push.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = (
    "struct P { x: int }\n"
    "fn main() {\n"
    "  let mut a: [P] = [P{x: 1}, P{x: 3}];\n"
    "  let b = a;\n"
    "  push(a, P{x: 4});\n"
    "  push(b, P{x: 9});\n"
    "  println(len(a));\n"
    "  println(len(b));\n"
    "  println(a[2].x);\n"
    "  println(b[2].x);\n"
    "  println(b[0].x);\n"
    "  println(b[1].x);\n"
    "  println(a[0].x);\n"
    "  println(a[1].x);\n"
    "}\n"
)
EXPECTED = "3\n3\n4\n9\n1\n3\n1\n3\n"

GROW_PROG = (
    "struct P { x: int }\n"
    "fn main() {\n"
    "  let mut a: [P] = [P{x: 1}, P{x: 2}];\n"
    "  let b = a;\n"
    "  push(a, P{x: 3});\n"
    "  push(a, P{x: 4});\n"
    "  push(a, P{x: 5});\n"
    "  push(a, P{x: 6});\n"
    "  push(a, P{x: 7});\n"
    "  push(a, P{x: 8});\n"
    "  println(len(a));\n"
    "  println(len(b));\n"
    "  println(a[7].x);\n"
    "  println(b[0].x);\n"
    "  println(b[1].x);\n"
    "}\n"
)
GROW_EXPECTED = "8\n2\n8\n1\n2\n"

STR_PROG = (
    "struct S { name: str, v: int }\n"
    "fn main() {\n"
    "  let mut a: [S] = [S{name: \"one\", v: 1}];\n"
    "  let b = a;\n"
    "  push(a, S{name: \"two\", v: 2});\n"
    "  println(len(b));\n"
    "  println(b[0].name);\n"
    "  println(b[0].v);\n"
    "  println(len(a));\n"
    "  println(a[1].name);\n"
    "  println(a[1].v);\n"
    "}\n"
)
STR_EXPECTED = "1\none\n1\n2\ntwo\n2\n"

ARR_PROG = (
    "struct T { xs: [int] }\n"
    "fn main() {\n"
    "  let mut a: [T] = [T{xs: [1, 2]}];\n"
    "  let b = a;\n"
    "  push(a, T{xs: [3]});\n"
    "  println(len(b));\n"
    "  println(b[0].xs[1]);\n"
    "  println(len(a));\n"
    "  println(a[1].xs[0]);\n"
    "  println(a[0].xs[0]);\n"
    "}\n"
)
ARR_EXPECTED = "1\n2\n2\n3\n1\n"

FIELD_PROG = (
    "struct P { x: int }\n"
    "struct M { ps: [P] }\n"
    "fn main() {\n"
    "  let mut m: M = M{ps: [P{x: 1}, P{x: 2}]};\n"
    "  let n = m;\n"
    "  push(m.ps, P{x: 3});\n"
    "  println(len(m.ps));\n"
    "  println(len(n.ps));\n"
    "  println(m.ps[2].x);\n"
    "  println(n.ps[0].x);\n"
    "  println(n.ps[1].x);\n"
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
        ("struct with str field", STR_PROG, STR_EXPECTED),
        ("struct with array field", ARR_PROG, ARR_EXPECTED),
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
    demo = os.path.join(ROOT, "examples", "structpush_demo.fg")
    rf = run([sys.executable, os.path.join(ROOT, "forge.py"),
              "fmt", "--check", demo], ROOT)
    if not check("demo fmt idempotent", rf.returncode == 0, rf.stderr.strip()):
        failures.append("demo fmt idempotent")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
