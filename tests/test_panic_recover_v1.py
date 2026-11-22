"""Top-500 #44: panic vs recover boundary (tests/test_panic_recover_v1.py).

fail() stays fatal in ordinary code; at a task boundary (a spawned
task) it ends just that task: the panic is printed to stderr as
"qasida: task panicked: <msg>", one panic is counted, the thread
exits, and the spawning scope joins normally. The program reads the
count with the new zero-arg builtin panicked_tasks() -> int after
the join and recovers (branches, retries, reports, continues).

v1 limits (named in the catalog): runtime faults via forge_fail
(bounds, overflow, div-by-zero, OOM) still kill the process even
in a task; a panicked task's owned locals are not freed (no
unwinding); the panic message is printed, not retrievable (count
only). big32, WASM and freestanding reject panicked_tasks() with
named errors (no threads there). Both compilers (Python + hosted).
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """before 0
steady done 2
after 1
recovered
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("no spawn, zero panics",
     r"""fn main() -> int {
  println(panicked_tasks());
  return 0;
}
""",
     """0
""",
     ""),
    ("one flaky task counts once, program continues",
     r"""fn flaky(n: int) {
  fail("boom");
}

fn steady(n: int) {
  println("steady done", n);
}

fn main() -> int {
  println("before", panicked_tasks());
  scope {
    spawn flaky(1);
    spawn steady(2);
  }
  println("after", panicked_tasks());
  return 0;
}
""",
     """before 0
steady done 2
after 1
""",
     "qasida: task panicked: boom"),
    ("two flaky tasks count twice",
     r"""fn flaky(n: int) {
  fail("boom");
}

fn main() -> int {
  scope {
    spawn flaky(1);
    spawn flaky(2);
  }
  println("count", panicked_tasks());
  return 0;
}
""",
     """count 2
""",
     "qasida: task panicked: boom"),
    ("fail inside a helper called by the task counts",
     r"""fn helper() {
  fail("deep boom");
}

fn worker(n: int) {
  helper();
}

fn main() -> int {
  scope {
    spawn worker(1);
  }
  println("count", panicked_tasks());
  return 0;
}
""",
     """count 1
""",
     "qasida: task panicked: deep boom"),
    ("nested scopes: count visible after inner join, stable after outer",
     r"""fn flaky(n: int) {
  fail("boom");
}

fn steady(n: int) {
  println("steady done", n);
}

fn main() -> int {
  scope {
    spawn flaky(1);
  }
  println("inner", panicked_tasks());
  scope {
    spawn steady(2);
  }
  println("outer", panicked_tasks());
  return 0;
}
""",
     """inner 1
steady done 2
outer 1
""",
     "qasida: task panicked: boom"),
    ("recovery branch falls back and continues",
     r"""fn flaky(n: int) {
  fail("boom");
}

fn fallback() -> int {
  return 42;
}

fn main() -> int {
  scope {
    spawn flaky(1);
  }
  if panicked_tasks() > 0 {
    println("fallback", fallback());
  }
  println("done");
  return 0;
}
""",
     """fallback 42
done
""",
     "qasida: task panicked: boom"),
    ("fail with a variable message counts",
     r"""fn flaky(n: int) {
  let m: str = "custom boom";
  fail(m);
}

fn main() -> int {
  scope {
    spawn flaky(1);
  }
  println("count", panicked_tasks());
  return 0;
}
""",
     """count 1
""",
     "qasida: task panicked: custom boom"),
]

# (name, program, expected stdout, expected stderr needle) — must
# exit non-zero: fail() outside a task stays fatal.
FATAL_CASES = [
    ("fail in main stays fatal",
     r"""fn main() -> int {
  println("start");
  fail("fatal boom");
  return 0;
}
""",
     """start
""",
     "qasida: fatal boom"),
    ("fail in a plain function called from main stays fatal",
     r"""fn helper() {
  fail("helper boom");
}

fn main() -> int {
  println("start");
  helper();
  return 0;
}
""",
     """start
""",
     "qasida: helper boom"),
]

# (name, program, error fragment) — must be rejected at check time.
REJECT_CASES = [
    ("panicked_tasks with an argument",
     r"""fn main() -> int {
  println(panicked_tasks(1));
  return 0;
}
""",
     "panicked_tasks() takes no arguments"),
    ("panicked_tasks as a statement",
     r"""fn main() -> int {
  panicked_tasks();
  return 0;
}
""",
     "is an expression, not a statement"),
]

# (name, forge argv after the file, error fragment) — backend rejections.
BACKEND_CASES = [
    ("emit-big32 rejects panicked_tasks",
     ["emit-big32"],
     "builtin panicked_tasks() is not supported on big32 (v1)"),
    ("emit-wasm rejects panicked_tasks",
     ["emit-wasm"],
     "wasm: panicked_tasks() needs threads"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "panic_recover_demo.fg")
    for mode, prefix in (("hosted", []), ("python", ["--python"])):
        r = run([sys.executable, os.path.join(ROOT, "forge.py")] + prefix +
                ["run", demo], ROOT)
        if not check(f"demo runs ({mode})", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append(f"demo runs ({mode})")
        elif not check(f"demo results ({mode})", r.stdout == DEMO_EXPECTED,
                       repr(r.stdout)):
            failures.append(f"demo results ({mode})")
        elif not check(f"demo panic line ({mode})",
                       "qasida: task panicked: boom" in r.stderr, repr(r.stderr)):
            failures.append(f"demo panic line ({mode})")
    with tempfile.TemporaryDirectory() as td:
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
        for name, prog, want, needle in FATAL_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = (rr.returncode != 0 and rr.stdout == want and
                      needle in rr.stderr)
                if not check(f"{name} ({mode})", ok,
                             repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                    failures.append(f"{name} ({mode})")
        for name, prog, frag in REJECT_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + ["run", p], ROOT)
                ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
                if not check(f"{name} ({mode})", ok,
                             (rr.stderr.strip().splitlines() or [""])[-1]):
                    failures.append(f"{name} ({mode})")
        # Freestanding rejects panicked_tasks() (needs the hosted
        # thread runtime). The program must not use println: in
        # freestanding mode println itself is rejected first, so
        # the call is read through a plain int binding instead.
        p = os.path.join(td, "c.fg")
        with open(p, "w") as f:
            f.write(r"""fn main() -> int {
  let n: int = panicked_tasks();
  return n;
}
""")
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                     prefix + ["check", p, "--freestanding"], ROOT)
            ok = (rr.returncode != 0 and
                  "needs the hosted runtime" in (rr.stderr + rr.stdout))
            if not check(f"freestanding rejects panicked_tasks ({mode})", ok,
                         (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(f"freestanding rejects panicked_tasks ({mode})")
        # big32 and WASM reject panicked_tasks programs (native-only).
        for name, cmd, frag in BACKEND_CASES:
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + cmd + [demo], ROOT)
                ok = rr.returncode != 0 and frag in (rr.stderr + rr.stdout)
                if not check(f"{name} ({mode})", ok,
                             (rr.stderr.strip().splitlines() or [""])[-1]):
                    failures.append(f"{name} ({mode})")
    rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", demo],
             ROOT)
    if not check("fmt runs", rf.returncode == 0, rf.stderr.strip()):
        failures.append("fmt runs")
    else:
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                   "fmt", "--check", demo], ROOT)
        if not check("fmt idempotent", rf2.returncode == 0, rf2.stderr.strip()):
            failures.append("fmt idempotent")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
