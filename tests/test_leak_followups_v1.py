"""Leak follow-ups (tests/test_leak_followups_v1.py).

Three measured leaks from the 22 Nov filesystem slice + the 23 Nov
generic-inc fix, fixed in BOTH compilers:

1. Enum scope-end freeing + match-arm binding freeing: a let-bound
   payload enum was never freed at scope end (_emit_free_one had no
   enum case) and a match arm's str binding (an independent copy)
   was never freed at arm end. The torture program's only remaining
   leaks were exactly these: 24 bytes in 2 allocations.
2. Index into a fresh array/struct and FieldAccess on a fresh
   struct leaked the fresh base (e.g. len(f()[0]) / f().field).
3. Return inside a for-over-fresh loop leaked the iterable (the
   loop's fresh array was never freed on the early return path).

Plus the construction side Fix 1 forces (§2a): a variant
construction must OWN its payload (concrete payload type), or
the scope-end free frees a borrowed value — a generic str
payload segfaulted freeing a string literal, a shared array
payload double-freed (both found by the suite gate, 23 Nov).

Each probe below runs under BOTH compilers (exact stdout), and the
ASan section compiles the same probes with -fsanitize=address
(leak detection ON) and asserts zero leaks. stdout is checked on
the plain binary because LeakSanitizer's _exit discards buffered
stdout. The q3 block-let shadowing probe is a runtime case ONLY:
shadowing an outer variable with a block let still leaks 6 bytes
(pre-existing, out of scope — the arm-frame rule matches it).
The q1/q2/q4/q5 probes are checker REJECTIONS (fresh IndexAssign
/ FieldAssign, tuple arrays, enum arrays), asserted as such.
Both compilers (Python + hosted); emit must be byte-identical
(checked by the parity gate, not here).
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (name, source, expected stdout) — runtime cases, both compilers.
OK_CASES = [
    ("p1 enum scope (torture core)",
     r"""enum Msg { Text(str), Num(int) }

fn main() -> int {
  let m = Text("hello " + "world");
  match m {
    Text(s) => {
      println(s);
    }
    Num(n) => {
      println(n);
    }
  }
  return 0;
}
""",
     "hello world\n"),
    ("p2 index into fresh [str]",
     r"""fn words() -> [str] {
  return ["aa", "bb"];
}

fn main() -> int {
  println(words()[0]);
  println(len(words()));
  return 0;
}
""",
     "aa\n2\n"),
    ("p3 index into fresh [int]",
     r"""fn nums() -> [int] {
  return [10, 20, 30];
}

fn main() -> int {
  println(nums()[1]);
  return 0;
}
""",
     "20\n"),
    ("p4 index into fresh [Point] + field of element",
     r"""struct Point { x: int, label: str }

fn pts() -> [Point] {
  return [Point { x: 5, label: "p" }];
}

fn main() -> int {
  let q = pts()[0];
  println(q.x);
  println(q.label);
  println(pts()[0].x);
  return 0;
}
""",
     "5\np\n5\n"),
    ("p5 field of fresh struct (str)",
     r"""struct Named { name: str, v: int }

fn mk() -> Named {
  return Named { name: "nm", v: 7 };
}

fn main() -> int {
  println(mk().name);
  println(mk().v);
  return 0;
}
""",
     "nm\n7\n"),
    ("p6 field of fresh struct (array)",
     r"""struct Bag { xs: [int], n: int }

fn mk() -> Bag {
  return Bag { xs: [1, 2, 3], n: 3 };
}

fn main() -> int {
  println(len(mk().xs));
  return 0;
}
""",
     "3\n"),
    ("p7 return inside for-over-fresh",
     r"""fn first() -> int {
  for x in [10, 20, 30] {
    return x;
  }
  return -1;
}

fn main() -> int {
  println(first());
  return 0;
}
""",
     "10\n"),
    ("p8 enum sharing (let copy + call args)",
     r"""enum Msg { Text(str), Num(int) }

fn show(m: Msg) -> int {
  match m {
    Text(s) => {
      println(s);
      return 1;
    }
    Num(n) => {
      println(n);
      return 2;
    }
  }
  return 0;
}

