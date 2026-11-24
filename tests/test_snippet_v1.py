"""Top-500 #345: source snippets with context lines (tests/test_snippet_v1.py).

Multi-line source-snippet rendering in forge_lang/stdlib/snippet.fg,
built on errrender.fg (#54): render_snippet_ctx renders the error
line as render_snippet does (gutter-aligned line number, caret
underline and label) plus up to `before` context lines above and
`after` below (same gutter width, no carets); render_error_ctx
composes the full block (code, message, file:line:col header plus
the context snippet). Line numbers are right-aligned to the width
of the largest line number shown. A span running past the end of
the error line is clamped to the line end and the caret line gains
a "(+N more lines)" note counting how many following lines the
span would have reached. Out-of-range line/col/span and context
counts are clamped, never fatal.

v1 limits (named in the catalog): single-line caret underline only
(the span never underlines across lines — the "(+N more lines)"
note is the only multi-line signal); pure string functions over
caller-supplied source; no file reading; no colour/ANSI output.
Both compilers (Python + hosted). Runs use cwd=ROOT (like
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

DEMO_EXPECTED = """E001: unexpected token
  --> src/main.fg:2:9
1 | let x = 1;
2 | let y = foo(;
  |         ^^^ expected ')'
3 | let z = 3;
3 | let z = 3;
  |     ^
2 | let y = foo(;
  |         ^^^^^ tail (+2 more lines)
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("context lines above and below",
     r"""import "snippet.fg";
fn main() -> int {
  let src: str = "let x = 1;\nlet y = foo(;\nlet z = 3;\nlet w = 4;";
  println(render_snippet_ctx(src, 2, 9, 3, "expected ')'", 1, 1));
  return 0;
}
""",
     """1 | let x = 1;
2 | let y = foo(;
  |         ^^^ expected ')'
3 | let z = 3;
""",
     ""),
    ("two-digit line widens the gutter, numbers right-aligned",
     r"""import "snippet.fg";
fn main() -> int {
  let src: str = "l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\nl10\nl11";
  println(render_snippet_ctx(src, 10, 1, 1, "", 1, 1));
  return 0;
}
""",
     """ 9 | l9
10 | l10
   | ^
11 | l11
""",
     ""),
    ("line, col, span and context counts all clamp",
     r"""import "snippet.fg";
fn main() -> int {
  println(render_snippet_ctx("abc", 99, 99, 0, "clamped", -1, -5));
  return 0;
}
""",
     """1 | abc
  |    ^ clamped
""",
     ""),
    ("span past the line end clamps and notes more lines",
     r"""import "snippet.fg";
fn main() -> int {
  let src: str = "let x = 1;\nlet y = foo(;\nlet z = 3;\nlet w = 4;";
  println(render_snippet_ctx(src, 2, 9, 99, "tail", 0, 0));
  return 0;
}
""",
     """2 | let y = foo(;
  |         ^^^^^ tail (+2 more lines)
""",
     ""),
    ("span ending exactly at the line end gets no note",
     r"""import "snippet.fg";
fn main() -> int {
  println(render_snippet_ctx("abcdef", 1, 4, 3, "tail", 0, 0));
  return 0;
}
""",
     """1 | abcdef
  |    ^^^ tail
""",
     ""),
    ("render_error_ctx composes the full block",
     r"""import "snippet.fg";
fn main() -> int {
  let src: str = "let a = 1;\nfoo(bar);";
  println(render_error_ctx("E002", "name not found", "lib/util.fg", src, 2, 5, 3, "unknown name", 1, 0));
  return 0;
}
""",
     """E002: name not found
  --> lib/util.fg:2:5
1 | let a = 1;
2 | foo(bar);
  |     ^^^ unknown name
""",
     ""),
    ("empty source still renders the clamped first line",
     r"""import "snippet.fg";
fn main() -> int {
  println(render_snippet_ctx("", 1, 1, 1, "", 1, 1));
  return 0;
}
""",
     """1 | 
  | ^
""",
     ""),
    ("context clamps at the start of the file",
     r"""import "snippet.fg";
fn main() -> int {
  let src: str = "let x = 1;\nlet y = foo(;\nlet z = 3;";
  println(render_snippet_ctx(src, 1, 2, 1, "", 5, 1));
  return 0;
}
""",
     """1 | let x = 1;
  |  ^
2 | let y = foo(;
""",
     ""),
    ("context clamps at the end of the file",
     r"""import "snippet.fg";
fn main() -> int {
  let src: str = "let x = 1;\nlet y = foo(;\nlet z = 3;\nlet w = 4;";
  println(render_snippet_ctx(src, 4, 5, 1, "", 1, 5));
  return 0;
}
""",
     """3 | let z = 3;
4 | let w = 4;
  |     ^
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
    demo = os.path.join(ROOT, "examples", "snippet_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "snippet.fg")
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
