#!/usr/bin/env python3
"""Slice 5A driver builtins: run_command / fail_compile / eprintln
(tests/test_driver_builtins_v1.py).

  * run_command(cmd: str) -> int — expression builtin, runs the
    command via system() (/bin/sh -c); exit code 0-255 on normal
    exit, -1 when system() fails or the child dies by signal.
  * fail_compile(msg: str) — statement builtin; prints
    "qasida: error: <msg>" to stderr and exits 1.
  * eprintln(msg: str) — statement builtin; prints msg + newline
    to stderr, does not exit.

Proves each builtin end to end (build + run, exact stdout/stderr/
exit code), the arity/type rejections, the statement-vs-expression
rules, and the gates: all three rejected in freestanding mode and
by the big32/WASM targets.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]

FAILURES = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    if cond:
        print(f"  PASS {name}")
        return True
    print(f"  FAIL {name} {detail}")
    FAILURES.append(name)
    return False


def run(args, cwd=None):
    return subprocess.run(args, capture_output=True, text=True,
                          timeout=120, cwd=cwd or ROOT)


def write_prog(d, prog, name="prog.fg"):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(prog)
    return path


def build_run(name, prog, exp_out, exp_err, exp_rc):
    d = tempfile.mkdtemp(prefix="driver-allow-")
    path = write_prog(d, prog)
    out = os.path.join(d, "prog")
    r = run(FORGE + ["build", path, "-o", out])
    if not check(f"{name} builds", r.returncode == 0,
                 f"err={r.stderr[:300]!r}"):
        return
    r2 = subprocess.run([out], capture_output=True, text=True, timeout=30)
    ok = (r2.returncode == exp_rc and r2.stdout == exp_out
          and r2.stderr == exp_err)
    check(f"{name} runs rc={exp_rc} out={exp_out!r} err={exp_err!r}", ok,
          f"rc={r2.returncode} out={r2.stdout!r} err={r2.stderr!r}")


def reject(name, prog, *needles, args=None):
    d = tempfile.mkdtemp(prefix="driver-reject-")
    path = write_prog(d, prog)
    r = run(FORGE + ["check", path] + (args or []))
    out = r.stdout + r.stderr
    ok = r.returncode != 0 and all(n in out for n in needles)
    check(f"rejects {name}", ok,
          f"rc={r.returncode} out={out[:300]!r}")


def gate(name, prog, cmd, *needles):
    d = tempfile.mkdtemp(prefix="driver-gate-")
    path = write_prog(d, prog)
    r = run(FORGE + cmd + [path])
    out = r.stdout + r.stderr
    ok = r.returncode != 0 and all(n in out for n in needles)
    check(f"gate rejects {name}", ok,
          f"rc={r.returncode} out={out[:300]!r}")


def main():
    print("run_command / fail_compile / eprintln (slice 5A)")
    # Exact runtime behaviour.
    build_run("run_command true/false/missing",
              'fn main() {\n'
              '    println(run_command("true"));\n'
              '    println(run_command("false"));\n'
              '    println(run_command("nonexistent_cmd_xyz_123"));\n'
              '}\n',
              "0\n1\n127\n", "sh: 1: nonexistent_cmd_xyz_123: not found\n", 0)
    build_run("run_command echo fixed output",
              'fn main() {\n'
              '    let r: int = run_command("echo hello-driver");\n'
              '    println(r);\n'
              '}\n',
              "hello-driver\n0\n", "", 0)
    build_run("run_command in arithmetic and condition",
              'fn main() {\n'
              '    let r: int = run_command("true") + 1;\n'
              '    println(r);\n'
              '    if run_command("true") == 0 {\n'
              '        println("yes");\n'
              '    }\n'
              '}\n',
              "1\nyes\n", "", 0)
    build_run("eprintln exact stderr, no exit",
              'fn main() {\n'
              '    eprintln("warn one");\n'
              '    println("on stdout");\n'
              '    eprintln("warn two");\n'
              '}\n',
              "on stdout\n", "warn one\nwarn two\n", 0)
    build_run("fail_compile exact stderr, exits 1",
              'fn main() {\n'
              '    println("before");\n'
              '    fail_compile("boom msg");\n'
              '    println("never");\n'
              '}\n',
              "before\n", "qasida: error: boom msg\n", 1)
    build_run("fail_compile computed message",
              'fn main() {\n'
              '    fail_compile("code " + "42");\n'
              '}\n',
              "", "qasida: error: code 42\n", 1)
    # Emission: the helper and the error prefix are in the C.
    d = tempfile.mkdtemp(prefix="driver-emit-")
    path = write_prog(d, 'fn main() {\n'
                         '    let r: int = run_command("true");\n'
                         '    println(r);\n'
                         '    fail_compile("x");\n'
                         '}\n')
    r = run(FORGE + ["emit", path])
    check("emit contains forge_run_command helper",
          r.returncode == 0 and "forge_run_command" in r.stdout
          and "WIFEXITED" in r.stdout,
          f"rc={r.returncode} err={r.stderr[:200]!r}")
    check("emit contains qasida: error: prefix",
          "qasida: error: %s" in r.stdout,
          f"rc={r.returncode}")
    # Arity / type rejections.
    reject("run_command int arg",
           'fn main() { let r: int = run_command(42); }\n',
           "run_command() takes exactly one str argument")
    reject("run_command no arg",
           'fn main() { let r: int = run_command(); }\n',
           "run_command() takes exactly one str argument")
    reject("run_command two args",
           'fn main() { let r: int = run_command("a", "b"); }\n',
           "run_command() takes exactly one str argument")
    reject("fail_compile int arg",
           'fn main() { fail_compile(42); }\n',
           "fail_compile() takes exactly one str argument")
    reject("fail_compile no arg",
           'fn main() { fail_compile(); }\n',
           "fail_compile() takes exactly one str argument")
    reject("eprintln int arg",
           'fn main() { eprintln(42); }\n',
           "eprintln() takes exactly one str argument")
    reject("eprintln no arg",
           'fn main() { eprintln(); }\n',
           "eprintln() takes exactly one str argument")
    # Statement-vs-expression rules.
    reject("run_command as statement",
           'fn main() { run_command("true"); }\n',
           "'run_command' is an expression, not a statement")
    reject("fail_compile as value",
           'fn main() { let x: int = fail_compile("m"); }\n',
           "can only be used as a statement")
    reject("eprintln as value",
           'fn main() { let x: int = eprintln("m"); }\n',
           "can only be used as a statement")
    # Freestanding gate (checker, --freestanding).
    reject("freestanding run_command",
           'fn main() { let r: int = run_command("true"); }\n',
           "needs the hosted runtime", "freestanding",
           args=["--freestanding"])
    reject("freestanding eprintln",
           'fn main() { eprintln("x"); }\n',
           "hosted I/O library", "freestanding",
           args=["--freestanding"])
    reject("freestanding fail_compile",
           'fn main() { fail_compile("x"); }\n',
           "writes to stderr", "freestanding",
           args=["--freestanding"])
    # big32 gate (codegen).
    gate("big32 run_command",
         'fn main() { let r: int = run_command("true"); println(r); }\n',
         ["build", "--target", "big32", "-o", "gate_big"],
         "run_command() is not supported on big32")
    gate("big32 eprintln",
         'fn main() { eprintln("x"); }\n',
         ["build", "--target", "big32", "-o", "gate_big"],
         "eprintln() is not supported on big32")
    gate("big32 fail_compile",
         'fn main() { fail_compile("x"); }\n',
         ["build", "--target", "big32", "-o", "gate_big"],
         "fail_compile() is not supported on big32")
    # WASM gate (codegen).
    gate("wasm run_command",
         'fn main() { let r: int = run_command("true"); println(r); }\n',
         ["build", "--target", "wasm", "-o", "gate.wasm"],
         "run_command() needs a shell")
    gate("wasm eprintln",
         'fn main() { eprintln("x"); }\n',
         ["build", "--target", "wasm", "-o", "gate.wasm"],
         "eprintln() writes to stderr")
    gate("wasm fail_compile",
         'fn main() { fail_compile("x"); }\n',
         ["build", "--target", "wasm", "-o", "gate.wasm"],
         "fail_compile() writes to stderr")

    print(f"\n{CHECKS[0] - len(FAILURES)} pass, {len(FAILURES)} fail "
          f"({CHECKS[0]} checks)")
    if FAILURES:
        print("FAILURES:")
        for f in FAILURES:
            print(" -", f)
        return 1
    print("PASS: all driver-builtin tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