fn main() -> int {
  let m = Text("shared");
  let m2 = m;
  println(show(m));
  println(show(m2));
  return 0;
}
""",
     "shared\n1\nshared\n1\n"),
    ("p9 enum return + reassign",
     r"""enum Msg { Text(str), Num(int) }

fn ident(m: Msg) -> Msg {
  return m;
}

fn main() -> int {
  let m = Text("ret");
  let m2 = ident(m);
  match m2 {
    Text(s) => {
      println(s);
    }
    Num(n) => {
      println(n);
    }
  }
  let mut m3 = Num(0);
  m3 = m;
  match m3 {
    Text(s) => {
      println(s);
    }
    Num(n) => {
      println(n);
    }
  }
  return 0;
}
""",
     "ret\nret\n"),
    ("p10 match on fresh enum scrutinee",
     r"""enum Msg { Text(str), Num(int) }

fn mk() -> Msg {
  return Text("fresh");
}

fn main() -> int {
  match mk() {
    Text(s) => {
      println(s);
    }
    Num(n) => {
      println(n);
    }
  }
  return 0;
}
""",
     "fresh\n"),
    ("p11 str index on fresh str",
     r"""fn main() -> int {
  let s = "hello" + " world";
  println(s[1]);
  println(("ab" + "cd")[2]);
  return 0;
}
""",
     "e\nc\n"),
    ("p12 nested index into fresh [[int]]",
     r"""fn matrix() -> [[int]] {
  return [[1, 2], [3, 4]];
}

fn main() -> int {
  println(len(matrix()[0]));
  println(matrix()[1][0]);
  return 0;
}
""",
     "2\n3\n"),
    ("p13 lambda captures payload enum and escapes",
     r"""enum Msg { Text(str), Num(int) }

fn make() -> fn() -> int {
  let m = Text("hello");
  let g = fn() -> int {
    match m {
      Text(s) => {
        println(s);
        return 1;
      }
      Num(n) => {
        println(n);
        return 2;
      }
    }
    return 0;
  };
  return g;
}

fn main() -> int {
  let f = make();
  println(f());
  return 0;
}
""",
     "hello\n1\n"),
    ("p14 break inside for-over-fresh",
     r"""fn nums() -> [int] {
  return [10, 20, 30];
}

fn main() -> int {
  let mut total = 0;
  for x in nums() {
    if x == 20 {
      break;
    }
    total = total + x;
  }
  println(total);
  return 0;
}
""",
     "10\n"),
    ("p15 shared array element field (special case)",
     r"""struct Pt { name: str, x: int }

fn main() -> int {
  let pts = [Pt { name: "p", x: 5 }];
  println(pts[0].name);
  println(pts[0].x);
  return 0;
}
""",
     "p\n5\n"),
    ("p16 continue inside for-over-fresh",
     r"""fn nums() -> [int] {
  return [10, 20, 30];
}

fn main() -> int {
  let mut total = 0;
  for x in nums() {
    if x == 20 {
      continue;
    }
    total = total + x;
  }
  println(total);
  return 0;
}
""",
     "40\n"),
    ("p17 tuple holding a payload enum",
     r"""enum Msg { Text(str), Num(int) }

fn main() -> int {
  let m = Text("hi");
  let t = (m, 3);
  let t2 = t;
  match t2.0 {
    Text(s) => {
      println(s);
    }
    Num(n) => {
      println(n);
    }
  }
  println(t2.1);
  return 0;
}
""",
     "hi\n3\n"),
    # q3: block-let shadowing an outer variable — RUNTIME ONLY.
    # It still leaks 6 bytes (pre-existing, out of scope: the
    # arm-frame shadowing rule matches it, and the ASan section
    # below does NOT assert zero for it).
    ("q3 block-let shadowing (runtime only, known 6B leak)",
     r"""fn main() -> int {
  let s = "outer";
  {
    let s = "inner";
    println(s);
  }
  println(s);
  return 0;
}
""",
     "inner\nouter\n"),
    # p18/p19: the construction-own fix (§2a). Found by the suite
    # gate (generic_enums_demo segfaulted under the first build):
    # a variant construction must OWN its payload, using the
    # CONCRETE payload type — the template type is a type parameter
    # for generic enums. p18 is the generic str-literal case;
    # p19 is a shared array payload (double-free without the fix).
    ("p18 generic enum str-literal payload",
     r"""enum ResultE<T, E> { Ok(T), Err(E) }

