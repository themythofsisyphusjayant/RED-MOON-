"""Top-500 #62: labeled break/continue, Go-style (tests/test_labeled_break_v1.py).

`outer: for ... { break outer; }` / `continue outer;` — a label prefix
on a loop, no new lexer token. v1 is loops only (no labeled blocks).
Labels are function-scoped in their own namespace (a label may share a
name with a variable); an inner loop may shadow an outer label name
(inner wins while in scope); there is NO duplicate-label error for
loops — a sibling loop may reuse a name too; a labeled break/continue inside a
nested function/closure must NOT see the outer function's labels
(the label stack resets on fn entry, like loop_depth).

The hard part is break-across-frames cleanup: a labeled break runs
cleanup for EVERY frame between the labeled loop and the innermost
(defers downto the labeled loop's defer frame, scope joins at each
crossed depth, frame frees downto the labeled loop's frame), then
`goto`s a per-loop end label — a bare C `break;` cannot do this. A
labeled continue jumps to the labeled loop's continue label (for: the
increment step; while: the condition re-check) after the same
cleanup. Unlabeled break/continue keep exactly today's behaviour.

Both compilers (Python + hosted). big32/wasm cases run under the
Python compiler only: the hosted driver defers emit-big32/emit-wasm
and routes them to the same backends (byte-identical emit).
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODEL_DIR = os.path.expanduser("~/workspace/big32/tools")

DEMO_EXPECTED = """2
5
"""

# (name, program, expected stdout).
OK_CASES = [
    ("1 break outer from inner (range for)",
     r"""fn main() -> int {
  let mut total: int = 0;
  outer: for i in 0..5 {
    for j in 0..5 {
      if j == 2 {
        break outer;
      }
      total = total + 1;
    }
  }
  println(total);
  return 0;
}
""",
     "2\n"),
    ("2 continue outer from inner (range for)",
     r"""fn main() -> int {
  let mut total: int = 0;
  outer: for i in 0..5 {
    for j in 0..3 {
      if j == 1 {
        continue outer;
      }
      total = total + 1;
    }
  }
  println(total);
  return 0;
}
""",
     "5\n"),
    ("3 break to innermost label",
     r"""fn main() -> int {
  let mut total: int = 0;
  outer: for i in 0..3 {
    inner: for j in 0..5 {
      if j == 2 {
        break inner;
      }
      total = total + 1;
    }
  }
  println(total);
  return 0;
}
""",
     "6\n"),
    ("4 continue to innermost label",
     r"""fn main() -> int {
  let mut total: int = 0;
  outer: for i in 0..3 {
    inner: for j in 0..5 {
      if j == 1 {
        continue inner;
      }
      total = total + 1;
    }
  }
  println(total);
  return 0;
}
""",
     "12\n"),
    ("5 unlabeled nested break unchanged",
     r"""fn main() -> int {
  let mut total: int = 0;
  for i in 0..3 {
    for j in 0..5 {
      if j == 2 {
        break;
      }
      total = total + 1;
    }
  }
  println(total);
  return 0;
}
""",
     "6\n"),
    ("6 break outer from inner while",
     r"""fn main() -> int {
  let mut i: int = 0;
  let mut total: int = 0;
  outer: while i < 5 {
    i = i + 1;
    let mut j: int = 0;
    while j < 5 {
      j = j + 1;
      if j == 2 {
        break outer;
      }
      total = total + 1;
    }
  }
  println(total);
  return 0;
}
""",
     "1\n"),
    ("7 continue outer from inner while",
     r"""fn main() -> int {
  let mut i: int = 0;
  let mut total: int = 0;
  outer: while i < 5 {
    i = i + 1;
    let mut j: int = 0;
    while j < 5 {
      j = j + 1;
      if j == 3 {
        continue outer;
      }
      total = total + 1;
    }
  }
  println(total);
  return 0;
}
""",
     "10\n"),
    ("8 unlabeled while break/continue unchanged",
     r"""fn main() -> int {
  let mut i: int = 0;
  let mut total: int = 0;
  while i < 3 {
    i = i + 1;
    let mut j: int = 0;
    while j < 5 {
      j = j + 1;
      if j == 2 {
        break;
      }
      total = total + 1;
    }
  }
  println(total);
  return 0;
}
""",
     "3\n"),
    ("9 defer runs on labeled break out of inner body",
     r"""fn bump() {
  println("deferred");
}
fn main() -> int {
  outer: for i in 0..3 {
    for j in 0..3 {
      defer bump();
      if j == 1 {
        break outer;
      }
      println("body");
    }
  }
  println("done");
  return 0;
}
""",
     "body\ndeferred\ndeferred\ndone\n"),
    ("10 defer runs on labeled continue out of inner body",
     r"""fn bump() {
  println("deferred");
}
fn main() -> int {
  outer: for i in 0..3 {
    for j in 0..3 {
      defer bump();
      if j == 1 {
        continue outer;
      }
      println("body");
    }
  }
  println("done");
  return 0;
}
""",
     "body\ndeferred\ndeferred\nbody\ndeferred\ndeferred\nbody\ndeferred\ndeferred\ndone\n"),
    ("11 labeled break out of a branch, owned local in body",
     r"""fn main() -> int {
  let mut total: int = 0;
  outer: for i in 0..3 {
    for j in 0..5 {
      let s: str = "x";
      if j == 2 {
        println(s);
        break outer;
      }
      total = total + 1;
    }
  }
  println(total);
  return 0;
}
""",
     "x\n2\n"),
    ("12 inner label shadows outer label (inner wins)",
     r"""fn main() -> int {
  let mut total: int = 0;
  outer: for i in 0..3 {
    outer: for j in 0..3 {
      if j == 1 {
        break outer;
      }
      total = total + 1;
    }
    total = total + 10;
  }
  println(total);
  return 0;
}
""",
     "33\n"),
    ("13 label shares a name with a variable",
     r"""fn main() -> int {
  let outer: int = 7;
  let mut total: int = 0;
  outer: for i in 0..3 {
    for j in 0..3 {
      if j == 1 {
        break outer;
      }
      total = total + 1;
    }
  }
  println(outer);
  println(total);
  return 0;
}
""",
     "7\n1\n"),
    ("14 sibling loops may reuse a label",
     r"""fn main() -> int {
  let mut total: int = 0;
  outer: for i in 0..3 {
    if i == 1 {
      break outer;
    }
    total = total + 1;
  }
  outer: for i in 0..3 {
    total = total + 1;
  }
  println(total);
  return 0;
}
""",
     "4\n"),
    ("15 labeled break over an array for-loop",
     r"""fn main() -> int {
  let xs: [int] = [10, 20, 30, 40];
  let ys: [int] = [1, 2, 3];
  let mut total: int = 0;
  outer: for x in xs {
    for y in ys {
      if y == 2 {
        break outer;
      }
      total = total + x;
    }
  }
  println(total);
  return 0;
}
""",
     "10\n"),
    ("16 labeled continue over an array for-loop",
     r"""fn main() -> int {
  let xs: [int] = [10, 20];
  let ys: [int] = [1, 2, 3];
  let mut total: int = 0;
  outer: for x in xs {
    for y in ys {
      if y == 2 {
        continue outer;
      }
      total = total + x;
    }
  }
  println(total);
  return 0;
}
""",
     "30\n"),
    ("17 labeled break out of a scope block inside the loop",
     r"""fn main() -> int {
  let mut total: int = 0;
  outer: for i in 0..3 {
    for j in 0..3 {
      scope {
        let s: str = "in";
        if j == 1 {
          println(s);
          break outer;
        }
      }
      total = total + 1;
    }
  }
  println(total);
  return 0;
}
""",
     "in\n1\n"),
]

# (name, program, error fragment in stderr).
ERR_CASES = [
    ("E1 unknown break label",
     r"""fn main() -> int {
  for i in 0..3 {
    break nope;
  }
  return 0;
}
""",
     "break label 'nope' does not name an enclosing loop"),
    ("E2 unknown continue label",
     r"""fn main() -> int {
  for i in 0..3 {
    continue nope;
  }
  return 0;
}
""",
     "continue label 'nope' does not name an enclosing loop"),
    ("E4 labeled break outside any loop",
     r"""fn main() -> int {
  break outer;
  return 0;
}
""",
     "break label 'outer' does not name an enclosing loop"),
    ("E5 label across a closure boundary (lambda inside the loop)",
     r"""fn main() -> int {
  outer: for i in 0..3 {
    let f = fn(x: int) -> int {
      break outer;
      return x;
    };
    println(f(i));
  }
  return 0;
}
""",
     "break label 'outer' does not name an enclosing loop"),
    ("E6 label must prefix a loop",
     r"""fn main() -> int {
  foo: println(1);
  return 0;
}
""",
     "label 'foo' must prefix a 'while' or 'for' loop (labels attach to loops only in v1)"),
    ("E7 unlabeled break outside a loop (old error kept)",
     r"""fn main() -> int {
  break;
  return 0;
}
""",
     "break outside a loop"),
    ("E8 unlabeled continue outside a loop (old error kept)",
     r"""fn main() -> int {
  continue;
  return 0;
}
""",
     "continue outside a loop"),
]

# big32: array for-loop, labeled break (Python compiler only).
BIG32_PROG = r"""fn main() -> int {
  let xs: [int] = [10, 20, 30, 40];
  let ys: [int] = [1, 2, 3];
  let mut total: int = 0;
  outer: for x in xs {
    for y in ys {
      if y == 2 {
        break outer;
      }
      total = total + x;
    }
  }
  println(total);
  return 0;
}
"""

# wasm: main returns the total (the node runner prints main's
# return value). Python compiler only.
WASM_CONT_PROG = r"""fn main() -> int {
  let mut i: int = 0;
  let mut total: int = 0;
  outer: while i < 5 {
    i = i + 1;
    let mut j: int = 0;
    while j < 5 {
      j = j + 1;
      if j == 3 {
        continue outer;
      }
      total = total + 1;
    }
  }
  return total;
}
"""

WASM_BREAK_PROG = r"""fn main() -> int {
  let mut i: int = 0;
  let mut total: int = 0;
  outer: while i < 5 {
    i = i + 1;
    let mut j: int = 0;
    while j < 5 {
      j = j + 1;
      if j == 2 {
        break outer;
      }
      total = total + 1;
    }
  }
  return total;
}
"""


def run(args, cwd, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    # The #50 slice found forge.py honors ambient
    # QASIDA_COMPILER; scrub it so "hosted" runs are hosted.
    e.pop("QASIDA_COMPILER", None)
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=e)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "labeled_break_demo.fg")
    for mode, prefix in (("hosted", []), ("python", ["--python"])):
        r = run([sys.executable, os.path.join(ROOT, "forge.py")] + prefix +
                ["run", demo], ROOT)
        if not check(f"demo runs ({mode})", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append(f"demo runs ({mode})")
        elif not check(f"demo results ({mode})", r.stdout == DEMO_EXPECTED,
                       repr(r.stdout)):
            failures.append(f"demo results ({mode})")
    with tempfile.TemporaryDirectory() as td:
        for name, prog, want in OK_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                if not check(f"{name} ({mode})", rr.returncode == 0 and rr.stdout == want,
                             f"rc={rr.returncode} out={rr.stdout!r} err={rr.stderr[:200]!r}"):
                    failures.append(f"{name} ({mode})")
        for name, prog, frag in ERR_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = rr.returncode != 0 and frag in rr.stderr
                if not check(f"{name} ({mode})", ok,
                             f"rc={rr.returncode} err={rr.stderr[:200]!r}"):
                    failures.append(f"{name} ({mode})")
        # big32 (Python compiler only): build, run under the model.
        p = os.path.join(td, "b.fg")
        with open(p, "w") as f:
            f.write(BIG32_PROG)
        hexpath = os.path.join(td, "b.hex")
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--target", "big32", "-o", os.path.join(td, "b")],
                 ROOT)
        if not check("big32 labeled break builds", rb.returncode == 0,
                     rb.stderr[:200]):
            failures.append("big32 labeled break builds")
        else:
            sys.path.insert(0, MODEL_DIR)
            import model as big32_model
            res = big32_model.run(hexpath)
            ok = res.get("uart", b"") == b"10\n" and res.get("halted") and res.get("a0") == 0
            if not check("big32 labeled break runs (uart 10, halted, a0=0)", ok,
                         repr(res.get("uart", b""))):
                failures.append("big32 labeled break runs")
        # wasm (Python compiler only): emit + node runner.
        for name, prog, want in (("wasm labeled continue", WASM_CONT_PROG, "10"),
                                  ("wasm labeled break", WASM_BREAK_PROG, "1")):
            p = os.path.join(td, "w.fg")
            with open(p, "w") as f:
                f.write(prog)
            out = os.path.join(td, "w.wasm")
            rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                      "emit-wasm", p, "-o", out], ROOT)
            if not check(f"{name} emits", rw.returncode == 0, rw.stderr[:200]):
                failures.append(f"{name} emits")
                continue
            rn = subprocess.run(["node", os.path.join(ROOT, "tools", "run_wasm.mjs"), out],
                                capture_output=True, text=True)
            if not check(name, rn.returncode == 0 and rn.stdout.strip() == want,
                         f"got {rn.stdout.strip()!r} err={rn.stderr[:200]!r}"):
                failures.append(name)
    if failures:
        print(f"FAILURES ({len(failures)}): {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
