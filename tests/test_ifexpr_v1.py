"""Top-500 #71: if-as-expression (tests/test_ifexpr_v1.py).

Eager ternary helpers (ite_int / ite_str / ite_bool) and lazy
variants (ite_lazy_int / ite_lazy_str / ite_lazy_bool) as pure
functions in forge_lang/stdlib/ifexpr.fg. The eager forms take
values, so both branches are evaluated before the call; the lazy
forms take zero-argument functions and call only the chosen one,
proved here with a shared array-buffer counter (index assignment
into a captured array is visible to the caller; push is not, and
assigning to a captured scalar is a checker error).

v1 limits (named in the catalog): int / str / bool only, concrete
variants (no generic helper — generic helpers returning structs
with array fields leak under the hosted codegen, #51); no
short-circuit in the eager forms by design. Both compilers
(Python + hosted). Runs use cwd=ROOT (like test_errrender_v1.py):
the hosted binary resolves stdlib imports relative to the repo
root (forge_lang/stdlib/), so a temp cwd would break every
import. Nothing is written to the tree.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """1
2
yes
no
true
false
10
20
no
true
20
0
1
20
1
2
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("ite_int picks by condition",
     r"""import "ifexpr.fg";
fn main() -> int {
  println(ite_int(true, 1, 2));
  println(ite_int(false, 1, 2));
  println(ite_int(3 > 2, 7, 8));
  return 0;
}
""",
     """1
2
7
""",
     ""),
    ("ite_str picks by condition",
     r"""import "ifexpr.fg";
fn main() -> int {
  println(ite_str(true, "a", "b"));
  println(ite_str(false, "a", "b"));
  println(ite_str(1 == 2, "same", "diff"));
  return 0;
}
""",
     """a
b
diff
""",
     ""),
    ("ite_bool picks by condition",
     r"""import "ifexpr.fg";
fn main() -> int {
  println(ite_bool(true, true, false));
  println(ite_bool(false, true, false));
  println(ite_bool(true, false, true));
  return 0;
}
""",
     """true
false
false
""",
     ""),
    ("ite_lazy_int calls only the chosen named fn",
     r"""import "ifexpr.fg";
fn ten() -> int { return 10; }
fn twenty() -> int { return 20; }
fn main() -> int {
  println(ite_lazy_int(true, ten, twenty));
  println(ite_lazy_int(false, ten, twenty));
  return 0;
}
""",
     """10
20
""",
     ""),
    ("ite_lazy_str and ite_lazy_bool with named fns",
     r"""import "ifexpr.fg";
fn yes() -> str { return "yes"; }
fn no() -> str { return "no"; }
fn tru() -> bool { return true; }
fn fls() -> bool { return false; }
fn main() -> int {
  println(ite_lazy_str(true, yes, no));
  println(ite_lazy_str(false, yes, no));
  println(ite_lazy_bool(false, tru, fls));
  return 0;
}
""",
     """yes
no
false
""",
     ""),
    ("lazy calls only the chosen branch (counter)",
     r"""import "ifexpr.fg";
fn main() -> int {
  let hits: [int] = [0, 0];
  let t = fn() -> int { hits[0] = hits[0] + 1; return 10; };
  let e = fn() -> int { hits[1] = hits[1] + 1; return 20; };
  println(ite_lazy_int(false, t, e));
  println(hits[0]);
  println(hits[1]);
  println(ite_lazy_int(true, t, e));
  println(hits[0]);
  println(hits[1]);
  return 0;
}
""",
     """20
0
1
10
1
1
""",
     ""),
    ("eager evaluates BOTH branches (counter)",
     r"""import "ifexpr.fg";
fn main() -> int {
  let hits: [int] = [0, 0];
  let t = fn() -> int { hits[0] = hits[0] + 1; return 10; };
  let e = fn() -> int { hits[1] = hits[1] + 1; return 20; };
  println(ite_int(false, t(), e()));
  println(hits[0]);
  println(hits[1]);
  return 0;
}
""",
     """20
1
1
""",
     ""),
    ("lazy str with inline lambdas",
     r"""import "ifexpr.fg";
fn main() -> int {
  let a = fn() -> str { return "picked-a"; };
  let b = fn() -> str { return "picked-b"; };
  println(ite_lazy_str(true, a, b));
  println(ite_lazy_str(false, a, b));
  return 0;
}
""",
     """picked-a
picked-b
""",
     ""),
    ("nested ite chains like else-if",
     r"""import "ifexpr.fg";
fn grade(n: int) -> str {
  return ite_str(n >= 90, "A", ite_str(n >= 70, "B", "C"));
}
fn main() -> int {
  println(grade(95));
  println(grade(80));
  println(grade(10));
  return 0;
}
""",
     """A
B
C
""",
     ""),
    ("ite_int with negative and zero values",
     r"""import "ifexpr.fg";
fn main() -> int {
  println(ite_int(true, 0 - 5, 5));
  println(ite_int(false, 0, 0 - 1));
  println(ite_lazy_int(false, fn() -> int { return 3; }, fn() -> int { return 4; }));
  return 0;
}
""",
     """-5
-1
4
""",
     ""),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_STACK,
                           (65536 * 1024, resource.RLIM_INFINITY))
    except Exception:
        pass
    with tempfile.TemporaryDirectory() as td:
        _run_all(td, failures)
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


def _run_all(td, failures):
    demo = os.path.join(ROOT, "examples", "ifexpr_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "ifexpr.fg")
    for mode, prefix in (("hosted", []), ("python", ["--python"])):
        r = run([sys.executable, os.path.join(ROOT, "forge.py")] + prefix +
                ["run", demo], ROOT)
        if not check(f"demo runs ({mode})", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append(f"demo runs ({mode})")
        elif not check(f"demo results ({mode})", r.stdout == DEMO_EXPECTED,
                       repr(r.stdout)):
            failures.append(f"demo results ({mode})")
    for name, prog, want, needle in OK_CASES:
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(prog)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["run", p], ROOT)
            ok = (rr.returncode == 0 and rr.stdout == want and
                  (not needle or needle in rr.stderr))
            if not check(f"{name} ({mode})", ok,
                         repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"{name} ({mode})")
    # fmt strips // comments, so the lib (which keeps its header) is
    # not fmt-run here — demo only, same as test_errrender_v1.py.
    for target in (demo,):
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", target],
                 ROOT)
        if not check(f"fmt runs ({os.path.basename(target)})",
                     rf.returncode == 0, rf.stderr.strip()):
            failures.append(f"fmt runs ({target})")
        else:
            rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                       "fmt", "--check", target], ROOT)
            if not check(f"fmt idempotent ({os.path.basename(target)})",
                         rf2.returncode == 0, rf2.stderr.strip()):
                failures.append(f"fmt idempotent ({target})")


if __name__ == "__main__":
    sys.exit(main())
