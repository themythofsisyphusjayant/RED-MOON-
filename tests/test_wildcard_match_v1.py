"""Top-500 #76: wildcard match arm (tests/test_wildcard_match_v1.py).

`match c { Red => { ... } _ => { println("other"); } }` — the
wildcard arm is the default. Probes on 24 Nov 2026 said this was
already implemented (catalog entry stale at [GAP]); the suite
already exercises it (`examples/enums_match.fg` uses `_ =>`).
This test proves it: enum wildcard hit + miss, union wildcard
(hit + miss), the three error rules (wildcard must be last,
wildcard cannot bind a value, non-exhaustive without a wildcard
still errors — for enums, unions, and the #50 narrowed-error-set
path), and the wildcard over an inferred error set.

Two pre-existing message divergences, NOT #76 gaps (both
compilers reject the program; only the spelling differs):
- Hosted UNION-path exhaustiveness message is bare ("match is
  not exhaustive", selfhost_check.fg:5137) while Python appends
  "; missing: <members>" (checker.py:2311). The test asserts the
  common fragment. (The hosted ENUM-path phase-2 message DOES
  carry the missing list, and the narrowed-error-set case agrees
  exactly in both compilers.)
- WASM has no match/enum support at all: the enum value fails
  first as "undefined variable 'Green'". The test asserts only
  rejection, not the message.

Both compilers (Python + hosted) for the native cases. big32/wasm
cases run under the Python compiler only: the hosted driver defers
emit-big32/emit-wasm and routes them to the same backends
(byte-identical emit). big32 rejects match/enums entirely and
WASM has no match support — pre-existing backend limits, not
#76 gaps.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (name, program, expected stdout).
OK_CASES = [
    ("1 enum wildcard hit",
     r"""enum Color { Red, Green, Blue }
fn main() -> int {
  let c: Color = Red;
  match c {
    Red => {
      println("red");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "red\n"),
    ("2 enum wildcard miss",
     r"""enum Color { Red, Green, Blue }
fn main() -> int {
  let c: Color = Green;
  match c {
    Red => {
      println("red");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "other\n"),
    ("3 enum wildcard miss with two named arms",
     r"""enum Color { Red, Green, Blue }
fn main() -> int {
  let c: Color = Blue;
  match c {
    Red => {
      println("red");
    }
    Green => {
      println("green");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "other\n"),
    ("4 union wildcard miss (int arm hits)",
     r"""fn main() -> int {
  let u: int | str = 5;
  match u {
    int(v) => {
      println(v);
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "5\n"),
    ("5 union wildcard hit (str value)",
     r"""fn main() -> int {
  let u: int | str = "hi";
  match u {
    int(v) => {
      println(v);
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
""",
     "other\n"),
    ("6 wildcard over an inferred error set",
     r"""import "result.fg";
import "errcode.fg";
fn read_maybe(x: int) -> Result<int, ErrCode> {
  if x == 0 {
    return Result { ok: false, value: 0, error: NotFound };
  }
  if x < 0 {
    return Result { ok: false, value: 0, error: TimedOut };
  }
  return Result { ok: true, value: x, error: Success };
}
fn caller(x: int) -> Result<int, ErrCode> {
  let v: int = read_maybe(x)?;
  return Result { ok: true, value: v * 2, error: Success };
}
fn main() -> int {
  let r: Result<int, ErrCode> = caller(0);
  if !r.ok {
    match r.error {
      NotFound => {
        println("not found");
      }
      _ => {
        println("other err");
      }
    }
  }
  let r2: Result<int, ErrCode> = caller(-1);
  if !r2.ok {
    match r2.error {
      NotFound => {
        println("not found");
      }
      _ => {
        println("other err");
      }
    }
  }
  return 0;
}
""",
     "not found\nother err\n"),
]

# (name, program, error fragment in stderr).
ERR_CASES = [
    ("E1 wildcard must be last",
     r"""enum Color { Red, Green, Blue }
fn main() -> int {
  let c: Color = Green;
  match c {
    _ => {
      println("other");
    }
    Red => {
      println("red");
    }
  }
  return 0;
}
""",
     "match wildcard '_' must be the last arm"),
    ("E2 wildcard cannot bind a value",
     r"""enum Color { Red, Green, Blue }
fn main() -> int {
  let c: Color = Green;
  match c {
    Red => {
      println("red");
    }
    _(v) => {
      println(v);
    }
  }
  return 0;
}
""",
     "wildcard arm cannot bind a value"),
    ("E3 non-exhaustive enum without a wildcard still errors",
     r"""enum Color { Red, Green, Blue }
fn main() -> int {
  let c: Color = Green;
  match c {
    Red => {
      println("red");
    }
  }
  return 0;
}
""",
     "match is not exhaustive; missing: Green"),
    ("E4 non-exhaustive union without a wildcard still errors",
     r"""fn main() -> int {
  let u: int | str = 5;
  match u {
    int(v) => {
      println(v);
    }
  }
  return 0;
}
""",
     # Hosted union-path message is bare (see module docstring);
     # the common fragment is asserted for both compilers.
     "match is not exhaustive"),
    ("E5 narrowed error set without a wildcard still errors",
     r"""import "result.fg";
import "errcode.fg";
fn read_maybe(x: int) -> Result<int, ErrCode> {
  if x == 0 {
    return Result { ok: false, value: 0, error: NotFound };
  }
  if x < 0 {
    return Result { ok: false, value: 0, error: TimedOut };
  }
  return Result { ok: true, value: x, error: Success };
}
fn caller(x: int) -> Result<int, ErrCode> {
  let v: int = read_maybe(x)?;
  return Result { ok: true, value: v * 2, error: Success };
}
fn main() -> int {
  let r: Result<int, ErrCode> = caller(0);
  if !r.ok {
    match r.error {
      NotFound => {
        println("not found");
      }
    }
  }
  return 0;
}
""",
     # Narrowing is engaged: only TimedOut is missing, not the
     # other 13 ErrCode variants. Both compilers agree exactly.
     "match is not exhaustive; missing: TimedOut"),
]

# Backend rejections (pre-existing limits, Python compiler only).
BIG32_MATCH_PROG = r"""enum Color { Red, Green, Blue }
fn main() -> int {
  let c: Color = Green;
  match c {
    Red => {
      println("red");
    }
    _ => {
      println("other");
    }
  }
  return 0;
}
"""
WASM_MATCH_PROG = BIG32_MATCH_PROG


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
        # big32 rejects match/enums entirely (enum decl fails first).
        p = os.path.join(td, "b.fg")
        with open(p, "w") as f:
            f.write(BIG32_MATCH_PROG)
        rb = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "build", p, "--target", "big32", "-o", os.path.join(td, "b")],
                 ROOT)
        if not check("big32 rejects match",
                     rb.returncode != 0 and "enums are not supported on big32" in rb.stderr,
                     f"rc={rb.returncode} err={rb.stderr[:200]!r}"):
            failures.append("big32 rejects match")
        # WASM has no match/enum support (enum value fails first).
        p = os.path.join(td, "w.fg")
        with open(p, "w") as f:
            f.write(WASM_MATCH_PROG)
        rw = run([sys.executable, os.path.join(ROOT, "forge.py"), "--python",
                  "emit-wasm", p, "-o", os.path.join(td, "w.wasm")], ROOT)
        if not check("wasm rejects match", rw.returncode != 0,
                     f"rc={rw.returncode} err={rw.stderr[:200]!r}"):
            failures.append("wasm rejects match")
    if failures:
        print(f"FAILURES ({len(failures)}): {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
