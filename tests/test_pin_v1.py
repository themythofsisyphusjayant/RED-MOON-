"""Top-500 #34: pinning v1 (tests/test_pin_v1.py).
`pin(x);` marks an owned binding immovable for the rest of
its scope: no move or copy after it (any whole-value use,
call argument, return, reassignment, or push is a checker
error), while in-place field/index writes, scalar field and
element reads, len/refcount, and for-iteration still work.
Pinning is compile-time only (native codegen emits nothing
for the statement); big32 and WASM reject pin programs.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "2\n2\n25\n3\n65\n9\n3\n"

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("scalar element through an owned field",
     "struct B { vals: [int]; tag: int; }\nfn main() {\n"
     "  let b: B = B { vals: [1, 2], tag: 2 };\n"
     "  pin(b);\n  println(b.vals[1]);\n}\n",
     "2\n"),
    ("scalar field write and read of pinned struct",
     "struct B { vals: [int]; tag: int; }\nfn main() {\n"
     "  let mut b: B = B { vals: [1], tag: 2 };\n"
     "  pin(b);\n  b.tag = 5;\n  println(b.tag);\n}\n",
     "5\n"),
    ("nested scalar read",
     "struct I { x: int; }\nstruct O { inner: I; }\nfn main() {\n"
     "  let o: O = O { inner: I { x: 4 } };\n"
     "  pin(o);\n  println(o.inner.x);\n}\n",
     "4\n"),
    ("pin of a parameter",
     "fn use_it(n: [int]) -> int {\n  pin(n);\n  return n[0];\n}\n"
     "fn main() {\n  println(use_it([8]));\n}\n",
     "8\n"),
    ("pin in an else branch, scalar read after",
     "fn main() {\n  let a = [1];\n  if false {\n"
     "    println(0);\n  } else {\n    pin(a);\n  }\n"
     "  println(a[0]);\n}\n",
     "1\n"),
    ("pin inside a loop body, scalar read after",
     "fn main() {\n  let mut a = [1, 2];\n  let mut i = 0;\n"
     "  while i < 1 {\n    pin(a);\n    i = i + 1;\n  }\n"
     "  println(a[0]);\n}\n",
     "1\n"),
    ("shadowing a pinned binding",
     "fn main() {\n  let a = [1];\n  pin(a);\n  if true {\n"
     "    let a = [9];\n    println(a[0]);\n  }\n"
     "  println(a[0]);\n}\n",
     "9\n1\n"),
    ("refcount of a pinned array",
     "fn main() {\n  let a = [1, 2];\n  pin(a);\n  println(refcount(a));\n}\n",
     "1\n"),
    ("for over a pinned nested array",
     "fn main() {\n  let a = [[1, 2], [3, 4]];\n  pin(a);\n"
     "  let mut t = 0;\n  for row in a {\n    t = t + row[0];\n  }\n"
     "  println(t);\n}\n",
     "4\n"),
]

# (name, program, error fragment) — must be rejected at check time.
REJECT_CASES = [
    ("move of pinned",
     "fn main() {\n  let a = [1];\n  pin(a);\n  let b = move(a);\n}\n",
     "cannot move pinned value 'a'"),
    ("copy via let",
     "fn main() {\n  let a = [1];\n  pin(a);\n  let b = a;\n}\n",
     "use of pinned value 'a'"),
    ("copy via call argument",
     "fn f(x: [int]) -> int { return x[0]; }\nfn main() {\n"
     "  let a = [1];\n  pin(a);\n  println(f(a));\n}\n",
     "use of pinned value 'a'"),
    ("return of pinned",
     "fn f() -> [int] {\n  let a = [1];\n  pin(a);\n  return a;\n}\n"
     "fn main() {\n  println(f()[0]);\n}\n",
     "use of pinned value 'a'"),
    ("reassign pinned",
     "fn main() {\n  let mut a = [1];\n  pin(a);\n  a = [2];\n}\n",
     "cannot reassign pinned variable 'a'"),
    ("push to pinned",
     "fn main() {\n  let mut a = [1];\n  pin(a);\n  push(a, 2);\n}\n",
     "cannot push to pinned value 'a'"),
    ("owned field read",
     "struct B { vals: [int]; tag: int; }\nfn main() {\n"
     "  let b: B = B { vals: [1], tag: 2 };\n"
     "  pin(b);\n  let v = b.vals;\n}\n",
     "use of pinned value 'b'"),
    ("owned element read",
     "fn main() {\n  let a = [[1], [2]];\n  pin(a);\n  let b = a[0];\n}\n",
     "use of pinned value 'a'"),
    ("pin of int",
     "fn main() {\n  let a = 5;\n  pin(a);\n}\n",
     "pin needs an owned value"),
    ("pin of literal",
     "fn main() {\n  pin([1, 2]);\n}\n",
     "pin needs a variable"),
    ("double pin",
     "fn main() {\n  let a = [1];\n  pin(a);\n  pin(a);\n}\n",
     "already pinned"),
    ("pin of moved",
     "fn main() {\n  let a = [1];\n  let b = move(a);\n  pin(a);\n}\n",
     "cannot pin moved value 'a'"),
    ("pin of for-loop variable",
     "fn main() {\n  let xs = [[1], [2]];\n  for x in xs {\n"
     "    pin(x);\n  }\n}\n",
     "pin of a for-loop variable"),
    ("move a field of pinned",
     "struct B { vals: [int]; tag: int; }\nfn main() {\n"
     "  let b: B = B { vals: [1], tag: 2 };\n"
     "  pin(b);\n  let v = move(b.vals);\n}\n",
     "cannot move a field of pinned value 'b'"),
    ("method call on pinned",
     "struct B { tag: int; }\nimpl B {\n"
     "  fn get(b: B) -> int { return b.tag; }\n}\n"
     "fn main() {\n  let b: B = B { tag: 7 };\n"
     "  pin(b);\n  println(b.get());\n}\n",
     "use of pinned value 'b'"),
    ("pin of a struct with a drop method",
     "struct B { tag: int; }\nimpl B {\n"
     "  fn drop(b: B) { println(b.tag); }\n}\n"
     "fn main() {\n  let b: B = B { tag: 7 };\n  pin(b);\n}\n",
     "cannot pin a value of struct 'B' with a drop method"),
    ("pin in a branch, then move after",
     "fn main() {\n  let a = [1];\n  if true {\n    pin(a);\n  }\n"
     "  let b = move(a);\n}\n",
     "cannot move pinned value 'a'"),
    ("pin used as a value",
     "fn main() {\n  let a = [1];\n  let b = pin(a);\n}\n",
     "can only be used as a statement"),
    ("pin of a field",
     "struct B { vals: [int]; tag: int; }\nfn main() {\n"
     "  let b: B = B { vals: [1], tag: 2 };\n  pin(b.vals);\n}\n",
     "pin needs a variable"),
    ("string index of pinned",
     "fn main() {\n  let s = \"hi\";\n  pin(s);\n  println(s[0]);\n}\n",
     "use of pinned value 's'"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "pin_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("pin demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("pin demo runs")
    elif not check("pin demo results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("pin demo results")
    with tempfile.TemporaryDirectory() as td:
        for name, prog, want in OK_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", p],
                     ROOT)
            ok = rr.returncode == 0 and rr.stdout == want
            if not check(f"{name} runs", ok,
                         repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
        for name, prog, frag in REJECT_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", p],
                     ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{name} rejected", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
        # big32 and WASM still reject pin programs (native-only).
        for cmd, frag in (("emit-big32", "big32: pin is not supported"),
                          ("emit-wasm", "wasm: pin is not supported")):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), cmd, demo],
                     ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{cmd} rejects pin", ok,
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
