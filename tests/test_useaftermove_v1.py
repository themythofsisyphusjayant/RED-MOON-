"""Top-500 #40: use-after-move checking (tests/test_useaftermove_v1.py).
Move semantics (#27 v2) already rejected the direct uses — a plain use,
a second move, len/for-iteration after a move — but five holes stayed
open, each confirmed as a real heap-use-after-free under AddressSanitizer
before the fix:

- push(a, v) and a[i] = v through a moved array (the push/index-assign
  paths only looked the target up, never checked it);
- a whole-value use of an intermediate struct path after a nested field
  move (let x = o.inner after move(o.inner.vals));
- a while condition that reads a value the body moves (the condition is
  re-evaluated after the body frees the moved-to binding);
- moving a for loop's iterable inside its body (the next iteration reads
  the freed buffer, even if the body reassigns the variable afterwards
  — the loop still holds the old buffer).

The fix is checker-only (forge_lang/checker.py): moved checks on the
push/index-assign variable targets, a descendant-moved-field check on
outermost field accesses, a re-check of the while condition against the
post-body moved set, and a for-iterable stack consulted by move().
Native-only; big32 and WASM reject move programs.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "1\n9\nhi\n3\n5\ndone\n"

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("field move then sibling use",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let b: Bag = Bag { vals: [1], tag: \"x\" };\n  let v = move(b.vals);\n  println(b.tag);\n  println(v[0]);\n}\n",
     "x\n1\n"),
    ("reassign revives moved var",
     "fn main() {\n  let mut a = [1];\n  let b = move(a);\n  a = [9];\n  println(a[0]);\n}\n",
     "9\n"),
    ("field assign revives moved field",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let mut b: Bag = Bag { vals: [1], tag: \"x\" };\n  let v = move(b.vals);\n  b.vals = [9];\n  println(b.vals[0]);\n}\n",
     "9\n"),
    ("whole intermediate assign revives nested field",
     "struct Inner {\n  vals: [int];\n  tag: str;\n}\n\nstruct Outer {\n  inner: Inner;\n  n: int;\n}\n\nfn main() {\n  let mut o: Outer = Outer { inner: Inner { vals: [1], tag: \"x\" }, n: 1 };\n  let f = move(o.inner.vals);\n  o.inner = Inner { vals: [7], tag: \"y\" };\n  println(o.inner.vals[0]);\n  println(o.inner.tag);\n}\n",
     "7\ny\n"),
    ("sibling of nested moved field stays usable",
     "struct Inner {\n  vals: [int];\n  tag: str;\n}\n\nstruct Outer {\n  inner: Inner;\n  n: int;\n}\n\nfn main() {\n  let mut o: Outer = Outer { inner: Inner { vals: [1], tag: \"x\" }, n: 1 };\n  let f = move(o.inner.vals);\n  println(o.inner.tag);\n  println(o.n);\n  println(f[0]);\n}\n",
     "x\n1\n1\n"),
    ("while cond uses var body does not move",
     "fn main() {\n  let a = [1, 2];\n  let mut i = 0;\n  while i < len(a) {\n    println(a[i]);\n    i = i + 1;\n  }\n}\n",
     "1\n2\n"),
    ("while body moves then reassigns before next check",
     "fn main() {\n  let mut a = [5];\n  let mut i = 0;\n  while i < len(a) {\n    let b = move(a);\n    println(b[0]);\n    a = [0];\n    i = i + 1;\n  }\n  println(\"done\");\n}\n",
     "5\ndone\n"),
    ("for over field, body does not move it",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let b: Bag = Bag { vals: [1, 2], tag: \"x\" };\n  for x in b.vals {\n    println(x);\n  }\n  println(b.tag);\n}\n",
     "1\n2\nx\n"),
    ("for body moves a body-local, not the iterable",
     "fn main() {\n  let a = [1, 2];\n  for x in a {\n    let tmp = [5];\n    let e = move(tmp);\n    println(e[0] + x);\n  }\n}\n",
     "6\n7\n"),
    ("shadowed iterable name may move",
     "fn main() {\n  let a = [1, 2];\n  for x in a {\n    let a = [9, 8];\n    let b = move(a);\n    println(b[0]);\n    println(x);\n  }\n}\n",
     "9\n1\n9\n2\n"),
    ("nested fors over different arrays",
     "fn main() {\n  let a = [1, 2];\n  let c = [3];\n  for x in a {\n    for y in c {\n      println(x + y);\n    }\n  }\n}\n",
     "4\n5\n"),
]

# (name, program, error fragment) — must be rejected at check time.
REJECT_CASES = [
    ("push into moved array",
     "fn main() {\n  let mut a = [1, 2];\n  let b = move(a);\n  push(a, 3);\n  println(b[0]);\n}\n",
     "use of moved value 'a'"),
    ("index-assign into moved array",
     "fn main() {\n  let mut a = [1, 2];\n  let b = move(a);\n  a[0] = 9;\n  println(b[0]);\n}\n",
     "use of moved value 'a'"),
    ("intermediate path after nested field move",
     "struct Inner {\n  vals: [int];\n  tag: str;\n}\n\nstruct Outer {\n  inner: Inner;\n  n: int;\n}\n\nfn main() {\n  let mut o: Outer = Outer { inner: Inner { vals: [1], tag: \"x\" }, n: 1 };\n  let f = move(o.inner.vals);\n  let x = o.inner;\n  println(x.tag);\n}\n",
     "with moved field 'o.inner.vals'"),
    ("push into moved intermediate field",
     "struct Inner {\n  vals: [int];\n  tag: str;\n}\n\nstruct Outer {\n  inner: Inner;\n  n: int;\n}\n\nfn main() {\n  let mut o: Outer = Outer { inner: Inner { vals: [1], tag: \"x\" }, n: 1 };\n  let q = move(o.inner);\n  push(o.inner.vals, 2);\n  println(q.tag);\n}\n",
     "use of moved value 'o.inner'"),
    ("while condition uses var the body moves",
     "fn main() {\n  let mut a = [1, 2];\n  let mut i = 0;\n  while i < len(a) {\n    let b = move(a);\n    println(b[0]);\n    i = i + 1;\n  }\n}\n",
     "use of moved value 'a'"),
    ("while condition indexes var the body moves",
     "fn main() {\n  let mut a = [1, 2];\n  let mut i = 0;\n  while a[0] > 0 {\n    let b = move(a);\n    println(b[0]);\n    i = i + 1;\n    if i > 1 {\n      a = [0];\n    }\n  }\n}\n",
     "use of moved value 'a'"),
    ("while condition uses field the body moves",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let mut b: Bag = Bag { vals: [1, 2], tag: \"x\" };\n  let mut i = 0;\n  while b.vals[0] > 0 {\n    let c = move(b);\n    println(c.tag);\n    i = i + 1;\n  }\n}\n",
     "use of moved value 'b'"),
    ("for iterable moved in body",
     "fn main() {\n  let a = [1, 2];\n  for x in a {\n    let b = move(a);\n    println(b[0]);\n  }\n}\n",
     "it is the iterable of an enclosing for loop"),
    # A field move inside a loop is already rejected by the v2
    # rule before the iterable check runs — the program is still
    # rejected, with the earlier message.
    ("for iterable field move rejected by v2 rule first",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let b: Bag = Bag { vals: [1, 2], tag: \"x\" };\n  for x in b.vals {\n    let v = move(b.vals);\n    println(v[0]);\n  }\n}\n",
     "move of a field inside a branch or loop is not supported in v2"),
    ("for iterable struct moved in body",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let b: Bag = Bag { vals: [1, 2], tag: \"x\" };\n  for x in b.vals {\n    let c = move(b);\n    println(c.tag);\n  }\n}\n",
     "it is the iterable of an enclosing for loop"),
    ("for iterable moved then reassigned in body",
     "fn main() {\n  let mut a = [1, 2];\n  for x in a {\n    let b = move(a);\n    println(b[0]);\n    a = [9];\n  }\n}\n",
     "it is the iterable of an enclosing for loop"),
    ("second move straight-line",
     "fn main() {\n  let a = [1];\n  let b = move(a);\n  let c = move(a);\n  println(b[0]);\n}\n",
     "use of moved value 'a'"),
    ("push into moved field",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let mut b: Bag = Bag { vals: [1], tag: \"x\" };\n  let v = move(b.vals);\n  push(b.vals, 2);\n  println(v[0]);\n}\n",
     "use of moved value 'b.vals'"),
    ("index-assign into moved field",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let mut b: Bag = Bag { vals: [1], tag: \"x\" };\n  let v = move(b.vals);\n  b.vals[0] = 9;\n  println(v[0]);\n}\n",
     "use of moved value 'b.vals'"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "useaftermove_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("use-after-move demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("use-after-move demo runs")
    elif not check("use-after-move demo results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("use-after-move demo results")
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
        # big32 and WASM still reject move programs (native-only).
        for cmd, frag in (("emit-big32", "big32: move is not supported"),
                          ("emit-wasm", "wasm: move is not supported")):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), cmd, demo],
                     ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{cmd} rejects move", ok,
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
