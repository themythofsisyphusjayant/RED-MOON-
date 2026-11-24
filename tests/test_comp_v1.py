"""Top-500 #128: array comprehensions as helpers (tests/test_comp_v1.py).

Comprehension-style helpers over [int] in
forge_lang/stdlib/comp.fg, built on the higher-order map/filter
of hof.fg (item 102) and driven by function values (item 103):
comp_range_map builds [f(i) for i in 0..n), comp_filter_map
builds [f(x) for x in xs if pred(x)], comp_range_filter builds
[i for i in 0..n if pred(i)]. The function may be a named
function or a lambda. No comprehension syntax in v1 — that is
a parser feature; these helpers are the library spelling.

v1 limits (named in the catalog): no comprehension syntax,
int arrays only. Both compilers (Python + hosted). Runs use
cwd=ROOT (like test_errrender_v1.py): the hosted binary
resolves stdlib imports relative to the repo root
(forge_lang/stdlib/), so a temp cwd would break every import.
Nothing is written to the tree.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """5
0
1
16
3
4
8
12
5
0
8
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("range_map squares 0..5",
     r"""import "comp.fg";
fn sq(x: int) -> int { return x * x; }
fn main() -> int {
  let a: [int] = comp_range_map(5, sq);
  println(len(a));
  println(a[0]);
  println(a[2]);
  println(a[4]);
  return 0;
}
""",
     """5
0
4
16
""",
     ""),
    ("range_map n=0 is empty",
     r"""import "comp.fg";
fn id(x: int) -> int { return x; }
fn main() -> int {
  let a: [int] = comp_range_map(0, id);
  println(len(a));
  return 0;
}
""",
     """0
""",
     ""),
    ("filter_map: even inputs doubled",
     r"""import "comp.fg";
fn is_even(x: int) -> bool { return x % 2 == 0; }
fn dbl(x: int) -> int { return x * 2; }
fn main() -> int {
  let xs: [int] = [1, 2, 3, 4, 5, 6];
  let a: [int] = comp_filter_map(xs, is_even, dbl);
  println(len(a));
  println(a[0]);
  println(a[1]);
  println(a[2]);
  return 0;
}
""",
     """3
4
8
12
""",
     ""),
    ("filter_map with no match is empty",
     r"""import "comp.fg";
fn is_neg(x: int) -> bool { return x < 0; }
fn dbl(x: int) -> int { return x * 2; }
fn main() -> int {
  let xs: [int] = [1, 2, 3];
  let a: [int] = comp_filter_map(xs, is_neg, dbl);
  println(len(a));
  return 0;
}
""",
     """0
""",
     ""),
    ("range_filter evens to 10",
     r"""import "comp.fg";
fn is_even(x: int) -> bool { return x % 2 == 0; }
fn main() -> int {
  let a: [int] = comp_range_filter(10, is_even);
  println(len(a));
  println(a[0]);
  println(a[2]);
  println(a[4]);
  return 0;
}
""",
     """5
0
4
8
""",
     ""),
    ("range_filter n=0 is empty",
     r"""import "comp.fg";
fn is_even(x: int) -> bool { return x % 2 == 0; }
fn main() -> int {
  let a: [int] = comp_range_filter(0, is_even);
  println(len(a));
  return 0;
}
""",
     """0
""",
     ""),
    ("lambda bound to a let works as the fn value",
     r"""import "comp.fg";
fn main() -> int {
  let f = fn(x: int) -> int { return x + 3; };
  let a: [int] = comp_range_map(3, f);
  println(len(a));
  println(a[0]);
  println(a[2]);
  return 0;
}
""",
     """3
3
5
""",
     ""),
    ("inline lambda passed directly",
     r"""import "comp.fg";
fn main() -> int {
  let a: [int] = comp_range_map(3, fn(x: int) -> int { return x * 10; });
  println(len(a));
  println(a[0]);
  println(a[1]);
  println(a[2]);
  return 0;
}
""",
     """3
0
10
20
""",
     ""),
    ("lambda predicate in filter_map",
     r"""import "comp.fg";
fn main() -> int {
  let xs: [int] = [5, 10, 15, 20];
  let a: [int] = comp_filter_map(xs, fn(x: int) -> bool { return x > 12; }, fn(x: int) -> int { return x - 1; });
  println(len(a));
  println(a[0]);
  println(a[1]);
  return 0;
}
""",
     """2
14
19
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
    demo = os.path.join(ROOT, "examples", "comp_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "comp.fg")
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
