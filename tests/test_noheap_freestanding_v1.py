#!/usr/bin/env python3
"""Top-500 #39: no implicit heap allocation in freestanding mode v1
(tests/test_noheap_freestanding_v1.py).

Freestanding v1 has no allocator, so the rule is enforced at
compile time, in the checker, with a named error for the first heap
value — not later in codegen or at the C compiler:

  * every expression whose type is heap-backed (str, any array
    including sized, a struct/enum/tuple carrying one) is rejected,
    naming the construct: string literal, array literal, push,
    a heap-typed variable, a call returning a heap type;
  * push() is rejected outright (it reallocates the heap buffer);
  * plain structs are stack values: a program using only int
    fields builds and runs freestanding, and the emitted C contains
    no malloc, free, or memset (the per-struct heap-array helpers
    are not emitted in freestanding mode).

Boundaries, stated honestly: declarations that merely *name* a heap
type (an unused str parameter, a struct field or enum payload of
type str, never given a value) still declare — they generate no heap
code, and any value of such a type is rejected at first use. Sized
arrays stay rejected: their literals malloc in codegen. fail() and
assert() with a string message stay rejected, as before (the message
is a string literal).
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
DEMO = os.path.join(ROOT, "examples", "noheap_demo.fg")

FAILURES = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    if cond:
        print(f"  PASS {name}")
        return True
    print(f"  FAIL {name} {detail}")
    FAILURES.append(name)
    return False


def run(args, cwd=None):
    return subprocess.run(args, capture_output=True, text=True,
                          timeout=120, cwd=cwd or ROOT)


def write_prog(d, prog, name="prog.fg"):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(prog)
    return path


def reject(name, prog, *needles):
    d = tempfile.mkdtemp(prefix="noheap-reject-")
    path = write_prog(d, prog)
    r = run(FORGE + ["check", path, "--freestanding"])
    out = r.stdout + r.stderr
    ok = r.returncode != 0 and all(n in out for n in needles)
    check(f"freestanding rejects {name}", ok,
          f"rc={r.returncode} out={out[:300]!r}")


def build_run(name, prog, expected_exit, freestanding=True):
    d = tempfile.mkdtemp(prefix="noheap-allow-")
    path = write_prog(d, prog)
    out = os.path.join(d, "prog")
    args = FORGE + ["build", path, "-o", out]
    if freestanding:
        args += ["--freestanding"]
    r = run(args)
    if not check(f"{name} builds", r.returncode == 0,
                 f"err={r.stderr[:300]!r}"):
        return
    r2 = subprocess.run([out], capture_output=True, text=True, timeout=30)
    check(f"{name} exits {expected_exit}", r2.returncode == expected_exit,
          f"rc={r2.returncode} err={r2.stderr[:200]!r}")


REJECT_CASES = [
    ("string literal",
     'fn main() { let s: str = "hi"; }\n',
     "string literal allocates on the heap", "freestanding"),
    ("array literal",
     "fn main() { let a: [int] = [1, 2]; }\n",
     "array literal allocates on the heap", "freestanding"),
    ("sized array literal",
     "fn main() { let a: [int; 3] = [1, 2, 3]; }\n",
     "array literal allocates on the heap", "freestanding"),
    ("string concatenation",
     'fn f(a: str, b: str) -> str { return a + b; }\nfn main() { }\n',
     "heap-backed type 'str'", "freestanding"),
    ("push on array parameter",
     "fn f(a: [int]) { push(a, 2); }\nfn main() { }\n",
     "push() reallocates the heap buffer", "freestanding"),
    ("str variable use",
     "fn f(s: str) -> int { return len(s); }\nfn main() { }\n",
     "variable 's' has heap-backed type 'str'", "freestanding"),
    ("str-typed return of a variable",
     "fn f(s: str) -> str { return s; }\nfn main() { }\n",
     "variable 's' has heap-backed type 'str'", "freestanding"),
    ("array parameter indexed",
     "fn f(a: [int]) -> int { return a[0]; }\nfn main() { }\n",
     "variable 'a' has heap-backed type '[int]'", "freestanding"),
    ("struct value carrying a str field",
     "struct S { name: str }\nfn f(s: S) -> int { return 1; }\n"
     "fn g(t: S) -> int { return f(t); }\nfn main() { }\n",
     "variable 't' has heap-backed type 'S'", "freestanding"),
    ("enum str payload constructed",
     'enum E { A(str), B }\nfn main() { let e: E = A("hi"); }\n',
     "string literal allocates on the heap", "freestanding"),
    ("tuple carrying a str",
     'fn main() { let t: (str, int) = ("a", 2); }\n',
     "string literal allocates on the heap", "freestanding"),
    ("fail with a string message",
     'fn main() { fail("boom"); }\n',
     "string literal allocates on the heap", "freestanding"),
]

DEMO_PROG = open(DEMO).read()

ALLOW_CASES = [
    ("demo struct program", DEMO_PROG, 42),
    ("plain struct passed between fns",
     "struct P { x: int, y: int }\n"
     "fn f(p: P) -> int { return p.x; }\n"
     "fn g(q: P) -> int { return f(q); }\n"
     "fn main() -> int { let p: P = P { x: 40, y: 2 }; return g(p); }\n",
     40),
    ("tuple of ints",
     "fn main() -> int { let t: (int, int) = (1, 2); return t.0 + t.1; }\n",
     3),
    ("enum with int payload",
     "enum E { A(int), B }\nfn main() -> int { let e: E = A(41); return 42; }\n",
     42),
    # Dead declarations naming heap types still declare: they
    # generate no heap code, and no value of such a type exists.
    ("struct with str field, declared only",
     "struct S { name: str }\nfn main() { }\n",
     0),
    ("unused str parameter",
     "fn f(s: str) -> int { return 1; }\nfn main() { }\n",
     0),
    ("enum with str payload, declared only",
     "enum E { A(str), B }\nfn main() { }\n",
     0),
]


def main():
    print("freestanding rejections (named, at check time)")
    for name, prog, *needles in REJECT_CASES:
        reject(name, prog, *needles)

    print("freestanding programs that build and run")
    for name, prog, expected in ALLOW_CASES:
        build_run(name, prog, expected)

    print("emitted C contains no heap calls")
    d = tempfile.mkdtemp(prefix="noheap-emit-")
    r = run(FORGE + ["emit", DEMO, "--freestanding"])
    c_src = r.stdout
    check("emit succeeds", r.returncode == 0, f"err={r.stderr[:200]!r}")
    check("emit has no malloc", "malloc" not in c_src)
    check("emit has no free(", "free(" not in c_src)
    check("emit has no memset", "memset" not in c_src)
    check("emit has no struct array-free helper",
          "array_free" not in c_src)

    print("big32 accepts the rule under the same flag")
    # The demo uses a struct parameter, which the big32 backend
    # does not support in v1 (pre-existing, unrelated to #39), so
    # the big32 check uses a scalar freestanding program instead.
    d = tempfile.mkdtemp(prefix="noheap-big32-")
    prog = ("fn main() {\n  poke32(32768, 24);\n"
            "  if peek32(32768) == 24 {\n"
            "    poke32(268435456, 79);\n  }\n}\n")
    path = write_prog(d, prog, "big32.fg")
    out = os.path.join(d, "demo")
    r = run(FORGE + ["build", path, "--target", "big32",
                     "--freestanding", "-o", out])
    check("build --target big32 --freestanding ok", r.returncode == 0,
          f"err={r.stderr[:200]!r}")
    check("big32 .hex produced", os.path.exists(out + ".hex"))
    path2 = write_prog(d, 'fn main() { let s: str = "hi"; }\n',
                       "big32_str.fg")
    r = run(FORGE + ["build", path2, "--target", "big32",
                     "--freestanding", "-o", os.path.join(d, "demo2")])
    check("big32 --freestanding rejects string literal",
          r.returncode != 0
          and "string literal allocates on the heap" in (r.stdout + r.stderr),
          f"rc={r.returncode} out={(r.stdout + r.stderr)[:200]!r}")

    print("hosted controls")
    build_run("str program builds hosted",
              'fn main() { let s: str = "hi"; }\n', 0, freestanding=False)
    build_run("push program builds hosted",
              "fn main() { let mut a: [int] = [1]; push(a, 2); }\n",
              0, freestanding=False)

    print("fmt idempotent (demo)")
    rf = run(FORGE + ["fmt", "--check", DEMO])
    check("fmt idempotent (demo)", rf.returncode == 0, rf.stderr.strip())

    print("ASan: the demo runs clean (hosted emit)")
    with tempfile.TemporaryDirectory() as td:
        c_path = os.path.join(td, "noheap.c")
        bin_path = os.path.join(td, "noheap_asan")
        r = run(FORGE + ["emit", DEMO])
        with open(c_path, "w") as f:
            f.write(r.stdout)
        cc = run(["cc", "-g", "-fsanitize=address", "-o", bin_path,
                  c_path, "-lssl", "-lcrypto", "-lm"])
        if cc.returncode != 0:
            check("ASan build", False, f"cc err={cc.stderr[:300]!r}")
        else:
            r = subprocess.run([bin_path], capture_output=True, text=True,
                               timeout=30)
            ok = (r.returncode == 42
                  and "AddressSanitizer" not in r.stderr)
            check("ASan run clean", ok,
                  f"rc={r.returncode} err={r.stderr[:300]!r}")

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print(f"\nALL PASS ({CHECKS[0]} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
