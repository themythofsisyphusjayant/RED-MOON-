#!/usr/bin/env python3
"""Type aliases v1 tests (#6): transparent `type` shorthands.

Aliases expand in the checker before any other checking, so every
backend sees only concrete types: aliases work for already
supported types on native and big32 alike. v1 limits: struct
literals via generic/array aliases are not rewritten (the
literal name must alias a bare struct name); aliases take no
type arguments.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL = os.path.expanduser("~/workspace/big32/tools/model.py")
FAILURES = []

PROG = """struct Person {
  name: str,
  age: int
}

struct Team {
  lead: User,
  ids: Scores
}

type User = Person;
type UserId = int;
type Id = UserId;
type Scores = [int];

fn greet(u: User) -> str {
  return u.name;
}

fn make_id() -> Id {
  return 7;
}

fn main() {
  let id: Id = 42;
  println(id);
  println(make_id());
  let u: User = Person { name: "ada", age: 36 };
  println(greet(u));
  println(u.age);
  let t = Team { lead: u, ids: [10, 20] };
  println(t.ids[1]);
  let v = User { name: "bob", age: 7 };
  println(v.name);
  let x = 5.7 as UserId;
  println(x);
}
"""

GENERIC_PROG = """struct Box<T> {
  value: T
}

type IntBox = Box<int>;

fn main() {
  let b: IntBox = Box { value: 42 };
  println(b.value);
}
"""

ENUM_PROG = """enum Color {
  Red,
  Green
}

type Shade = Color;

fn f(s: Shade) -> int {
  return 1;
}

fn main() {
  let c: Shade = Red;
  println(f(c));
}
"""

KERNEL = """type N = int;

fn put(c: int) {
  poke32(0x10000000, c);
}

fn print_int(v: int) {
  if v < 0 {
    put(45);
    print_int(0 - v);
    return;
  }
  if v >= 10 {
    print_int(v / 10);
  }
  put(48 + v % 10);
}

fn trap_handler(frame: int) {
  let cause = csr_read(834);
  if cause < 0 {
    poke32(0x10000018, 0 - 1);
    poke32(0x1000001C, 0 - 1);
    return;
  }
  csr_write(833, csr_read(833) + 4);
}

fn main() {
  let x: N = 42;
  print_int(x);
  put(10);
  put(68);
  put(79);
  put(78);
  put(69);
  put(10);
  csr_write(773, 0);
  let h = ecall(0, 0);
}
"""

CASES = [
    ("duplicate alias",
     "type A = int;\ntype A = str;\nfn main() {}\n",
     "duplicate type alias 'A'"),
    ("cycle",
     "type A = B;\ntype B = A;\nfn main() {}\n",
     "cyclic type alias"),
    ("unknown target",
     "type Foo = Bar;\nfn main() {}\n",
     "targets unknown type 'Bar'"),
    ("collision with struct",
     "struct S {\n  x: int\n}\ntype S = int;\nfn main() {}\n",
     "collides with an existing type"),
    ("bare generic target",
     "struct Stack<T> {\n  items: [T]\n}\ntype S = Stack;\nfn main() {}\n",
     "without type arguments"),
    ("alias with arguments",
     "type S = int;\nfn main() {\n  let x: S<int> = 5;\n  println(x);\n}\n",
     "takes no type arguments"),
]


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def build(td, name, src, args):
    p = os.path.join(td, name + ".fg")
    with open(p, "w") as f:
        f.write(src)
    out = os.path.join(td, name)
    r = subprocess.run(FORGE + args + ["-o", out, p],
                       capture_output=True, text=True, cwd=ROOT)
    return r, out, p


def main():
    print("type aliases v1 (#6)")
    with tempfile.TemporaryDirectory() as td:
        r, out, _ = build(td, "alias", PROG, ["build"])
        check("alias program builds", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            r2 = subprocess.run([out], capture_output=True, text=True)
            check("alias results",
                  r2.stdout == "42\n7\nada\n36\n20\nbob\n5\n",
                  repr(r2.stdout))
        r, out, _ = build(td, "genalias", GENERIC_PROG, ["build"])
        check("generic alias builds", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            r2 = subprocess.run([out], capture_output=True, text=True)
            check("generic alias result", r2.stdout == "42\n", repr(r2.stdout))
        r, out, _ = build(td, "enumalias", ENUM_PROG, ["build"])
        check("enum alias builds", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            r2 = subprocess.run([out], capture_output=True, text=True)
            check("enum alias result", r2.stdout == "1\n", repr(r2.stdout))
        for name, src, needle in CASES:
            r, _, _ = build(td, "bad", src, ["build"])
            check(f"{name} rejected", r.returncode != 0 and needle in
                  (r.stdout + r.stderr), r.stderr[-200:])
        r, _, p = build(td, "alias", PROG, ["build"])
        r = subprocess.run(FORGE + ["fmt", p],
                           capture_output=True, text=True, cwd=ROOT)
        check("fmt runs", r.returncode == 0, r.stderr[-200:])
        r = subprocess.run(FORGE + ["fmt", "--check", p],
                           capture_output=True, text=True, cwd=ROOT)
        check("fmt idempotent", r.returncode == 0, r.stdout[-200:])
        r2 = subprocess.run(FORGE + ["build", "-o", os.path.join(td, "alias2"), p],
                            capture_output=True, text=True, cwd=ROOT)
        if r2.returncode == 0:
            r3 = subprocess.run([os.path.join(td, "alias2")],
                                capture_output=True, text=True)
            check("formatted program still runs",
                  r3.stdout == "42\n7\nada\n36\n20\nbob\n5\n", repr(r3.stdout))
        else:
            check("formatted program still runs", False, r2.stderr[-200:])
        r, kout, _ = build(td, "aliaskern", KERNEL,
                           ["build", "--target", "big32", "--freestanding"])
        check("alias kernel builds big32", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            spec = importlib.util.spec_from_file_location("big32model", MODEL)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            res = mod.run(kout + ".hex")
            uart = res["uart"].decode("utf-8", "replace")
            check("kernel halts", res["halted"] is True)
            check("kernel transcript", uart == "42\nDONE\n", repr(uart))
    if FAILURES:
        print("FAILED:", FAILURES)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