fn main() -> int {
  let r: ResultE<int, str> = Err("div by zero");
  match r {
    Ok(v) => {
      println(v);
    }
    Err(e) => {
      println("err", e);
    }
  }
  return 0;
}
""",
     "err div by zero\n"),
    ("p19 enum shared array payload",
     r"""enum E { Xs([int]), N(int) }

fn main() -> int {
  let a = [1, 2, 3];
  let e = Xs(a);
  match e {
    Xs(x) => {
      println(len(x));
    }
    N(n) => {
      println(n);
    }
  }
  println(len(a));
  return 0;
}
""",
     "3\n3\n"),
]

# (name, source, fragment that must appear in the checker error).
REJECT_CASES = [
    ("q1 IndexAssign on a fresh array",
     r"""fn nums() -> [int] {
  return [1, 2, 3];
}

fn main() -> int {
  nums()[0] = 99;
  println(1);
  return 0;
}
""",
     "index assignment target must be a variable or a field"),
    ("q2 tuple arrays",
     r"""fn main() -> int {
  let ts = [(1, "a"), (2, "b")];
  println(ts[0].0);
  return 0;
}
""",
     "unsupported index element type"),
    ("q4 FieldAssign on a fresh struct",
     r"""struct Named { name: str, v: int }

fn mk() -> Named {
  return Named { name: "nm", v: 7 };
}

fn main() -> int {
  mk().v = 9;
  println(1);
  return 0;
}
""",
     "field assignment target must start from a variable"),
    ("q5 enum arrays",
     r"""enum Msg { Text(str), Num(int) }

fn msgs() -> [Msg] {
  return [Text("a"), Num(1)];
}

