"""Top-500 #342: multi-error reporting (tests/test_multireport_v1.py).

Aggregate checker-style errors into one report in
forge_lang/stdlib/multireport.fg: MultiError holds parallel arrays
(codes, messages, files, lines, cols); mr_add is the only writer,
so the arrays stay in sync, and it returns a new value — the input
is unchanged. mr_render prints a "N errors:" header plus numbered
"[E001] message (file:line:col)" lines; mr_json renders the same
report as JSON via errors_to_json from errjson.fg (#341).

v1 limits (named in the catalog): library-side ONLY — it does NOT
hook the checker (the checker still emits plain text, first error
only); parallel arrays must stay in sync (mr_add is the only
writer). Both compilers (Python + hosted). Runs use cwd=ROOT (like
test_errrender_v1.py): the hosted binary resolves stdlib imports
relative to the repo root (forge_lang/stdlib/), so a temp cwd would
break every import. Nothing is written to the tree.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """2 errors:
1. [E001] unexpected token (src/main.fg:1:9)
2. [E002] name not found (lib/util.fg:2:5)
{"errors":[{"code":"E001","message":"unexpected token","file":"src/main.fg","line":1,"col":9},{"code":"E002","message":"name not found","file":"lib/util.fg","line":2,"col":5}]}
0 errors:
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("empty report renders zero and empty json",
     r"""import "multireport.fg";
fn main() -> int {
  let m: MultiError = mr_new();
  println(mr_count(m));
  println(mr_render(m));
  println(mr_json(m));
  return 0;
}
""",
     """0
0 errors:
{"errors":[]}
""",
     ""),
    ("one error, count and render",
     r"""import "multireport.fg";
fn main() -> int {
  let mut m: MultiError = mr_new();
  m = mr_add(m, "E001", "unexpected token", "src/main.fg", 1, 9);
  println(mr_count(m));
  println(mr_render(m));
  return 0;
}
""",
     """1
1 errors:
1. [E001] unexpected token (src/main.fg:1:9)
""",
     ""),
    ("three errors render numbered in insertion order",
     r"""import "multireport.fg";
fn main() -> int {
  let mut m: MultiError = mr_new();
  m = mr_add(m, "E002", "second", "b.fg", 2, 2);
  m = mr_add(m, "E001", "first", "a.fg", 1, 1);
  m = mr_add(m, "E003", "third", "c.fg", 3, 3);
  println(mr_render(m));
  return 0;
}
""",
     """3 errors:
1. [E002] second (b.fg:2:2)
2. [E001] first (a.fg:1:1)
3. [E003] third (c.fg:3:3)
""",
     ""),
    ("mr_add does not change its input",
     r"""import "multireport.fg";
fn main() -> int {
  let m: MultiError = mr_new();
  let m2: MultiError = mr_add(m, "E001", "one", "a.fg", 1, 1);
  println(mr_count(m));
  println(mr_count(m2));
  println(mr_render(m2));
  return 0;
}
""",
     """0
1
1 errors:
1. [E001] one (a.fg:1:1)
""",
     ""),
    ("mr_json escapes quotes in the message",
     r"""import "multireport.fg";
fn main() -> int {
  let mut m: MultiError = mr_new();
  m = mr_add(m, "E001", "undefined variable \"total\"", "main.fg", 7, 1);
  println(mr_json(m));
  return 0;
}
""",
     "{\"errors\":[{\"code\":\"E001\",\"message\":\"undefined variable \\\"total\\\"\",\"file\":\"main.fg\",\"line\":7,\"col\":1}]}\n",
     ""),
    ("negative line and col render in text and json",
     r"""import "multireport.fg";
fn main() -> int {
  let mut m: MultiError = mr_new();
  m = mr_add(m, "E001", "m", "f.fg", -1, -2);
  println(mr_render(m));
  println(mr_json(m));
  return 0;
}
""",
     """1 errors:
1. [E001] m (f.fg:-1:-2)
{"errors":[{"code":"E001","message":"m","file":"f.fg","line":-1,"col":-2}]}
""",
     ""),
    ("mr_render and mr_json agree on the same report",
     r"""import "multireport.fg";
fn main() -> int {
  let mut m: MultiError = mr_new();
  m = mr_add(m, "E001", "unexpected token", "src/main.fg", 1, 9);
  m = mr_add(m, "E002", "name not found", "lib/util.fg", 2, 5);
  println(mr_render(m));
  println(mr_json(m));
  println(mr_count(m));
  return 0;
}
""",
     """2 errors:
1. [E001] unexpected token (src/main.fg:1:9)
2. [E002] name not found (lib/util.fg:2:5)
{"errors":[{"code":"E001","message":"unexpected token","file":"src/main.fg","line":1,"col":9},{"code":"E002","message":"name not found","file":"lib/util.fg","line":2,"col":5}]}
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
    demo = os.path.join(ROOT, "examples", "multireport_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "multireport.fg")
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
