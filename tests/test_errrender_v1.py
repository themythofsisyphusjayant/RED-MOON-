"""Top-500 #54: structured error rendering (tests/test_errrender_v1.py).

miette-style snippets and labels as pure string functions in
forge_lang/stdlib/errrender.fg: render_snippet shows one source
line with its line number, a caret underline and a label;
render_error composes the full block (code, message,
file:line:col header plus snippet). The caller supplies the
source text — the renderer never reads files. Out-of-range
line/col/span are clamped, never fatal.

v1 limits (named in the catalog): single-line spans only (no
multi-line underline), no colour/ANSI output, no file reading,
no severity or help-note lines yet. Both compilers (Python +
hosted). Runs use cwd=ROOT (like test_errcode_v1.py): the
hosted binary resolves stdlib imports relative to the repo
root (forge_lang/stdlib/), so a temp cwd would break every
import. Nothing is written to the tree.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """E001: unexpected token
  --> src/main.fg:1:9
1 | let x = foo(;
  |         ^^^ expected ')'
2 | let y = 2;
  |     ^
2 | let y = 2;
  |           ^ clamped
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("snippet basic, 1-digit line",
     r"""import "errrender.fg";
fn main() -> int {
  println(render_snippet("let x = foo(;", 1, 9, 3, "expected ')'"));
  return 0;
}
""",
     """1 | let x = foo(;
  |         ^^^ expected ')'
""",
     ""),
    ("two-digit line widens the gutter",
     r"""import "errrender.fg";
fn main() -> int {
  let src: str = "l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\nl10\nl11";
  println(render_snippet(src, 10, 1, 1, ""));
  return 0;
}
""",
     """10 | l10
   | ^
""",
     ""),
    ("line 0, col 0 and span 0 all clamp to 1",
     r"""import "errrender.fg";
fn main() -> int {
  println(render_snippet("abc", 0, 0, 0, ""));
  return 0;
}
""",
     """1 | abc
  | ^
""",
     ""),
    ("col past end clamps, span trims to the line end",
     r"""import "errrender.fg";
fn main() -> int {
  println(render_snippet("abc", 1, 99, 5, "end"));
  return 0;
}
""",
     """1 | abc
  |    ^ end
""",
     ""),
    ("span trims at the line end",
     r"""import "errrender.fg";
fn main() -> int {
  println(render_snippet("abcdef", 1, 4, 99, "tail"));
  return 0;
}
""",
     """1 | abcdef
  |    ^^^ tail
""",
     ""),
    ("render_error composes the full block",
     r"""import "errrender.fg";
fn main() -> int {
  let src: str = "let a = 1;\nfoo(bar);";
  println(render_error("E002", "name not found", "lib/util.fg", src, 2, 5, 3, "unknown name"));
  return 0;
}
""",
     """E002: name not found
  --> lib/util.fg:2:5
2 | foo(bar);
  |     ^^^ unknown name
""",
     ""),
    ("render_error clamps an out-of-range line in the header too",
     r"""import "errrender.fg";
fn main() -> int {
  println(render_error("E003", "oops", "f.fg", "only one", 7, 2, 1, ""));
  return 0;
}
""",
     """E003: oops
  --> f.fg:1:2
1 | only one
  |  ^
""",
     ""),
    ("er_int_str handles 0, positive and negative",
     r"""import "errrender.fg";
fn main() -> int {
  println(er_int_str(0));
  println(er_int_str(42));
  println(er_int_str(-7));
  return 0;
}
""",
     """0
42
-7
""",
     ""),
    ("er_line_text returns the clamped line",
     r"""import "errrender.fg";
fn main() -> int {
  println(er_line_text("a\nb\nc", 9));
  println(er_line_text("a\nb\nc", 1));
  return 0;
}
""",
     """c
a
""",
     ""),
    ("empty label omits the suffix",
     r"""import "errrender.fg";
fn main() -> int {
  println(er_spaces(3) + "x");
  println(render_snippet("xy", 1, 2, 1, ""));
  return 0;
}
""",
     """   x
1 | xy
  |  ^
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
    demo = os.path.join(ROOT, "examples", "errrender_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "errrender.fg")
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
