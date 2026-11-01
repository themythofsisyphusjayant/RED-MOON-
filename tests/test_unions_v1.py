"""Top-500 #7: union types v1 (tests/test_unions_v1.py).

`int | str` holds exactly one member value, tagged by member
index. Member values wrap into a union at assignment, argument,
return, and struct-field sites; a union leaves only through match
arms named by member type, which bind the narrowed value. v1
members are the four scalars; struct, enum, array, and generic
members, subset conversions, and arrays of unions are later
slices. big32 and WASM reject union programs in v1.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
fn describe(x: int | str) -> int {
  let mut out: int = 0;
  match x {
    int(v) => { out = v; }
    str(s) => { out = 7; }
  }
  return out;
}
struct Box { v: int | str; }
fn make() -> int | str {
  return 9;
}
fn main() {
  let u: int | str = 42;
  match u {
    int(v) => { println(v); }
    str(s) => { println(s); }
  }
  let v: int | str = "hi";
  match v {
    int(n) => { println(n); }
    str(s) => { println(s); }
  }
  println(describe(v));
  let mut w: int | str = 1;
  w = "yo";
  match w {
    int(n) => { println(n); }
    str(s) => { println(s); }
  }
  let y: int | str = v;
  match y {
    int(n) => { println(n); }
    str(s) => { println(s); }
  }
  let b = Box { v: "s" };
  match b.v {
    int(n) => { println(n); }
    str(s) => { println(s); }
  }
  let m: int | str = make();
  match m {
    int(n) => { println(n); }
    str(s) => { println(s); }
  }
}
"""

EXPECTED = "42\nhi\n7\nyo\nhi\ns\n9\n"

CASES = [
    # (name, program, expected stderr fragment)
    ("union to member assignment",
     "fn main() {\n  let u: int | str = 5;\n  let n: int = u;\n  println(n);\n}\n",
     "declared int but initialised with int | str"),
    ("non-member value",
     "fn main() {\n  let u: int | str = 5.5;\n  println(1);\n}\n",
     "declared int | str but initialised with float"),
    ("duplicate member",
     "fn main() {\n  let u: int | int = 5;\n  println(1);\n}\n",
     "unknown type"),
    ("struct member",
     "struct P { x: int; }\nfn main() {\n  let u: int | P = 5;\n  println(1);\n}\n",
     "unknown type"),
    ("non-exhaustive match",
     "fn main() {\n  let u: int | str = 5;\n  match u {\n    int(v) => { println(v); }\n  }\n}\n",
     "not exhaustive"),
    ("arm without binding",
     "fn main() {\n  let u: int | str = 5;\n  match u {\n    int => { println(1); }\n    str(s) => { println(s); }\n  }\n}\n",
     "has a value"),
    ("unknown member arm",
     "fn main() {\n  let u: int | str = 5;\n  match u {\n    int(v) => { println(v); }\n    bool(b) => { println(b); }\n  }\n}\n",
     "not a member of union"),
    ("union equality",
     "fn main() {\n  let u: int | str = 5;\n  let v: int | str = 5;\n  println(u == v);\n}\n",
     "needs matching"),
    ("mixed array literal",
     "fn main() {\n  let xs: [int | str] = [1, \"a\"];\n  println(1);\n}\n",
     "same type"),
    ("union to member cast",
     "fn main() {\n  let u: int | str = 5;\n  let n: int = u as int;\n  println(n);\n}\n",
     "cannot cast int | str to int"),
    ("member passed as wrong union",
     "fn take(x: int | bool) -> int {\n  return 1;\n}\nfn main() {\n  let u: int | str = 5;\n  println(take(u));\n}\n",
     "must be int | bool, got int | str"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "u.fg")
        with open(src, "w") as f:
            f.write(PROG)
        exe = os.path.join(td, "u")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "-o", exe, src], ROOT)
        if not check("union program builds", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("union program builds")
        else:
            r2 = run([exe], td)
            if not check("union results", r2.stdout == EXPECTED,
                         repr(r2.stdout)):
                failures.append("union results")
        # Cast into a union through an alias (direct `as int | str`
        # parses as a cast followed by bitwise-or, so the alias
        # route is the explicit-cast spelling).
        alias = ("type U = int | str;\nfn main() {\n"
                 "  let u: U = 5 as U;\n"
                 "  match u {\n    int(v) => { println(v); }\n"
                 "    str(s) => { println(s); }\n  }\n}\n")
        asrc = os.path.join(td, "a.fg")
        with open(asrc, "w") as f:
            f.write(alias)
        aexe = os.path.join(td, "a")
        ra = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                  "-o", aexe, asrc], ROOT)
        if ra.returncode == 0:
            r2 = run([aexe], td)
            if not check("alias cast into union", r2.stdout == "5\n",
                         repr(r2.stdout)):
                failures.append("alias cast into union")
        else:
            if not check("alias cast into union", False, ra.stderr.strip()):
                failures.append("alias cast into union")
        # Rejections.
        for name, prog, frag in CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", p],
                     ROOT)
            ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
            if not check(f"{name} rejected", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
        # fmt round-trip.
        fmt = os.path.join(td, "f.fg")
        with open(fmt, "w") as f:
            f.write(PROG)
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", fmt],
                 ROOT)
        if not check("fmt runs", rf.returncode == 0, rf.stderr.strip()):
            failures.append("fmt runs")
        else:
            rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                       "fmt", "--check", fmt], ROOT)
            if not check("fmt idempotent", rf2.returncode == 0, rf2.stderr.strip()):
                failures.append("fmt idempotent")
            else:
                fexe = os.path.join(td, "f")
                rb = run([sys.executable, os.path.join(ROOT, "forge.py"),
                          "build", "-o", fexe, fmt], ROOT)
                if rb.returncode == 0:
                    r2 = run([fexe], td)
                    if not check("formatted program still runs",
                                 r2.stdout == EXPECTED, repr(r2.stdout)):
                        failures.append("formatted program still runs")
                else:
                    check("formatted program still runs", False, rb.stderr.strip())
                    failures.append("formatted program still runs")
        # big32 and WASM gates. The big32 program is freestanding
        # (no println): the union gate must fire, not the I/O one.
        bsrc = os.path.join(td, "bk.fg")
        with open(bsrc, "w") as f:
            f.write("fn main() {\n  let u: int | float = 5;\n  let n: int = 1;\n}\n")
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                  "--target", "big32", "--freestanding", "-o",
                  os.path.join(td, "b"), bsrc], ROOT)
        ok = rb.returncode != 0 and "big32: union types are not supported" in (
            rb.stderr + rb.stdout)
        if not check("big32 rejects unions", ok, rb.stderr.strip()[-120:]):
            failures.append("big32 rejects unions")
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit-wasm",
                  "-o", os.path.join(td, "w.wasm"), src], ROOT)
        ok = rw.returncode != 0 and "wasm: union types are not supported" in (
            rw.stderr + rw.stdout)
        if not check("wasm rejects unions", ok, rw.stderr.strip()[-120:]):
            failures.append("wasm rejects unions")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