fn main() -> int {
  let m = msgs()[0];
  match m {
    Text(s) => {
      println(s);
    }
    Num(n) => {
      println(n);
    }
  }
  return 0;
}
""",
     "unsupported index element type"),
]

# The torture program (filesystem slice after/torture_leak.fg),
# read at test time so the test tracks the recorded program.
TORTURE_SRC = os.path.join(
    os.path.expanduser("~"), "workspace", "blackmoon-iso",
    "filesystem-slice", "after", "torture_leak.fg")

# Torture expected stdout, recorded 23 Nov 2026 from the Python
# compiler (post-fix). stderr is exactly "err msg\n" (the program's
# own eprintln). stat_mode 33188 assumes umask 0007 (0660 file);
# uid/gid 1000 come from the program's own chown(..., 1000, 1000).
TORTURE_EXPECTED = """hi
true
hello
true
20
5
true
2
true
0
true
0
true
true
/tmp/leakcheck/t2.txt
true
/tmp/leakcheck/t2.txt
true
true
33188
1000
1000
true
false
0
42
1.5
2
x-y
ell
hi
true
true
0
11
4
1
false
1
ab
ab
nm
pq
hello world
0
true
hello
true
2
hi!
true
true
/tmp/leakcheck/t2.txt
a
/tmp/leakcheck/t2.txt
a
"""


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def leak_summary(stderr):
    m = re.search(
        r"SUMMARY: AddressSanitizer: (\d+) byte\(s\) leaked in (\d+) allocation",
        stderr)
    if m:
        return int(m.group(1)), int(m.group(2))
    if "AddressSanitizer" in stderr or "LeakSanitizer" in stderr:
        return ("?", "?")
    return (0, 0)


def main():
    failures = []
    total = 0
    with tempfile.TemporaryDirectory() as td:
        for name, prog, want in OK_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                total += 1
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = rr.returncode == 0 and rr.stdout == want
                if not check(f"{name} ({mode})", ok,
                             repr(rr.stdout) +
                             (rr.stderr.strip().splitlines() or [""])[-1]):
                    failures.append(f"{name} ({mode})")
        for name, prog, frag in REJECT_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                total += 1
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
                if not check(f"{name} ({mode})", ok,
                             (rr.stderr.strip().splitlines() or [""])[-1]):
                    failures.append(f"{name} ({mode})")
        # Torture program: runtime under both compilers.
        with open(TORTURE_SRC) as f:
            torture = f.read()
        tp = os.path.join(td, "torture.fg")
        with open(tp, "w") as f:
            f.write(torture)
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            total += 1
            shutil.rmtree("/tmp/leakcheck", ignore_errors=True)
            os.makedirs("/tmp/leakcheck", exist_ok=True)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["run", tp], ROOT)
            ok = (rr.returncode == 0 and rr.stdout == TORTURE_EXPECTED
                  and rr.stderr == "err msg\n")
            if not check(f"torture runs ({mode})", ok,
                         repr(rr.stdout[:120]) + repr(rr.stderr)):
                failures.append(f"torture runs ({mode})")
        # ASan section: every runtime probe (except q3) + the
        # torture program must be leak-free under BOTH compilers.
        # Emit C, compile with -fsanitize=address, run; stdout is
        # checked on the plain binary (LSan _exit discards it).
        asan_cases = [(n, s, w) for (n, s, w) in OK_CASES
                      if not n.startswith("q3")]
        asan_cases.append(("torture", torture, TORTURE_EXPECTED))
        for name, prog, want in asan_cases:
            p = os.path.join(td, "a.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                total += 1
                tag = "hosted" if mode == "hosted" else "python"
                if name == "torture":
                    shutil.rmtree("/tmp/leakcheck", ignore_errors=True)
                    os.makedirs("/tmp/leakcheck", exist_ok=True)
                em = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["emit", p], ROOT)
                if em.returncode != 0:
                    check(f"asan {name} ({mode})", False,
                          "emit rc=%d" % em.returncode)
                    failures.append(f"asan {name} ({mode}) emit")
                    continue
                c_path = os.path.join(td, "a.%s.c" % tag)
                with open(c_path, "w") as f:
                    f.write(em.stdout)
                bin_path = os.path.join(td, "a.%s" % tag)
                cc = run(["cc", "-g", "-O1", "-fsanitize=address",
                          "-o", bin_path, c_path, "-lssl", "-lcrypto",
                          "-lm", "-pthread"], td)
                if cc.returncode != 0:
                    check(f"asan {name} ({mode})", False,
                          "cc rc=%d" % cc.returncode)
                    failures.append(f"asan {name} ({mode}) cc")
                    continue
                plain_path = os.path.join(td, "a.%s.plain" % tag)
                cc2 = run(["cc", "-g", "-O1",
                           "-o", plain_path, c_path, "-lssl", "-lcrypto",
                           "-lm", "-pthread"], td)
                if cc2.returncode != 0:
                    check(f"asan {name} ({mode})", False,
                          "plain cc rc=%d" % cc2.returncode)
                    failures.append(f"asan {name} ({mode}) plain cc")
                    continue
                if name == "torture":
                    shutil.rmtree("/tmp/leakcheck", ignore_errors=True)
                    os.makedirs("/tmp/leakcheck", exist_ok=True)
                rp = run([plain_path], td)
                if name == "torture":
                    # The plain run created t2.txt / td / tlink;
                    # reset so the ASan run sees the same fresh
                    # directory (mkdir/symlink return false when
                    # the target already exists).
                    shutil.rmtree("/tmp/leakcheck", ignore_errors=True)
                    os.makedirs("/tmp/leakcheck", exist_ok=True)
                ra = run([bin_path], td)
                leaks = leak_summary(ra.stderr)
                ok = (rp.returncode == 0 and rp.stdout == want
                      and ra.returncode == 0 and leaks == (0, 0))
                if not check(f"asan {name} ({mode})", ok,
                             "plain rc=%d asan rc=%d leaks=%s" %
                             (rp.returncode, ra.returncode, leaks)):
                    failures.append(f"asan {name} ({mode})")
    print(f"leak_followups: {total - len(failures)}/{total} checks passed")
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
