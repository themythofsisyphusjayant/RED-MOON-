"""Top-500 #37: pool allocators v1 (tests/test_pool_v1.py).
Fixed-size object pools for drivers, pure Qasida in
forge_lang/stdlib/pool.fg: a pool serves one fixed object size
(an int slot in v1), never grows, alloc is O(1) via a separate
free stack, and out-of-memory is a value (-1). Unlike #22's
intrusive freelist, a freed slot's value is never clobbered by a
next-pointer, and an occupancy bitmap makes double-free and
use-after-free detectable: pool_free / pool_set / pool_get on a
free or out-of-range slot return false and leave the pool
unchanged. Freed slots are zeroed, so reuse never leaks the old
value. Native-only in v1: big32 and WASM reject tuple programs.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

IMP = 'import "pool.fg";\n'

DEMO_EXPECTED = ("4\n4\n0\n1\n2\n3\ntrue\ntrue\n100\nfalse\n3\ntrue\n-1\n"
                 "true\nfalse\nfalse\n1\n0\n0\n4\n0\n")

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("alloc order 0,1,2 then -1 when full",
     IMP + "fn main() {\n  let mut p: Pool = pool_new(3);\n"
     "  let a = pool_alloc(p); println(a.0); p = a.1;\n"
     "  let b = pool_alloc(p); println(b.0); p = b.1;\n"
     "  let c = pool_alloc(p); println(c.0); p = c.1;\n"
     "  let d = pool_alloc(p); println(d.0); p = d.1;\n"
     "  println(pool_used(p));\n  println(pool_full(p));\n}\n",
     "0\n1\n2\n-1\n3\ntrue\n"),
    ("set/get round-trip; get on a free slot is false",
     IMP + "fn main() {\n  let mut p: Pool = pool_new(2);\n"
     "  let a = pool_alloc(p); p = a.1;\n"
     "  let s = pool_set(p, a.0, 55); println(s.0); p = s.1;\n"
     "  let g = pool_get(p, a.0); println(g.0); println(g.1);\n"
     "  let h = pool_get(p, 1); println(h.0); println(h.1);\n}\n",
     "true\ntrue\n55\nfalse\n0\n"),
    ("double-free is false and the pool is unchanged",
     IMP + "fn main() {\n  let mut p: Pool = pool_new(2);\n"
     "  let a = pool_alloc(p); p = a.1;\n"
     "  let b = pool_alloc(p); p = b.1;\n"
     "  let f1 = pool_free(p, a.0); println(f1.0); p = f1.1;\n"
     "  let f2 = pool_free(p, a.0); println(f2.0); p = f2.1;\n"
     "  let r = pool_alloc(p); println(r.0); p = r.1;\n"
     "  println(pool_used(p));\n}\n",
     "true\nfalse\n0\n2\n"),
    ("free is LIFO: last freed is first reused",
     IMP + "fn main() {\n  let mut p: Pool = pool_new(3);\n"
     "  let a = pool_alloc(p); p = a.1;\n"
     "  let b = pool_alloc(p); p = b.1;\n"
     "  let c = pool_alloc(p); p = c.1;\n"
     "  let f1 = pool_free(p, a.0); p = f1.1;\n"
     "  let f2 = pool_free(p, c.0); p = f2.1;\n"
     "  let r1 = pool_alloc(p); println(r1.0); p = r1.1;\n"
     "  let r2 = pool_alloc(p); println(r2.0); p = r2.1;\n}\n",
     "2\n0\n"),
    ("reset restores all slots and zeroes values",
     IMP + "fn main() {\n  let mut p: Pool = pool_new(2);\n"
     "  let a = pool_alloc(p); p = a.1;\n"
     "  let s = pool_set(p, a.0, 77); p = s.1;\n"
     "  let b = pool_alloc(p); p = b.1;\n"
     "  p = pool_reset(p);\n"
     "  println(pool_used(p));\n  println(pool_free_count(p));\n"
     "  let r = pool_alloc(p); println(r.0); p = r.1;\n"
     "  let g = pool_get(p, r.0); println(g.0); println(g.1);\n}\n",
     "0\n2\n0\ntrue\n0\n"),
    ("cap 0 and negative cap: empty pool, alloc is -1",
     IMP + "fn main() {\n  let mut p: Pool = pool_new(0);\n"
     "  println(pool_cap(p));\n  println(pool_used(p));\n"
     "  println(pool_free_count(p));\n  println(pool_full(p));\n"
     "  let a = pool_alloc(p); println(a.0); p = a.1;\n"
     "  let mut q: Pool = pool_new(-3);\n"
     "  println(pool_cap(q));\n"
     "  let b = pool_alloc(q); println(b.0); q = b.1;\n}\n",
     "0\n0\n0\ntrue\n-1\n0\n-1\n"),
    ("cap 1 pool: alloc, full, free, alloc again",
     IMP + "fn main() {\n  let mut p: Pool = pool_new(1);\n"
     "  let a = pool_alloc(p); println(a.0); p = a.1;\n"
     "  let b = pool_alloc(p); println(b.0); p = b.1;\n"
     "  let f = pool_free(p, a.0); println(f.0); p = f.1;\n"
     "  let c = pool_alloc(p); println(c.0); p = c.1;\n}\n",
     "0\n-1\ntrue\n0\n"),
    ("bad slots rejected, pool unchanged",
     IMP + "fn main() {\n  let mut p: Pool = pool_new(2);\n"
     "  let f1 = pool_free(p, -1); println(f1.0); p = f1.1;\n"
     "  let f2 = pool_free(p, 2); println(f2.0); p = f2.1;\n"
     "  let f3 = pool_free(p, 99); println(f3.0); p = f3.1;\n"
     "  let s1 = pool_set(p, -1, 1); println(s1.0); p = s1.1;\n"
     "  let s2 = pool_set(p, 2, 1); println(s2.0); p = s2.1;\n"
     "  let g1 = pool_get(p, -1); println(g1.0);\n"
     "  let g2 = pool_get(p, 2); println(g2.0);\n"
     "  let a = pool_alloc(p); println(a.0); p = a.1;\n}\n",
     "false\nfalse\nfalse\nfalse\nfalse\nfalse\nfalse\n0\n"),
    ("free does not disturb neighbouring slots",
     IMP + "fn main() {\n  let mut p: Pool = pool_new(3);\n"
     "  let a = pool_alloc(p); p = a.1;\n"
     "  let b = pool_alloc(p); p = b.1;\n"
     "  let c = pool_alloc(p); p = c.1;\n"
     "  let s1 = pool_set(p, a.0, 10); p = s1.1;\n"
     "  let s2 = pool_set(p, c.0, 30); p = s2.1;\n"
     "  let f = pool_free(p, b.0); println(f.0); p = f.1;\n"
     "  let g0 = pool_get(p, a.0); println(g0.0); println(g0.1);\n"
     "  let g2 = pool_get(p, c.0); println(g2.0); println(g2.1);\n"
     "  let g1 = pool_get(p, b.0); println(g1.0); println(g1.1);\n}\n",
     "true\ntrue\n10\ntrue\n30\nfalse\n0\n"),
    ("set on a free slot is false until it is allocated",
     IMP + "fn main() {\n  let mut p: Pool = pool_new(2);\n"
     "  let a = pool_alloc(p); p = a.1;\n"
     "  let s1 = pool_set(p, 1, 5); println(s1.0); p = s1.1;\n"
     "  let g1 = pool_get(p, 1); println(g1.0); println(g1.1);\n"
     "  let b = pool_alloc(p); println(b.0); p = b.1;\n"
     "  let s2 = pool_set(p, 1, 5); println(s2.0); p = s2.1;\n"
     "  let g2 = pool_get(p, 1); println(g2.0); println(g2.1);\n}\n",
     "false\nfalse\n0\n1\ntrue\ntrue\n5\n"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "pool_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("pool demo", r.returncode == 0 and r.stdout == DEMO_EXPECTED,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("pool demo")
    for name, prog, expected in OK_CASES:
        with tempfile.NamedTemporaryFile("w", suffix=".fg", delete=False,
                                        dir=ROOT) as f:
            f.write(prog)
            path = f.name
        try:
            r = run([sys.executable, os.path.join(ROOT, "forge.py"),
                     "run", path], ROOT)
            ok = r.returncode == 0 and r.stdout == expected
            if not check(name, ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:200]!r})"):
                failures.append(name)
        finally:
            os.unlink(path)
    # fmt idempotent on both new files.
    for rel in ("forge_lang/stdlib/pool.fg", "examples/pool_demo.fg"):
        p = os.path.join(ROOT, rel)
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"),
                  "fmt", p], ROOT)
        if not check(f"fmt runs ({rel})", rf.returncode == 0,
                     rf.stderr.strip()):
            failures.append(f"fmt runs ({rel})")
            continue
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                   "fmt", "--check", p], ROOT)
        if not check(f"fmt idempotent ({rel})", rf2.returncode == 0,
                     rf2.stderr.strip()):
            failures.append(f"fmt idempotent ({rel})")
    # big32 and WASM reject pool programs: tuples are not supported.
    for target in ("big32", "wasm"):
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "--target", target, demo], ROOT)
        ok = r.returncode != 0 and "tuples are not supported" in (
            r.stderr + r.stdout)
        if not check(f"{target} rejects pool demo", ok,
                     f"(rc={r.returncode} err={r.stderr[:200]!r})"):
            failures.append(f"{target} gate")
    # ASan: the demo runs clean.
    with tempfile.TemporaryDirectory() as td:
        c_path = os.path.join(td, "pool.c")
        bin_path = os.path.join(td, "pool_asan")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit",
                 demo], ROOT)
        with open(c_path, "w") as f:
            f.write(r.stdout)
        cc = run(["cc", "-g", "-fsanitize=address", "-o", bin_path, c_path,
                  "-lssl", "-lcrypto", "-lm"], ROOT)
        if cc.returncode != 0:
            check("ASan build", False, f"(cc err={cc.stderr[:300]!r})")
            failures.append("ASan build")
        else:
            r = run([bin_path], ROOT)
            ok = r.returncode == 0 and r.stdout == DEMO_EXPECTED
            if not check("ASan run clean", ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:300]!r})"):
                failures.append("ASan run")
    if failures:
        print(f"FAILURES: {len(failures)}: {failures}")
        return 1
    print(f"ALL PASS ({1 + len(OK_CASES) + 4 + 2 + 1} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
