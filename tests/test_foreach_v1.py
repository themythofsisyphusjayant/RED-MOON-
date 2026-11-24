"""Top-500 #66: for-each over any iterable (tests/test_foreach_v1.py).

For-each helpers over iter.fg Iter values and string chars in
forge_lang/stdlib/foreach.fg: fe_each applies a body to each
element of an Iter in order and returns the count; fe_each_str
applies a body to each character of a string (as a 1-char str)
and returns the count; fe_map_iter maps f over an Iter and
returns the [int] results (via hof.fg map over the remaining
elements). These cover what `for` does not provide: Iter
values (which compose with it_skip / it_take) and string
characters.

v1 limits (named in the catalog): no maps/sets/generators (no
such types exist yet in the language); int elements + str
chars only. Both compilers (Python + hosted). Runs use
cwd=ROOT (like test_errcode_v1.py): the hosted binary
resolves stdlib imports relative to the repo root
(forge_lang/stdlib/), so a temp cwd would break every
import. Nothing is written to the tree.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """10
20
30
3
h
i
2
3
6
9
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("fe_each applies in order and returns the count",
     r"""import "foreach.fg";
import "iter.fg";
fn show_num(x: int) -> int {
  println(x);
  return x;
}

fn main() -> int {
  println(fe_each(it_new([5, 6]), show_num));
  return 0;
}
""",
     """5
6
2
""",
     ""),
    ("fe_each on an empty iterator returns 0",
     r"""import "foreach.fg";
import "iter.fg";
fn show_num(x: int) -> int {
  println(x);
  return x;
}

fn main() -> int {
  println(fe_each(it_new([]), show_num));
  return 0;
}
""",
     """0
""",
     ""),
    ("fe_each respects a skipped iterator",
     r"""import "foreach.fg";
import "iter.fg";
fn show_num(x: int) -> int {
  println(x);
  return x;
}

fn main() -> int {
  let rest: Iter = it_skip(it_new([1, 2, 3, 4]), 2);
  println(fe_each(rest, show_num));
  return 0;
}
""",
     """3
4
2
""",
     ""),
    ("fe_each_str applies to each char and returns the count",
     r"""import "foreach.fg";
fn show_ch(c: str) -> int {
  println(c);
  return 1;
}

fn main() -> int {
  println(fe_each_str("ab", show_ch));
  return 0;
}
""",
     """a
b
2
""",
     ""),
    ("fe_each_str on an empty string returns 0",
     r"""import "foreach.fg";
fn show_ch(c: str) -> int {
  println(c);
  return 1;
}

fn main() -> int {
  println(fe_each_str("", show_ch));
  return 0;
}
""",
     """0
""",
     ""),
    ("fe_map_iter maps in order",
     r"""import "foreach.fg";
import "iter.fg";
fn triple(x: int) -> int {
  return x * 3;
}

fn main() -> int {
  let mapped: [int] = fe_map_iter(it_new([1, 2, 3]), triple);
  for x in mapped {
    println(x);
  }
  return 0;
}
""",
     """3
6
9
""",
     ""),
    ("fe_map_iter on an empty iterator returns an empty array",
     r"""import "foreach.fg";
import "iter.fg";
fn triple(x: int) -> int {
  return x * 3;
}

fn main() -> int {
  let mapped: [int] = fe_map_iter(it_new([]), triple);
  println(len(mapped));
  return 0;
}
""",
     """0
""",
     ""),
    ("fe_each composes with it_take",
     r"""import "foreach.fg";
import "iter.fg";
fn show_num(x: int) -> int {
  println(x);
  return x;
}

fn main() -> int {
  let first2: Iter = it_new([9, 8, 7]);
  println(fe_each(it_new(it_take(first2, 2)), show_num));
  return 0;
}
""",
     """9
8
2
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
    demo = os.path.join(ROOT, "examples", "foreach_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "foreach.fg")
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
    # not fmt-run here — demo only, same as test_errcode_v1.py.
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
