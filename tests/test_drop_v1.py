"""Top-500 #33: destructor hooks v1 (tests/test_drop_v1.py).
A struct method named `drop` runs automatically when an
owned binding of that struct dies: block end, function
end, return path, break — every site funnels through
_emit_free_one, and the hook fires before the free so
drop still sees live fields. The hook passes an
independently owned copy (the call-arg pattern), and
the drop method's own receiver parameter never hooks
(otherwise drop would call itself forever — caught by
the first demo run, which printed forever until killed).
Native-only in v1; big32/WASM/freestanding reject.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

EXPECTED = "before\ninside\ndropped\n7\nafter\nbag inside\n3\ndone\n"

DROP_EXTRA = (
    "struct Guard {\n"
    "  id: int;\n"
    "}\n"
    "impl Guard {\n"
    "  fn drop(g: Guard, x: int) {\n"
    "  }\n"
    "}\n"
    "fn main() {\n"
    "  let g = Guard { id: 1 };\n"
    "}\n"
)

DROP_RET = (
    "struct Guard {\n"
    "  id: int;\n"
    "}\n"
    "impl Guard {\n"
    "  fn drop(g: Guard) -> int {\n"
    "    return 1;\n"
    "  }\n"
    "}\n"
    "fn main() {\n"
    "  let g = Guard { id: 1 };\n"
    "}\n"
)

DROP_FREE = (
    "struct Guard {\n"
    "  id: int;\n"
    "}\n"
    "impl Guard {\n"
    "  fn drop(g: Guard) {\n"
    "  }\n"
    "}\n"
    "fn main() {\n"
    "  let g = Guard { id: 1 };\n"
    "}\n"
)


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          timeout=30)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    forge = [sys.executable, os.path.join(ROOT, "forge.py")]
    demo = os.path.join(ROOT, "examples", "drop_demo.fg")
    r = run(forge + ["run", demo], ROOT)
    if not check("drop demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("drop demo runs")
    elif not check("drop results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("drop results")
    with tempfile.TemporaryDirectory() as td:
        for name, prog, needle in (
                ("drop extra param", DROP_EXTRA,
                 "drop must take only its struct as receiver"),
                ("drop non-void", DROP_RET, "drop must return void")):
            p = os.path.join(td, "d.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run(forge + ["check", p], ROOT)
            if not check(name, rr.returncode != 0
                         and needle in (rr.stdout + rr.stderr),
                         (rr.stdout + rr.stderr)[-200:]):
                failures.append(name)
        p = os.path.join(td, "f.fg")
        with open(p, "w") as f:
            f.write(DROP_FREE)
        rf = run(forge + ["check", "--freestanding", p], ROOT)
        if not check("freestanding rejects drop", rf.returncode != 0
                     and "drop is not supported in freestanding v1"
                     in (rf.stdout + rf.stderr),
                     (rf.stdout + rf.stderr)[-200:]):
            failures.append("freestanding rejects drop")
        rb = run(forge + ["build", "--target", "big32", demo], ROOT)
        if not check("big32 rejects drop", rb.returncode != 0
                     and "big32: drop is not supported in v1"
                     in (rb.stdout + rb.stderr),
                     (rb.stdout + rb.stderr)[-200:]):
            failures.append("big32 rejects drop")
        rw = run(forge + ["emit-wasm", "-o", os.path.join(td, "d.wasm"),
                          demo], ROOT)
        if not check("wasm rejects drop", rw.returncode != 0
                     and "wasm: drop is not supported in v1"
                     in (rw.stdout + rw.stderr),
                     (rw.stdout + rw.stderr)[-200:]):
            failures.append("wasm rejects drop")
    rf = run(forge + ["fmt", demo], ROOT)
    if not check("fmt runs", rf.returncode == 0, rf.stderr.strip()):
        failures.append("fmt runs")
    else:
        rf2 = run(forge + ["fmt", "--check", demo], ROOT)
        if not check("fmt idempotent", rf2.returncode == 0, rf2.stderr.strip()):
            failures.append("fmt idempotent")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
