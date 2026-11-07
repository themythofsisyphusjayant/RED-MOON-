"""Top-500 #36: allocation failure as a value (tests/test_allocfail_v1.py).
`try_alloc(n)` returns Result<[int], str>: Ok with a zero-initialised
[int] array, or Err("out of memory") / Err("bad size") instead of the
fatal forge_fail. Native-only in v1: big32 and WASM reject it, and
freestanding mode rejects it (it needs the hosted calloc). The program
must import "result.fg" (the Result struct lives there); the checker
registers the Result<[int], str> instantiation so codegen emits it.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

IMP = 'import "result.fg";\n'
BIG = "1152921504606846976"  # 2^60 elements = 2^63 bytes: calloc must fail.

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("success: 5 zeroes",
     IMP + "fn main() {\n  let r = try_alloc(5);\n"
     "  println(r.ok);\n  println(len(r.value));\n"
     "  println(r.value[0]);\n  println(r.value[4]);\n}\n",
     "true\n5\n0\n0\n"),
    ("bad size: Err, no crash",
     IMP + "fn main() {\n  let r = try_alloc(-1);\n"
     "  println(r.ok);\n  println(r.error);\n}\n",
     "false\nbad size\n"),
    ("zero size: Ok empty",
     IMP + "fn main() {\n  let r = try_alloc(0);\n"
     "  println(r.ok);\n  println(len(r.value));\n}\n",
     "true\n0\n"),
    ("huge request: Err, no crash",
     IMP + "fn main() {\n  let r = try_alloc(" + BIG + ");\n"
     "  println(r.ok);\n  println(r.error);\n}\n",
     "false\nout of memory\n"),
    ("write and read back the allocated array",
     IMP + "fn main() {\n  let r = try_alloc(3);\n"
     "  let mut v = r.value;\n  v[0] = 7;\n  v[2] = 9;\n"
     "  println(v[0]);\n  println(v[1]);\n  println(v[2]);\n"
     "  println(r.value[0]);\n}\n",
     "7\n0\n9\n7\n"),
    ("? propagation: Err reaches the caller",
     IMP + "fn alloc_or_fail(n: int) -> Result<[int], str> {\n"
     "  let v = try_alloc(n)?;\n"
     "  return Result { ok: true, value: v, error: \"\" };\n}\n"
     "fn main() {\n  let p = alloc_or_fail(" + BIG + ");\n"
     "  println(p.ok);\n  println(p.error);\n"
     "  let q = alloc_or_fail(3);\n"
     "  println(q.ok);\n  println(len(q.value));\n}\n",
     "false\nout of memory\ntrue\n3\n"),
    ("? propagation: Ok passes through",
     IMP + "fn alloc_or_fail(n: int) -> Result<[int], str> {\n"
     "  let v = try_alloc(n)?;\n"
     "  return Result { ok: true, value: v, error: \"\" };\n}\n"
     "fn main() {\n  let q = alloc_or_fail(2);\n"
     "  println(q.ok);\n  println(q.value[1]);\n}\n",
     "true\n0\n"),
    ("n evaluated once (side effect counted once)",
     IMP + "fn bump(x: int) -> int { return x + 1; }\n"
     "fn main() {\n  let mut c = 0;\n"
     "  c = bump(c);\n"
     "  let r = try_alloc(c + 2);\n"
     "  println(len(r.value));\n  println(c);\n}\n",
     "3\n1\n"),
]

# (name, program, error fragment) — must be rejected at check time.
REJECT_CASES = [
    ("no argument",
     IMP + "fn main() {\n  let r = try_alloc();\n}\n",
     "try_alloc() takes exactly one int argument"),
    ("two arguments",
     IMP + "fn main() {\n  let r = try_alloc(1, 2);\n}\n",
     "try_alloc() takes exactly one int argument"),
    ("str argument",
     IMP + "fn main() {\n  let r = try_alloc(\"5\");\n}\n",
     "try_alloc() takes exactly one int argument"),
    ("float argument",
     IMP + "fn main() {\n  let r = try_alloc(1.5);\n}\n",
     "try_alloc() takes exactly one int argument"),
    ("missing result.fg import",
     "fn main() {\n  let r = try_alloc(5);\n}\n",
     "try_alloc() needs import \"result.fg\""),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "allocfail_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    exp_demo = ("true\n5\n0\n0\nfalse\nbad size\ntrue\n0\n"
                "false\nout of memory\nfalse\nout of memory\ntrue\n3\n")
    if not check("allocfail demo", r.returncode == 0 and r.stdout == exp_demo,
                 f"(rc={r.returncode} out={r.stdout!r} err={r.stderr[:200]!r})"):
        failures.append("allocfail demo")
    for name, prog, expected in OK_CASES:
        with tempfile.NamedTemporaryFile("w", suffix=".fg", delete=False,
                                        dir=ROOT) as f:
            f.write(prog)
            path = f.name
        try:
            r = run([sys.executable, os.path.join(ROOT, "forge.py"),
                     "run", path], ROOT)
            ok = r.returncode == 0 and r.stdout == expected
            if not check(name, ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:200]!r})"):
                failures.append(name)
        finally:
            os.unlink(path)
    for name, prog, frag in REJECT_CASES:
        with tempfile.NamedTemporaryFile("w", suffix=".fg", delete=False,
                                        dir=ROOT) as f:
            f.write(prog)
            path = f.name
        try:
            r = run([sys.executable, os.path.join(ROOT, "forge.py"),
                     "check", path], ROOT)
            ok = r.returncode != 0 and frag in (r.stderr + r.stdout)
            if not check(name, ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:200]!r})"):
                failures.append(name)
        finally:
            os.unlink(path)
    # Emitted C: calloc is the allocation, and the Err strings are there.
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit", demo],
            ROOT)
    c_src = r.stdout
    ok = (r.returncode == 0 and "calloc" in c_src
          and "out of memory" in c_src and "bad size" in c_src)
    if not check("emitted C uses calloc + Err strings", ok,
                 f"(rc={r.returncode})"):
        failures.append("emitted C")
    # big32 and WASM reject try_alloc with a named error.
    for target, flag in (("big32", "--target"), ("wasm", "--target")):
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "build",
                 flag, target, demo], ROOT)
        ok = r.returncode != 0 and "try_alloc is not supported" in (
            r.stderr + r.stdout)
        if not check(f"{target} rejects try_alloc", ok,
                     f"(rc={r.returncode} err={r.stderr[:200]!r})"):
            failures.append(f"{target} gate")
    # ASan: the success + bad-size + zero-size paths run clean.
    # (The huge-allocation path is NOT under ASan: ASan refuses to
    # attempt a 2^63-byte calloc at all — its own maximum-size abort,
    # not a try_alloc bug. That path is covered by the non-ASan run
    # above, where calloc returns NULL and try_alloc returns Err.)
    asan_prog = (IMP + "fn main() {\n  let r = try_alloc(5);\n"
                 "  println(r.ok);\n  println(len(r.value));\n"
                 "  let mut v = r.value;\n  v[0] = 7;\n  println(v[0]);\n"
                 "  let bad = try_alloc(-1);\n  println(bad.ok);\n  println(bad.error);\n"
                 "  let z = try_alloc(0);\n  println(z.ok);\n  println(len(z.value));\n}\n")
    asan_exp = "true\n5\n7\nfalse\nbad size\ntrue\n0\n"
    with tempfile.TemporaryDirectory() as td:
        src_path = os.path.join(td, "asan_prog.fg")
        c_path = os.path.join(td, "allocfail.c")
        bin_path = os.path.join(td, "allocfail_asan")
        with open(src_path, "w") as f:
            f.write(asan_prog)
        r = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit",
                 src_path], ROOT)
        with open(c_path, "w") as f:
            f.write(r.stdout)
        cc = run(["cc", "-g", "-fsanitize=address", "-o", bin_path, c_path,
                  "-lssl", "-lcrypto", "-lm"], ROOT)
        if cc.returncode != 0:
            check("ASan build", False, f"(cc err={cc.stderr[:300]!r})")
            failures.append("ASan build")
        else:
            r = run([bin_path], ROOT)
            ok = r.returncode == 0 and r.stdout == asan_exp
            if not check("ASan run clean", ok,
                         f"(rc={r.returncode} out={r.stdout!r} "
                         f"err={r.stderr[:300]!r})"):
                failures.append("ASan run")
    if failures:
        print(f"FAILURES: {len(failures)}: {failures}")
        return 1
    print(f"ALL PASS ({1 + len(OK_CASES) + len(REJECT_CASES) + 4} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
