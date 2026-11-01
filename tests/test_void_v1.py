"""Top-500 #20: void/unit consistency v1
(tests/test_void_v1.py). void is no value: it is allowed only
as a function or method return type, and every attempt to
treat it as a value fails in the checker with a clear message
instead of broken C downstream.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROG = """
fn greet() {
  println(1);
}
fn greet2() -> int {
  println(2);
  return 3;
}
fn main() {
  greet();
  println(greet2());
}
"""

EXPECTED = "1\n2\n3\n"

CASES = [
    ("void let",
     "fn f() { println(1); }\nfn main() {\n  let x = f();\n}\n",
     "returns void"),
    ("void method let",
     "struct S { v: int; }\nimpl S {\n  fn m(s: S) { println(s.v); }\n}\n"
     "fn main() {\n  let s: S = S { v: 1 };\n  let x = s.m();\n}\n",
     "returns void"),
    ("void struct field",
     "struct S { v: void; }\nfn main() {\n  println(1);\n}\n",
     "unknown field type 'void'"),
    ("void array param",
     "fn g(a: [void]) -> int { return 0; }\nfn main() {\n  println(1);\n}\n",
     "not a value type"),
    ("void tuple element",
     "fn f() { println(1); }\nfn main() {\n  let t = (f(), 5);\n}\n",
     "contains void"),
    ("void array element",
     "fn f() { println(1); }\nfn main() {\n  let a = [f()];\n}\n",
     "contains void"),
    ("void enum payload",
     "enum E { V(void) }\nfn main() {\n  println(1);\n}\n",
     "unknown payload type 'void'"),
    ("void alias",
     "type X = void;\nfn main() {\n  println(1);\n}\n",
     "targets unknown type 'void'"),
    ("void cast",
     "fn main() {\n  let x = 5 as void;\n}\n",
     "unknown cast target 'void'"),
    ("void return with value",
     "fn f() { println(1); }\nfn h() {\n  return f();\n}\nfn main() {\n  h();\n}\n",
     "void function cannot return a value"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "v.fg")
        with open(src, "w") as f:
            f.write(PROG)
        exe = os.path.join(td, "v")
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 "-o", exe, src], ROOT)
        if not check("void program builds", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append("void program builds")
        else:
            r2 = run([exe], td)
            if not check("void results", r2.stdout == EXPECTED,
                         repr(r2.stdout)):
                failures.append("void results")
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
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
