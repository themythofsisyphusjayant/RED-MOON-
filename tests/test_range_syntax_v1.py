"""Top-500 #67: range syntax in for loops (tests/test_range_syntax_v1.py).

`for i in 0..n` — half-open ranges, the `..` literal. Probes on
24 Nov 2026 said this was already implemented (catalog entry stale
at [PARTIAL]); this test proves it, including the edge shapes:
empty range (5..5), reversed range (5..0 — VERIFIED zero
iterations, not assumed), negative endpoints, expression
endpoints, nested range loops, a parameter endpoint, a function
returning the total, and range values (`let r = 2..6`,
`r.len()`/`r.sum()`, `for i in r`).

Small build in this slice (not pure verification): `0..n` in a
for loop was REJECTED on big32 ("big32: ranges are not supported
in v1") while `range()` worked as a for-loop source. big32 now
lowers a range literal as a for-loop source to the same counted
loop as `range(n)`, with the counter starting at lo and stopping
before hi. Range VALUES (`let r = a..b`, `for i in r`) are still
rejected on big32, and WASM rejects ranges outright — both are
pre-existing v1 limits, not #67 gaps. Inclusive `..=` is NOT part
of #67 (half-open only, per #18's v1 limits).

Both compilers (Python + hosted) for the native cases. big32/wasm
cases run under the Python compiler only: the hosted driver defers
emit-big32/emit-wasm and routes them to the same backends
(byte-identical emit).
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODEL_DIR = os.path.expanduser("~/workspace/big32/tools")

# (name, program, expected stdout).
OK_CASES = [
    ("1 for i in 0..5",
     r"""fn main() -> int {
  let mut total: int = 0;
  for i in 0..5 {
    total = total + i;
  }
  println(total);
  return 0;
}
""",
     "10\n"),
    ("2 variable endpoint 0..n",
     r"""fn main() -> int {
  let n: int = 4;
  let mut total: int = 0;
  for i in 0..n {
    total = total + i;
  }
  println(total);
  return 0;
}
""",
     "6\n"),
    ("3 empty range 5..5",
     r"""fn main() -> int {
  let mut total: int = 0;
  for i in 5..5 {
    total = total + 1;
  }
  println(total);
  return 0;
}
""",
     "0\n"),
    ("4 reversed range 5..0",
     r"""fn main() -> int {
  let mut total: int = 0;
  for i in 5..0 {
    total = total + 1;
  }
  println(total);
  return 0;
}
""",
     "0\n"),
    ("5 negative endpoints -3..3",
     r"""fn main() -> int {
  let mut total: int = 0;
  for i in -3..3 {
    total = total + i;
  }
  println(total);
  return 0;
}
""",
     "-3\n"),
    ("6 expression endpoints 0..n+1",
     r"""fn main() -> int {
  let n: int = 4;
  let mut total: int = 0;
  for i in 0..n + 1 {
    total = total + i;
  }
  println(total);
  return 0;
}
""",
     "10\n"),
    ("7 nested range loops",
     r"""fn main() -> int {
  let mut count: int = 0;
  for i in 0..3 {
    for j in 0..3 {
      count = count + 1;
    }
  }
  println(count);
  return 0;
}
""",
     "9\n"),
    ("8 endpoint is a function parameter",
     r"""fn sum_to(n: int) -> int {
  let mut total: int = 0;
  for i in 0..n {
    total = total + i;
  }
  return total;
}
fn main() -> int {
  println(sum_to(4));
  return 0;
}
""",
     "6\n"),
    ("9 range loop inside a function returning the total",
     r"""fn total_range() -> int {
  let mut t: int = 0;
  for i in 2..6 {
    t = t + i;
  }
  return t;
}
fn main() -> int {
  println(total_range());
  return 0;
}
""",
     "14\n"),
    ("10 range value: len, sum, iterate",
     r"""fn main() -> int {
  let r = 2..6;
  println(r.len());
  println(r.sum());
  let mut total: int = 0;
  for i in r {
    total = total + i;
  }
  println(total);
  return 0;
}
""",
     "4\n14\n14\n"),
]

# big32: (name, program, expected UART). Python compiler only.
BIG32_CASES = [
    ("big32 0..n", r"""fn main() -> int {
  let n: int = 4;
  let mut total: int = 0;
  for i in 0..n {
    total = total + i;
  }
  println(total);
  return 0;
}
""", b"6\n"),
    ("big32 empty 5..5", r"""fn main() -> int {
  let mut total: int = 0;
  for i in 5..5 {
    total = total + 1;
  }
  println(total);
  return 0;
}
""", b"0\n"),
    ("big32 reversed 5..0", r"""fn main() -> int {
  let mut total: int = 0;
  for i in 5..0 {
    total = total + 1;
  }
  println(total);
  return 0;
}
""", b"0\n"),
    ("big32 negative -3..3", r"""fn main() -> int {
  let mut total: int = 0;
  for i in -3..3 {
    total = total + i;
  }
  println(total);
  return 0;
}
""", b"-3\n"),
    ("big32 expr 0..n+1", r"""fn main() -> int {
  let n: int = 4;
  let mut total: int = 0;
  for i in 0..n + 1 {
    total = total + i;
  }
  println(total);
  return 0;
}
""", b"10\n"),
    ("big32 nested range loops", r"""fn main() -> int {
  let mut count: int = 0;
  for i in 0..3 {
    for j in 0..3 {
      count = count + 1;
    }
  }
  println(count);
  return 0;
}
""", b"9\n"),
    ("big32 range loop with labeled break", r"""fn main() -> int {
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
""", b"2\n"),
]

# Range values are still rejected on big32 (pre-existing v1 limit).
BIG32_VALUE_PROG = r"""fn main() -> int {
  let r = 2..6;
  println(r.len());
  return 0;
}
"""

# WASM rejects ranges outright (pre-existing v1 limit).
WASM_RANGE_PROG = r"""fn main() -> int {
  let mut total: int = 0;
  for i in 0..5 {
    total = total + i;
  }
  println(total);
  return 0;
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
        # big32 (Python compiler only): build, run under the model.
        sys.path.insert(0, MODEL_DIR)
        import model as big32_model
        for name, prog, uart in BIG32_CASES:
            p = os.path.join(td, "b.fg")
            with open(p, "w") as f:
                f.write(prog)
            hexpath = os.path.join(td, "b.hex")
            rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                      "build", p, "--target", "big32", "-o", os.path.join(td, "b")],
                     ROOT)
            if rb.returncode != 0:
                check(name, False, f"build rc={rb.returncode} err={rb.stderr[:200]!r}")
                failures.append(f"{name} builds")
                continue
            res = big32_model.run(hexpath)
            ok = res.get("uart", b"") == uart and res.get("halted") and res.get("a0") == 0
            if not check(name, ok, f"uart={res.get('uart', b'')!r} halted={res.get('halted')} a0={res.get('a0')}"):
                failures.append(name)
        # big32 still rejects range VALUES.
        p = os.path.join(td, "bv.fg")
        with open(p, "w") as f:
            f.write(BIG32_VALUE_PROG)
        rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--target", "big32", "-o", os.path.join(td, "bv")],
                 ROOT)
        if not check("big32 range value still rejected",
                     rr.returncode != 0 and "ranges are not supported in v1" in rr.stderr,
                     f"rc={rr.returncode} err={rr.stderr[:200]!r}"):
            failures.append("big32 range value still rejected")
        # WASM still rejects ranges outright.
        p = os.path.join(td, "w.fg")
        with open(p, "w") as f:
            f.write(WASM_RANGE_PROG)
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "emit-wasm", p, "-o", os.path.join(td, "w.wasm")], ROOT)
        if not check("wasm rejects ranges",
                     rw.returncode != 0 and "ranges are not supported in v1" in rw.stderr,
                     f"rc={rw.returncode} err={rw.stderr[:200]!r}"):
            failures.append("wasm rejects ranges")
    if failures:
        print(f"FAILURES ({len(failures)}): {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
