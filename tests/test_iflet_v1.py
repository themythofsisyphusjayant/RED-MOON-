"""Top-500 #63: if-let / while-let (tests/test_iflet_v1.py).

Branch-on-value helpers over Result<int, str> and Option<int> in
forge_lang/stdlib/iflet.fg: iflet_ok dispatches on r.ok,
iflet_some dispatches on o.present, and wl_step is the while-let
loop (while has_next(cur) { body(cur); cur = next(cur); }),
returning the count of values consumed. Bodies collect results
through a shared array buffer (index assignment into a captured
array is visible to the caller; push is not, and assigning to a
captured scalar is a checker error).

v1 limits (named in the catalog): concrete over Result<int, str>
and Option<int> only; the direct step form next: fn(int) ->
Option<int> is NOT buildable (both compilers fail to emit the fn
typedef for a generic-struct return), so the step is split into
has_next + next_value; body results are discarded. PYTHON-COMPILER
CAVEAT: the Python compiler only emits the C typedef for a
generic-struct instantiation when the MAIN program mentions that
type, so cases exercising only one side declare a dummy of the
other type (`let _o: Option<int> = ...` / `let _r: Result<int, str>
= ...`); without it the Python build fails with "unknown type
name Option_int" / "Result_int_str". The hosted compiler is
unaffected. Both compilers (Python + hosted). Runs use cwd=ROOT
(like test_errrender_v1.py):
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

DEMO_EXPECTED = """10
4
14
-1
4
4
40
30
20
10
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("iflet_ok takes the ok arm",
     r"""import "iflet.fg";
fn dbl(x: int) -> int { return x * 2; }
fn elen(s: str) -> int { return len(s); }
fn main() -> int {
  let _o: Option<int> = Option { present: false, value: 0 };
  let ok: Result<int, str> = Result { ok: true, value: 5, error: "" };
  println(iflet_ok(ok, dbl, elen));
  return 0;
}
""",
     """10
""",
     ""),
    ("iflet_ok takes the err arm",
     r"""import "iflet.fg";
fn dbl(x: int) -> int { return x * 2; }
fn elen(s: str) -> int { return len(s); }
fn main() -> int {
  let _o: Option<int> = Option { present: false, value: 0 };
  let err: Result<int, str> = Result { ok: false, value: 0, error: "boom" };
  println(iflet_ok(err, dbl, elen));
  let err2: Result<int, str> = Result { ok: false, value: 0, error: "longer message" };
  println(iflet_ok(err2, dbl, elen));
  return 0;
}
""",
     """4
14
""",
     ""),
    ("iflet_some takes the some arm",
     r"""import "iflet.fg";
fn dbl(x: int) -> int { return x * 2; }
fn none0() -> int { return 0 - 1; }
fn main() -> int {
  let _r: Result<int, str> = Result { ok: false, value: 0, error: "" };
  let s: Option<int> = Option { present: true, value: 7 };
  println(iflet_some(s, dbl, none0));
  let z: Option<int> = Option { present: true, value: 0 };
  println(iflet_some(z, dbl, none0));
  return 0;
}
""",
     """14
0
""",
     ""),
    ("iflet_some takes the none arm",
     r"""import "iflet.fg";
fn dbl(x: int) -> int { return x * 2; }
fn none0() -> int { return 0 - 1; }
fn main() -> int {
  let _r: Result<int, str> = Result { ok: false, value: 0, error: "" };
  let n: Option<int> = Option { present: false, value: 0 };
  println(iflet_some(n, dbl, none0));
  return 0;
}
""",
     """-1
""",
     ""),
    ("iflet_ok with inline lambdas",
     r"""import "iflet.fg";
fn main() -> int {
  let _o: Option<int> = Option { present: false, value: 0 };
  let ok: Result<int, str> = Result { ok: true, value: 3, error: "" };
  let a = fn(x: int) -> int { return x + 100; };
  let b = fn(s: str) -> int { return 0 - len(s); };
  println(iflet_ok(ok, a, b));
  let err: Result<int, str> = Result { ok: false, value: 0, error: "xx" };
  println(iflet_ok(err, a, b));
  return 0;
}
""",
     """103
-2
""",
     ""),
    ("iflet_some with inline lambdas",
     r"""import "iflet.fg";
fn main() -> int {
  let _r: Result<int, str> = Result { ok: false, value: 0, error: "" };
  let s: Option<int> = Option { present: true, value: 9 };
  println(iflet_some(s, fn(x: int) -> int { return x * x; }, fn() -> int { return 0 - 9; }));
  let n: Option<int> = Option { present: false, value: 0 };
  println(iflet_some(n, fn(x: int) -> int { return x * x; }, fn() -> int { return 0 - 9; }));
  return 0;
}
""",
     """81
-9
""",
     ""),
    ("wl_step counts a countdown",
     r"""import "iflet.fg";
fn dec(x: int) -> int { return x - 1; }
fn gt0(x: int) -> bool { return x > 0; }
fn dbl(x: int) -> int { return x * 2; }
fn main() -> int {
  let _o: Option<int> = Option { present: false, value: 0 };
  let _r: Result<int, str> = Result { ok: false, value: 0, error: "" };
  println(wl_step(4, gt0, dec, dbl));
  println(wl_step(1, gt0, dec, dbl));
  return 0;
}
""",
     """4
1
""",
     ""),
    ("wl_step with zero iterations returns 0",
     r"""import "iflet.fg";
fn dec(x: int) -> int { return x - 1; }
fn gt0(x: int) -> bool { return x > 0; }
fn dbl(x: int) -> int { return x * 2; }
fn main() -> int {
  let _o: Option<int> = Option { present: false, value: 0 };
  let _r: Result<int, str> = Result { ok: false, value: 0, error: "" };
  println(wl_step(0, gt0, dec, dbl));
  println(wl_step(0 - 5, gt0, dec, dbl));
  return 0;
}
""",
     """0
0
""",
     ""),
    ("wl_step body collects through a shared buffer",
     r"""import "iflet.fg";
fn dec(x: int) -> int { return x - 1; }
fn gt0(x: int) -> bool { return x > 0; }
fn main() -> int {
  let _o: Option<int> = Option { present: false, value: 0 };
  let _r: Result<int, str> = Result { ok: false, value: 0, error: "" };
  let seen: [int] = [0, 0, 0, 0, 0];
  let collect = fn(x: int) -> int { seen[x] = seen[x] + x * 10; return x; };
  println(wl_step(4, gt0, dec, collect));
  println(seen[4]);
  println(seen[2]);
  println(seen[0]);
  return 0;
}
""",
     """4
40
20
0
""",
     ""),
    ("wl_step counts up with a custom step",
     r"""import "iflet.fg";
fn add2(x: int) -> int { return x + 2; }
fn lt10(x: int) -> bool { return x < 10; }
fn ident(x: int) -> int { return x; }
fn main() -> int {
  let _o: Option<int> = Option { present: false, value: 0 };
  let _r: Result<int, str> = Result { ok: false, value: 0, error: "" };
  println(wl_step(0, lt10, add2, ident));
  println(wl_step(8, lt10, add2, ident));
  return 0;
}
""",
     """5
1
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
    demo = os.path.join(ROOT, "examples", "iflet_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "iflet.fg")
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
