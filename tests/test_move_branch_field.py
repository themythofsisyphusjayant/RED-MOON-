"""Top-500 #27 v2: branch/loop moves + field moves
(tests/test_move_branch_field.py). A move in a branch
or loop is a runtime-flagged transfer: the branch may
not run (so the source must still free), and a loop
may run twice (so a second move fails at runtime
instead of transferring a freed buffer). After a
conditional move the source counts as moved, so a
later use is a checker error until reassignment
revives it. A field move transfers one struct field;
sibling fields stay usable, the whole struct and the
moved field do not, and assigning the field revives
it. Field moves in branches/loops and moves of
for-loop variables are rejected (named limits).
Native-only; big32 and WASM reject move programs.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "1\n3\n9\n8\n5\nhi\n"

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("branch taken",
     "fn main() {\n  let mut a = [1, 2, 3];\n  if true {\n    let b = move(a);\n    println(b[0]);\n  }\n  a = [9];\n  println(a[0]);\n}\n",
     "1\n9\n"),
    ("branch not taken",
     "fn main() {\n  let mut a = [1, 2, 3];\n  if false {\n    let b = move(a);\n    println(b[0]);\n  } else {\n    println(a[0]);\n  }\n  a = [5];\n  println(a[0]);\n}\n",
     "1\n5\n"),
    ("both branches move",
     "fn main() {\n  let a = [1, 2];\n  if false {\n    let b = move(a);\n    println(b[0]);\n  } else {\n    let b = move(a);\n    println(b[1]);\n  }\n}\n",
     "2\n"),
    ("loop once",
     "fn main() {\n  let a = [7, 8];\n  let mut i = 0;\n  while i < 1 {\n    let b = move(a);\n    println(b[1]);\n    i = i + 1;\n  }\n}\n",
     "8\n"),
    ("loop break after move",
     "fn main() {\n  let a = [7, 8];\n  let mut i = 0;\n  while i < 5 {\n    let b = move(a);\n    println(b[0]);\n    break;\n  }\n}\n",
     "7\n"),
    ("str branch revive",
     "fn main() {\n  let mut s = \"hello\";\n  if false {\n    let t = move(s);\n    println(t);\n  } else {\n    println(s);\n  }\n  s = \"bye\";\n  println(s);\n}\n",
     "hello\nbye\n"),
    ("field move",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let mut b: Bag = Bag { vals: [1, 2, 3], tag: \"hi\" };\n  let v = move(b.vals);\n  println(v[2]);\n  println(b.tag);\n  b.vals = [9];\n  println(b.vals[0]);\n}\n",
     "3\nhi\n9\n"),
]

# (name, program, error fragment) — must be rejected at check time.
REJECT_CASES = [
    ("use after conditional move",
     "fn main() {\n  let a = [1];\n  if true {\n    let b = move(a);\n    println(b[0]);\n  }\n  println(a[0]);\n}\n",
     "use of moved value 'a'"),
    ("moved field reuse",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let b: Bag = Bag { vals: [1], tag: \"x\" };\n  let v = move(b.vals);\n  println(b.vals[0]);\n}\n",
     "use of moved value 'b.vals'"),
    ("whole struct after field move",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let b: Bag = Bag { vals: [1], tag: \"x\" };\n  let v = move(b.vals);\n  println(b);\n}\n",
     "with moved field 'b.vals'"),
    ("field move in branch",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let b: Bag = Bag { vals: [1], tag: \"x\" };\n  if true {\n    let v = move(b.vals);\n    println(v[0]);\n  }\n}\n",
     "move of a field inside a branch or loop is not supported in v2"),
    ("field move in loop",
     "struct Bag {\n  vals: [int];\n  tag: str;\n}\n\nfn main() {\n  let b: Bag = Bag { vals: [1], tag: \"x\" };\n  let mut i = 0;\n  while i < 1 {\n    let v = move(b.vals);\n    println(v[0]);\n    i = i + 1;\n  }\n}\n",
     "move of a field inside a branch or loop is not supported in v2"),
    ("for-loop variable move",
     "fn main() {\n  let xs = [[1], [2]];\n  for x in xs {\n    let y = move(x);\n    println(y[0]);\n  }\n}\n",
     "move of a for-loop variable is not supported in v2"),
    ("move of literal",
     "fn main() {\n  let b = move([1, 2]);\n}\n",
     "move needs a variable or field"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "move_branch_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("branch demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("branch demo runs")
    elif not check("branch demo results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("branch demo results")
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
        # A second loop move is a runtime failure, not a
        # checker error: the first iteration prints, then the
        # flag trips on the second move.
        p = os.path.join(td, "twice.fg")
        with open(p, "w") as f:
            f.write("fn main() {\n  let a = [7, 8];\n  let mut i = 0;\n"
                    "  while i < 2 {\n    let b = move(a);\n    println(b[0]);\n"
                    "    i = i + 1;\n  }\n}\n")
        rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", p],
                 ROOT)
        ok = (rr.returncode != 0 and rr.stdout == "7\n"
              and "use of moved value 'a'" in rr.stderr)
        if not check("second loop move fails at runtime", ok,
                     repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
            failures.append("second loop move")
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
