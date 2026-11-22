"""Top-500 #47: backtraces on fail in debug builds (tests/test_backtrace_v1.py).

A DEBUG build (`build --debug`) prints a native backtrace after the
failure message: `stack backtrace:` followed by one line per frame,
innermost first, `  N: <fn> at <file>:<line>`. A RELEASE build prints
the failure message only — no backtrace, and the binary contains no
"stack backtrace" string at all (verified by reading the binary).

Covered: fail() in a nested chain (exact stderr, both compilers);
fail() at top level (single frame); runtime faults via forge_fail
(bounds, div-by-zero) in debug and release; assert failure; fail()
in a spawned task (the task's own chain only — no main frame —
siblings finish, panicked_tasks() counts it, #44 still works);
recursion depth 5 (push/pop balance); the --debug rejections
(big32/wasm/freestanding/shared); the stripped-release proof.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO = os.path.join(ROOT, "examples", "backtrace_demo.fg")


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def build(prog_path, out_path, debug, prefix):
    """Build with forge.py (hosted default, --python prefix)."""
    args = [sys.executable, os.path.join(ROOT, "forge.py")] + prefix + ["build"]
    if debug:
        args.append("--debug")
    args += ["-o", out_path, prog_path]
    return run(args, ROOT)


def trace(path, frames):
    """Expected stderr for a failing debug build: the message is
    prepended by the caller; frames is [(fn, line), ...]."""
    lines = ["stack backtrace:"]
    for i, (fn, line) in enumerate(frames):
        lines.append(f"  {i}: {fn} at {path}:{line}")
    return "\n".join(lines) + "\n"


def main():
    failures = []
    with tempfile.TemporaryDirectory() as td:
        # --- The demo, both compilers, debug + release. ---
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            dbg = os.path.join(td, f"demo_dbg_{mode}")
            rel = os.path.join(td, f"demo_rel_{mode}")
            r = build(DEMO, dbg, True, prefix)
            if not check(f"demo debug builds ({mode})", r.returncode == 0,
                         r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""):
                failures.append(f"demo debug builds ({mode})")
                continue
            rr = run([dbg], td)
            # The demo is fmt-canonical: no header comment (the
            # formatter strips // comments) and multi-line fns,
            # so helper/middle/main sit on lines 2/6/10.
            want = ("qasida: deep boom\n" +
                    trace(DEMO, [("helper", 2), ("middle", 6), ("main", 10)]))
            if not check(f"demo debug stderr ({mode})",
                         rr.returncode != 0 and rr.stderr == want, repr(rr.stderr)):
                failures.append(f"demo debug stderr ({mode})")
            r = build(DEMO, rel, False, prefix)
            if not check(f"demo release builds ({mode})", r.returncode == 0,
                         r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""):
                failures.append(f"demo release builds ({mode})")
                continue
            rr = run([rel], td)
            if not check(f"demo release stderr ({mode})",
                         rr.returncode != 0 and rr.stderr == "qasida: deep boom\n",
                         repr(rr.stderr)):
                failures.append(f"demo release stderr ({mode})")
            # Stripped proof: the release binary has no backtrace
            # string at all; the debug binary has it.
            with open(rel, "rb") as f:
                rel_bytes = f.read()
            with open(dbg, "rb") as f:
                dbg_bytes = f.read()
            if not check(f"release binary has no backtrace string ({mode})",
                         b"stack backtrace" not in rel_bytes):
                failures.append(f"release binary has no backtrace string ({mode})")
            if not check(f"debug binary has the backtrace string ({mode})",
                         b"stack backtrace" in dbg_bytes):
                failures.append(f"debug binary has the backtrace string ({mode})")

        # --- Case programs: (name, program, debug frames, message,
        # release message). The frame file is the temp program path.
        cases = [
            ("3-deep chain",
             "fn helper() { fail(\"deep boom\"); }\n"
             "fn middle() { helper(); }\n"
             "fn main() -> int { middle(); return 0; }\n",
             [("helper", 1), ("middle", 2), ("main", 3)],
             "qasida: deep boom\n",
             "qasida: deep boom\n"),
            ("fail at top level (single frame)",
             "fn main() -> int {\n"
             "  fail(\"solo\");\n"
             "  return 0;\n"
             "}\n",
             [("main", 2)],
             "qasida: solo\n",
             "qasida: solo\n"),
            ("bounds fault in a helper",
             "fn get(xs: [int], i: int) -> int {\n"
             "  return xs[i];\n"
             "}\n"
             "fn main() -> int {\n"
             "  let xs: [int] = [10, 20];\n"
             "  let v: int = get(xs, 5);\n"
             "  println(v);\n"
             "  return 0;\n"
             "}\n",
             [("get", 2), ("main", 6)],
             "qasida: runtime error: array index out of bounds\n",
             "qasida: runtime error: array index out of bounds\n"),
            ("div-by-zero in a helper",
             "fn divide(a: int, b: int) -> int {\n"
             "  return a / b;\n"
             "}\n"
             "fn main() -> int {\n"
             "  println(divide(10, 0));\n"
             "  return 0;\n"
             "}\n",
             [("divide", 2), ("main", 5)],
             "qasida: runtime error: division by zero\n",
             "qasida: runtime error: division by zero\n"),
            ("assert failure",
             "fn check(n: int) {\n"
             "  assert(n > 0, \"n must be positive\");\n"
             "}\n"
             "fn main() -> int {\n"
             "  check(0);\n"
             "  return 0;\n"
             "}\n",
             [("check", 2), ("main", 5)],
             "qasida: assertion failed: n must be positive\n",
             "qasida: assertion failed: n must be positive\n"),
            ("recursion depth 5",
             "fn down(n: int) {\n"
             "  if n == 0 {\n"
             "    fail(\"bottom\");\n"
             "  }\n"
             "  down(n - 1);\n"
             "}\n"
             "fn main() -> int {\n"
             "  down(4);\n"
             "  return 0;\n"
             "}\n",
             [("down", 3), ("down", 5), ("down", 5),
              ("down", 5), ("down", 5), ("main", 8)],
             "qasida: bottom\n",
             "qasida: bottom\n"),
        ]
        for name, prog, frames, msg, rel_msg in cases:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                dbg = os.path.join(td, f"c_dbg_{mode}")
                rel = os.path.join(td, f"c_rel_{mode}")
                r = build(p, dbg, True, prefix)
                if r.returncode != 0:
                    if not check(f"{name} debug builds ({mode})", False,
                                 r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""):
                        failures.append(f"{name} debug builds ({mode})")
                    continue
                rr = run([dbg], td)
                want = msg + trace(p, frames)
                if not check(f"{name} debug stderr ({mode})",
                             rr.returncode != 0 and rr.stderr == want,
                             repr(rr.stderr)):
                    failures.append(f"{name} debug stderr ({mode})")
                r = build(p, rel, False, prefix)
                if r.returncode != 0:
                    if not check(f"{name} release builds ({mode})", False,
                                 r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""):
                        failures.append(f"{name} release builds ({mode})")
                    continue
                rr = run([rel], td)
                if not check(f"{name} release stderr ({mode})",
                             rr.returncode != 0 and rr.stderr == rel_msg,
                             repr(rr.stderr)):
                    failures.append(f"{name} release stderr ({mode})")

        # --- fail() in a spawned task (#44 still works): the task's
        # own chain only (no main frame), siblings finish, count 1.
        p = os.path.join(td, "task.fg")
        with open(p, "w") as f:
            f.write(
                "fn helper() {\n"
                "  fail(\"boom\");\n"
                "}\n"
                "fn worker(n: int) {\n"
                "  helper();\n"
                "}\n"
                "fn steady(n: int) {\n"
                "  println(\"steady done\", n);\n"
                "}\n"
                "fn main() -> int {\n"
                "  scope {\n"
                "    spawn worker(1);\n"
                "    spawn steady(2);\n"
                "  }\n"
                "  println(\"count\", panicked_tasks());\n"
                "  return 0;\n"
                "}\n")
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            dbg = os.path.join(td, f"task_dbg_{mode}")
            r = build(p, dbg, True, prefix)
            if r.returncode != 0:
                if not check(f"task fail debug builds ({mode})", False,
                             r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""):
                    failures.append(f"task fail debug builds ({mode})")
                continue
            rr = run([dbg], td)
            want_err = ("qasida: task panicked: boom\n" +
                        trace(p, [("helper", 2), ("worker", 5)]))
            ok = (rr.returncode == 0 and
                  rr.stdout == "steady done 2\ncount 1\n" and
                  rr.stderr == want_err)
            if not check(f"task fail debug ({mode})", ok,
                         repr(rr.stdout) + repr(rr.stderr)):
                failures.append(f"task fail debug ({mode})")

        # --- --debug rejections. forge.py routes --target big32/wasm
        # and --shared to Python (they are deferred in hosted), so
        # those three are Python-only here; --freestanding reaches
        # both drivers.
        p = os.path.join(td, "rej.fg")
        with open(p, "w") as f:
            f.write("fn main() -> int { return 0; }\n")
        rejects = [
            ("debug + big32", ["build", "--debug", "--target", "big32", p],
             {"python": "--debug is only supported for native builds"}),
            ("debug + wasm", ["build", "--debug", "--target", "wasm", p],
             {"python": "--debug is only supported for native builds"}),
            ("debug + freestanding", ["build", "--debug", "--freestanding", p],
             {"hosted": "--debug is not supported with --freestanding",
              "python": "--debug is not supported with --freestanding"}),
            ("debug + shared", ["build", "--debug", "--shared", p],
             {"python": "--debug is not supported with --shared"}),
        ]
        for name, argv, frags in rejects:
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                if mode not in frags:
                    continue
                rr = run([sys.executable, os.path.join(ROOT, "forge.py")] +
                         prefix + argv, ROOT)
                ok = rr.returncode != 0 and frags[mode] in (rr.stderr + rr.stdout)
                if not check(f"{name} rejected ({mode})", ok,
                             (rr.stderr.strip().splitlines() or [""])[-1]):
                    failures.append(f"{name} rejected ({mode})")

    # fmt idempotent on the demo (hosted `forge.py fmt` — the Python
    # formatter strips file-leading // comments; pre-existing quirk).
    rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", DEMO], ROOT)
    if not check("fmt runs", rf.returncode == 0, rf.stderr.strip()):
        failures.append("fmt runs")
    else:
        rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                   "fmt", "--check", DEMO], ROOT)
        if not check("fmt idempotent", rf2.returncode == 0, rf2.stderr.strip()):
            failures.append("fmt idempotent")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
