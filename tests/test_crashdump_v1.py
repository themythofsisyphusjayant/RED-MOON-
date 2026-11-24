#!/usr/bin/env python3
"""Top-500 #60: crash dumps in freestanding mode — stage A (big32) + D1.

Stage A: on big32, fail()/assert()/float->int-cast failure prints
  qasida: crash: <msg>
followed by the pinned 32-line register dump (pc + the 30
trap-frame-order registers + sp, 0x + 8 lowercase hex digits)
over UART, then halts with a0 = 1. The snapshot is taken at the
fail site, BEFORE the message is evaluated or any helper runs,
so the dumped registers are the failure's own (t0 = 41 in the
fail case below proves it: the message print would have put the
message address in t0 instead). pc is ra at the fail site — the
instruction after the fail call, off by one call — so the test
asserts pc == ra and the hex format, never an exact pc value
(the address is pure code layout and shifts with any codegen
change). The t/a/s register values ARE pinned exactly: they are
the current temp allocation for these exact programs, and a
future allocator change must update them here (not silently).

D1 (both compilers): a string literal as the fail()/assert()
message is exempt from the freestanding heap rejection — it
lowers to a static C string / static data. Any other str
expression (variable, concatenation) is still rejected
freestanding. The crash_handler hook (stage B) is validated
here too: exactly (code: int, pc: int) -> void, not generic,
not extern, freestanding only; fail()/assert() inside it is
rejected (it would recurse).

Native freestanding (stage A): fail()/assert() with a literal
message routes through forge_fail and halts; a no-fail
freestanding program is unaffected by the forge_fail signature
change.

Stage C: the native half. forge_fail snapshots the surviving
registers (rip/rbx/rbp/r12-r15/rsp), prints the pinned partial
transcript (`qasida: crash: <msg>` + `partial` + 8 register
lines, 0x + 16 lowercase hex) to fd 2 via a raw write syscall,
then halts. rip is the return address at the fail handler; the
dump is visible under Linux, invisible on bare metal. .text
cost: a no-fail program pays 0 (GCC eliminates the unreferenced
static helpers); a failing program pays the dump code
(~590 bytes at stage C, fail .text 291 -> 881).

Stage B: the crash_handler hook. On fail, the compiler
(1) snapshots registers, (2) calls user-defined
crash_handler(code, pc) if defined with exactly that name and
signature, (3) prints the pinned dump, (4) halts. Codes: 0
OTHER, 1 USER, 2 ASSERT, 3 F2I, 4 OVERFLOW, 5 DIVZERO, 6
BOUNDS, 7 OOM. The hook runs after the snapshot, so the dumped
values are the fail site's own (the hook's poke32s cannot
change them). On big32 the hook poke32s a marker + code/pc
into RAM (0x8000/0x8004/0x8008) and the test reads them back
from the model's dmem; on native there is no mapped RAM to
poke (0x8000 is unmapped under Linux), so the native hook
does a safe local computation and the test asserts the
transcript + halt + the call in the disassembly. A program
with no hook is behaviour-identical to A+C (same transcript
and halt); on big32 its .s is byte-identical too (no hook
call emitted), while on native its .text grows by the
hook-check code in forge_fail (+218 bytes: fail .text
881 -> 1099). -ffreestanding is passed for freestanding
builds (both compilers): without it GCC rewrites the
strlen-shaped loop in forge_crash_msg into a strlen() call,
which cannot link under -nostdlib (found 24 Nov 2026).

big32 runs under the Python compiler only (the hosted driver's
emit-big32 routes to the same RV backend and is byte-identical —
verified in this test); the checker/native parts run under BOTH
compilers. QASIDA_COMPILER is scrubbed in run() so a "hosted"
run really uses the hosted driver (the #50 lesson).

Exits 0 only if every check passes. Prints one PASS/FAIL line
per check (109 checks).
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL_DIR = os.path.expanduser("~/workspace/big32/tools")
KERNEL = os.path.expanduser(
    "~/workspace/os-repo-staging/examples/os/kernel_unified.fg")

FAILURES = []

LABELS = ["pc", "ra", "gp", "tp", "t0", "t1", "t2", "s0", "s1",
          "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7",
          "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9",
          "s10", "s11", "t3", "t4", "t5", "t6", "sp"]
# Register index in the model's regs[] list (x0=zero .. x31=t6).
REG_IDX = {"ra": 1, "sp": 2, "gp": 3, "tp": 4, "t0": 5, "t1": 6,
           "t2": 7, "s0": 8, "s1": 9, "a0": 10, "a1": 11, "a2": 12,
           "a3": 13, "a4": 14, "a5": 15, "a6": 16, "a7": 17,
           "s2": 18, "s3": 19, "s4": 20, "s5": 21, "s6": 22,
           "s7": 23, "s8": 24, "s9": 25, "s10": 26, "s11": 27,
           "t3": 28, "t4": 29, "t5": 30, "t6": 31}


def run(args, cwd, timeout=120):
    env = dict(os.environ)
    env.pop("QASIDA_COMPILER", None)
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          env=env, timeout=timeout)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    if not ok:
        FAILURES.append(name)
    return ok


def write_prog(d, prog, name="prog.fg"):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(prog)
    return path


def zeros(**over):
    d = {name: 0 for name in LABELS if name not in ("pc", "ra")}
    d.update(over)
    return d


# Exact dumped values (pc/ra excluded: asserted via pc == ra).
FAIL_VALS = zeros(t0=0x29, t1=0x01, t2=0x2A, t3=0x01, t4=0x01,
                  t5=0x2A, s0=0xFFF4, sp=0xF7F4)
ASSERT_VALS = zeros(t0=0x05, t2=0x06, s0=0xFFF4, sp=0xF7F4)
F2I_VALS = zeros(t1=0xC1, t2=0x002D78EC, a0=0x60AD78EC, t6=0x9E,
                 s0=0xFFF4, sp=0xF7F4)

FAIL_PROG = """fn main() -> int {
  let x: int = 41;
  let y: int = 1;
  let z: int = x + y;
  if z == 42 {
    fail("boom");
  }
  return 0;
}
"""

ASSERT_PROG = """fn main() -> int {
  let x: int = 5;
  assert(x == 6, "x is not six");
  return 0;
}
"""

F2I_PROG = """fn main() -> int {
  let f: float = 100000000000000000000.0;
  let i: int = f as int;
  return i;
}
"""

NOFAIL_PROG = """fn main() -> int {
  let x: int = 40 + 2;
  return x;
}
"""

FPRINT_PROG = """fn main() -> int {
  let f: float = 1.5;
  print(f);
  return 0;
}
"""


def parse_dump(uart, msg):
    """Parse the UART transcript into {label: int}; None if malformed."""
    lines = uart.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    if len(lines) != 33:
        return None
    if lines[0] != f"qasida: crash: {msg}":
        return None
    out = {}
    for i, name in enumerate(LABELS):
        line = lines[1 + i]
        if not line.startswith(f"  {name} 0x"):
            return None
        hexpart = line[len(f"  {name} 0x"):]
        if len(hexpart) != 8 or any(c not in "0123456789abcdef"
                                   for c in hexpart):
            return None
        out[name] = int(hexpart, 16)
    return out


def model_run(hexpath):
    sys.path.insert(0, MODEL_DIR)
    import model as big32_model
    return big32_model.run(hexpath)


def build_big32(d, prog, name, freestanding=False):
    path = write_prog(d, prog, name + ".fg")
    out = os.path.join(d, name)
    args = FORGE + ["--python", "build", path, "--target", "big32"]
    if freestanding:
        args += ["--freestanding"]
    r = run(args + ["-o", out], ROOT)
    return r, out, out + ".s", out + ".hex"


def dump_checks(tag, uart, msg, want, res):
    """The five per-case dump checks; res is the model result dict."""
    got = parse_dump(uart, msg)
    check(f"{tag} transcript structure (33 lines, labels in order)",
          got is not None, repr(uart[:120]))
    if got is None:
        check(f"{tag} exact register values", False, "unparsable")
        check(f"{tag} pc == ra", False, "unparsable")
        check(f"{tag} preserved regs match model", False, "unparsable")
        check(f"{tag} halts with a0=1", False, "unparsable")
        return
    bad = [(k, got[k], want[k]) for k in want if got[k] != want[k]]
    check(f"{tag} exact register values", not bad,
          f"mismatches={bad[:4]}" if bad else "")
    check(f"{tag} pc == ra (return address at fail site)",
          got["pc"] == got["ra"] and 0 < got["pc"] < 0x10000,
          f"pc={got['pc']:#x} ra={got['ra']:#x}")
    # gp/tp/s0/sp are never temps and never touched by the dump
    # path, so the model state at halt must equal the dump.
    regs = res["regs"]
    cross = [(k, got[k], regs[REG_IDX[k]])
             for k in ("gp", "tp", "s0", "sp") if got[k] != regs[REG_IDX[k]]]
    check(f"{tag} preserved regs match model", not cross,
          f"mismatches={cross}" if cross else "")
    check(f"{tag} halts with a0=1",
          res["halted"] is True and res["a0"] == 1,
          f"halted={res['halted']} a0={res['a0']}")


# --- Stage C: native freestanding partial dump. ---
NATIVE_LABELS = ["rip", "rbx", "rbp", "r12", "r13", "r14", "r15", "rsp"]

OVF_PROG = """fn main() -> int {
  let x: int = 9223372036854775807;
  let y: int = x + 1;
  return y;
}
"""

# --- Stage B: the crash_handler hook. ---
# big32 hook: poke32s a marker + code/pc into RAM (0x8000 is the
# freestanding test's scratch area; 0x10000000 is the UART, not RAM).
HOOK_PROG = """fn crash_handler(code: int, pc: int) {
  poke32(32768, 3735928559);
  poke32(32772, code);
  poke32(32776, pc);
}

fn main() -> int {
  let x: int = 41;
  let y: int = 1;
  let z: int = x + y;
  if z == 42 {
    fail("boom");
  }
  return 0;
}
"""

# Native hook: poke32 to RAM is impossible under Linux (0x8000 is
# unmapped), so the hook does a safe local computation on its
# params and returns; the test asserts the transcript + halt +
# the call in the disassembly.
HOOK_NATIVE_PROG = """fn crash_handler(code: int, pc: int) {
  let mut total: int = code + pc;
  total = total + 1;
}

fn main() -> int {
  fail("boom");
  return 0;
}
"""


def has_disasm_call(path, symbol):
    """True when objdump -d shows a call to <symbol> in path."""
    r = subprocess.run(["objdump", "-d", path], capture_output=True,
                       text=True, timeout=30)
    return f"call" in r.stdout and f"<{symbol}>" in r.stdout


def parse_native_dump(stderr_text, msg):
    """Parse the native partial transcript; returns {label: int} or None.

    Pinned format (10 lines): `qasida: crash: <msg>`, `partial`,
    then ` <reg> 0x<16 lowercase hex>` for rip/rbx/rbp/r12-r15/rsp.
    rip is the return address at the fail handler (the fail site
    for a direct fail(), inside the inlined helper for a runtime
    fault); the callee-saved values are the values at the snapshot
    point and are format-checked only, never pinned exactly.
    """
    lines = stderr_text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    if len(lines) != 10:
        return None
    if lines[0] != f"qasida: crash: {msg}":
        return None
    if lines[1] != "partial":
        return None
    out = {}
    for i, name in enumerate(NATIVE_LABELS):
        line = lines[2 + i]
        if not line.startswith(f" {name} 0x"):
            return None
        hexpart = line[len(f" {name} 0x"):]
        if len(hexpart) != 16 or any(c not in "0123456789abcdef"
                                     for c in hexpart):
            return None
        out[name] = int(hexpart, 16)
    return out


def text_range(path):
    """(.text vaddr, size) from readelf; (None, None) on failure.

    readelf -S prints each section on TWO lines: the first holds
    the address (5th whitespace token), the second holds the size
    (1st whitespace token).
    """
    r = subprocess.run(["readelf", "-S", path], capture_output=True,
                       text=True, timeout=30)
    lines = r.stdout.split("\n")
    for i, line in enumerate(lines):
        if ".text" in line and "PROGBITS" in line:
            parts = line.split()
            try:
                vaddr = int(parts[4], 16)
                size = int(lines[i + 1].split()[0], 16)
            except (ValueError, IndexError):
                return None, None
            return vaddr, size
    return None, None


def text_size(path):
    """The `size` text column (all text sections); None on failure."""
    r = subprocess.run(["size", path], capture_output=True, text=True,
                       timeout=30)
    lines = r.stdout.strip().split("\n")
    if len(lines) >= 2:
        try:
            return int(lines[1].split()[0])
        except (ValueError, IndexError):
            return None
    return None


def native_run_dump(path, td):
    """Run a halting freestanding binary, capture its stderr dump and
    its load base from /proc/<pid>/maps. Returns (stderr, base, alive):
    alive is True when the process was still running after 1s (it
    halts in forge_fail's infinite loop rather than exiting)."""
    import time
    proc = subprocess.Popen([path], cwd=td, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    time.sleep(1)
    alive = proc.poll() is None
    base = None
    try:
        with open(f"/proc/{proc.pid}/maps") as f:
            for line in f:
                if path in line:
                    base = int(line.split("-")[0], 16)
                    break
    except OSError:
        base = None
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    _, stderr = proc.communicate()
    return stderr, base, alive


def main():
    print("D1 + hook validation (both compilers)")
    cases = [
        ("fail literal checks freestanding",
         "fn main() -> int {\n  fail(\"boom\");\n  return 0;\n}\n",
         True, None),
        ("assert literal checks freestanding",
         "fn main() -> int {\n  let x: int = 5;\n  assert(x == 6, \"nope\");\n  return 0;\n}\n",
         True, None),
        ("str-var fail message rejected freestanding",
         "fn main() -> int {\n  let s: str = \"boom\";\n  fail(s);\n  return 0;\n}\n",
         False, "heap"),
        ("str-concat fail message rejected freestanding",
         "fn main() -> int {\n  fail(\"bo\" + \"om\");\n  return 0;\n}\n",
         False, "heap"),
        ("valid crash_handler checks freestanding",
         "fn crash_handler(code: int, pc: int) {\n}\nfn main() -> int {\n  return 0;\n}\n",
         True, None),
        ("crash_handler wrong arity rejected",
         "fn crash_handler(code: int) {\n}\nfn main() -> int {\n  return 0;\n}\n",
         False, "exactly (code: int, pc: int)"),
        ("crash_handler wrong param type rejected",
         "fn crash_handler(code: int, pc: str) {\n}\nfn main() -> int {\n  return 0;\n}\n",
         False, "exactly (code: int, pc: int)"),
        ("crash_handler non-void return rejected",
         "fn crash_handler(code: int, pc: int) -> int {\n  return 0;\n}\nfn main() -> int {\n  return 0;\n}\n",
         False, "exactly (code: int, pc: int)"),
        ("crash_handler generic rejected",
         "fn crash_handler<T>(code: int, pc: int) {\n}\nfn main() -> int {\n  return 0;\n}\n",
         False, "cannot be generic"),
        ("crash_handler extern rejected",
         "extern fn crash_handler(code: int, pc: int);\nfn main() -> int {\n  return 0;\n}\n",
         False, "must be defined in Qasida"),
        ("fail() inside crash_handler rejected",
         "fn crash_handler(code: int, pc: int) {\n  fail(\"nope\");\n}\nfn main() -> int {\n  return 0;\n}\n",
         False, "would recurse"),
        ("assert() inside crash_handler rejected",
         "fn crash_handler(code: int, pc: int) {\n  assert(code == 1, \"nope\");\n}\nfn main() -> int {\n  return 0;\n}\n",
         False, "would recurse"),
    ]
    with tempfile.TemporaryDirectory() as td:
        for name, prog, ok_want, needle in cases:
            path = write_prog(td, prog)
            for mode, prefix in (("hosted", []), ("python", ["--python"])):
                r = run(FORGE + prefix + ["check", path, "--freestanding"],
                        ROOT)
                good = (r.returncode == 0) if ok_want else (
                    r.returncode != 0 and (needle is None or needle in r.stderr))
                check(f"{name} ({mode})", good,
                      f"rc={r.returncode} err={r.stderr.strip()[:120]!r}")
        print("crash_handler hosted rejected (both compilers)")
        path = write_prog(td, "fn crash_handler(code: int, pc: int) {\n}\n"
                               "fn main() -> int {\n  return 0;\n}\n")
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            r = run(FORGE + prefix + ["check", path], ROOT)
            check(f"crash_handler hosted rejected ({mode})",
                  r.returncode != 0 and "freestanding-only hook" in r.stderr,
                  f"rc={r.returncode} err={r.stderr.strip()[:120]!r}")

        print("native freestanding fail/assert (both compilers)")
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            path = write_prog(td, "fn main() -> int {\n  fail(\"boom\");\n"
                                   "  return 0;\n}\n")
            out = os.path.join(td, f"fs_fail_{mode}")
            r = run(FORGE + prefix + ["build", path, "--freestanding",
                                       "-o", out], ROOT)
            check(f"native freestanding fail builds ({mode})",
                  r.returncode == 0, f"err={r.stderr.strip()[:120]!r}")
            if r.returncode == 0:
                try:
                    run([out], td, timeout=5)
                    check(f"native freestanding fail halts ({mode})",
                          False, "exited instead of halting")
                except subprocess.TimeoutExpired:
                    check(f"native freestanding fail halts ({mode})", True)
            path = write_prog(td, "fn main() -> int {\n  let x: int = 5;\n"
                                   "  assert(x == 6, \"nope\");\n"
                                   "  return 0;\n}\n")
            out = os.path.join(td, f"fs_assert_{mode}")
            r = run(FORGE + prefix + ["build", path, "--freestanding",
                                       "-o", out], ROOT)
            check(f"native freestanding assert builds ({mode})",
                  r.returncode == 0, f"err={r.stderr.strip()[:120]!r}")
            if r.returncode == 0:
                try:
                    run([out], td, timeout=5)
                    check(f"native freestanding assert halts ({mode})",
                          False, "exited instead of halting")
                except subprocess.TimeoutExpired:
                    check(f"native freestanding assert halts ({mode})", True)
            path = write_prog(td, NOFAIL_PROG, "nofail_fs.fg")
            out = os.path.join(td, f"fs_nofail_{mode}")
            r = run(FORGE + prefix + ["build", path, "--freestanding",
                                       "-o", out], ROOT)
            ok = r.returncode == 0
            rc = None
            if ok:
                rr = run([out], td, timeout=30)
                rc = rr.returncode
                ok = rc == 42
            check(f"native freestanding no-fail exits 42 ({mode})", ok,
                  f"build_rc={r.returncode} run_rc={rc}")

        print("native freestanding partial dump (stage C, both compilers)")
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            for tag, prog, msg in (
                    ("fail", "fn main() -> int {\n  fail(\"boom\");\n"
                             "  return 0;\n}\n", "boom"),
                    ("overflow", OVF_PROG, "integer overflow")):
                path = write_prog(td, prog, f"fs_{tag}_C_{mode}.fg")
                out = os.path.join(td, f"fs_{tag}_C_{mode}")
                r = run(FORGE + prefix + ["build", path, "--freestanding",
                                           "-o", out], ROOT)
                check(f"stage C {tag} builds ({mode})", r.returncode == 0,
                      f"err={r.stderr.strip()[:120]!r}")
                if r.returncode != 0:
                    continue
                stderr, base, alive = native_run_dump(out, td)
                got = parse_native_dump(stderr, msg)
                check(f"stage C {tag} transcript ({mode})", got is not None,
                      repr(stderr[:120]))
                if got is not None:
                    vaddr, size = text_range(out)
                    ok = (base is not None and vaddr is not None
                          and base + vaddr <= got["rip"]
                          < base + vaddr + size)
                    check(f"stage C {tag} rip in text range ({mode})", ok,
                          f"rip={got['rip']:#x} base={base:#x} "
                          f"text=[{vaddr:#x}, +{size:#x})"
                          if base is not None and vaddr is not None
                          else "no base/text range")
                else:
                    check(f"stage C {tag} rip in text range ({mode})",
                          False, "unparsable transcript")
                check(f"stage C {tag} still halts ({mode})", alive,
                      "" if alive else "exited instead of halting")
            # .text cost: a no-fail program (forge_fail unreferenced,
            # constant-folded) pays 0 — GCC eliminates the unreferenced
            # static helpers; a failing program pays the dump code.
            path = write_prog(td, NOFAIL_PROG, f"nofail_C_{mode}.fg")
            out_nf = os.path.join(td, f"fs_nofail_C_{mode}")
            r = run(FORGE + prefix + ["build", path, "--freestanding",
                                       "-o", out_nf], ROOT)
            nf_text = text_size(out_nf) if r.returncode == 0 else None
            out_f = os.path.join(td, f"fs_fail_C_{mode}")
            f_text = text_size(out_f)
            check(f"stage C no-fail .text is 273 (delta 0) ({mode})",
                  nf_text == 273, f".text={nf_text}")
            check(f"stage C fail .text carries the dump ({mode})",
                  f_text is not None and nf_text is not None
                  and f_text > nf_text + 400,
                  f"fail .text={f_text} no-fail .text={nf_text}")

        print("stage B hook (native, both compilers)")
        for mode, prefix in (("hosted", []), ("python", ["--python"])):
            path = write_prog(td, HOOK_NATIVE_PROG,
                              f"fs_hook_B_{mode}.fg")
            out = os.path.join(td, f"fs_hook_B_{mode}")
            r = run(FORGE + prefix + ["build", path, "--freestanding",
                                       "-o", out], ROOT)
            check(f"stage B hook builds ({mode})", r.returncode == 0,
                  f"err={r.stderr.strip()[:120]!r}")
            if r.returncode != 0:
                continue
            stderr, base, alive = native_run_dump(out, td)
            got = parse_native_dump(stderr, "boom")
            check(f"stage B hook transcript ({mode})", got is not None,
                  repr(stderr[:120]))
            if got is not None:
                vaddr, size = text_range(out)
                ok = (base is not None and vaddr is not None
                      and base + vaddr <= got["rip"]
                      < base + vaddr + size)
                check(f"stage B hook rip in text range ({mode})", ok,
                      f"rip={got['rip']:#x} base={base:#x} "
                      f"text=[{vaddr:#x}, +{size:#x})"
                      if base is not None and vaddr is not None
                      else "no base/text range")
            else:
                check(f"stage B hook rip in text range ({mode})",
                      False, "unparsable transcript")
            check(f"stage B hook still halts ({mode})", alive,
                  "" if alive else "exited instead of halting")
            check(f"stage B hook call in disassembly ({mode})",
                  has_disasm_call(out, "crash_handler"))

        print("stage B hook (big32, Python compiler)")
        r, out, spath, hexpath = build_big32(td, HOOK_PROG, "cd_hook",
                                             freestanding=True)
        check("stage B big32 hook builds", r.returncode == 0,
              f"err={r.stderr.strip()[:120]!r}")
        if r.returncode == 0:
            s = open(spath).read()
            check("stage B big32 .s calls the hook",
                  "crash_handler:" in s
                  and "jal ra, crash_handler" in s)
            res = model_run(hexpath)
            # The snapshot precedes the hook, so the dump is the
            # fail site's own values (FAIL_VALS) and the preserved
            # regs still match the model at halt.
            dump_checks("stage B big32 hook",
                        res["uart"].decode("utf-8", "replace"),
                        "boom", FAIL_VALS, res)
            dmem = res["dmem"]

            def rd32(a):
                return (dmem[a] | (dmem[a + 1] << 8)
                        | (dmem[a + 2] << 16) | (dmem[a + 3] << 24))
            got = parse_dump(res["uart"].decode("utf-8", "replace"),
                             "boom")
            check("stage B big32 hook marker in RAM",
                  rd32(0x8000) == 0xDEADBEEF,
                  f"marker={rd32(0x8000):#x}")
            check("stage B big32 hook code is USER (1)",
                  rd32(0x8004) == 1, f"code={rd32(0x8004)}")
            check("stage B big32 hook pc equals dumped pc",
                  got is not None and rd32(0x8008) == got["pc"],
                  f"hook pc={rd32(0x8008):#x} "
                  f"dump pc={got['pc']:#x}" if got is not None
                  else "unparsable transcript")
        # No hook: big32 .s is byte-identical to A+C (no hook call
        # emitted); the dump itself is already covered by the
        # plain big32 fail checks below.
        r, out, spath, hexpath = build_big32(td, FAIL_PROG, "cd_nohook")
        check("stage B big32 no-hook builds", r.returncode == 0,
              f"err={r.stderr.strip()[:120]!r}")
        if r.returncode == 0:
            s = open(spath).read()
            check("stage B big32 no-hook .s has no hook call",
                  "crash_handler" not in s
                  and "jal ra, crash_handler" not in s)

        print("big32 crash dumps (Python compiler)")
        r, out, spath, hexpath = build_big32(td, FAIL_PROG, "cd_fail")
        check("big32 fail builds", r.returncode == 0,
              f"err={r.stderr.strip()[:120]!r}")
        if r.returncode == 0:
            res = model_run(hexpath)
            dump_checks("big32 fail", res["uart"].decode("utf-8", "replace"),
                        "boom", FAIL_VALS, res)
        r, out, spath, hexpath = build_big32(td, ASSERT_PROG, "cd_assert")
        check("big32 assert builds", r.returncode == 0,
              f"err={r.stderr.strip()[:120]!r}")
        if r.returncode == 0:
            res = model_run(hexpath)
            dump_checks("big32 assert",
                        res["uart"].decode("utf-8", "replace"),
                        "x is not six", ASSERT_VALS, res)
        r, out, spath, hexpath = build_big32(td, F2I_PROG, "cd_f2i")
        check("big32 f2i builds", r.returncode == 0,
              f"err={r.stderr.strip()[:120]!r}")
        if r.returncode == 0:
            res = model_run(hexpath)
            dump_checks("big32 f2i", res["uart"].decode("utf-8", "replace"),
                        "float to int cast out of range", F2I_VALS, res)
        r, out, spath, hexpath = build_big32(td, NOFAIL_PROG, "cd_nofail")
        check("big32 no-fail builds", r.returncode == 0,
              f"err={r.stderr.strip()[:120]!r}")
        if r.returncode == 0:
            s = open(spath).read()
            check("big32 no-fail: no crash dump in .s",
                  "forge_crash_dump" not in s and "forge_print_hex" not in s
                  and "qasida: crash" not in s)
            res = model_run(hexpath)
            check("big32 no-fail: runs to a0=42",
                  res["halted"] is True and res["a0"] == 42,
                  f"halted={res['halted']} a0={res['a0']}")
        r, out, spath, hexpath = build_big32(td, FPRINT_PROG, "cd_fprint")
        check("big32 float-print-only builds", r.returncode == 0,
              f"err={r.stderr.strip()[:120]!r}")
        if r.returncode == 0:
            s = open(spath).read()
            check("big32 float-print-only: no crash dump in .s "
                  "(f2i fail path unreachable, addr 0)",
                  "forge_crash_dump" not in s
                  and "forge_print_hex" not in s)
            res = model_run(hexpath)
            uart = res["uart"].decode("utf-8", "replace")
            check("big32 float-print-only: prints 1.5, a0=0",
                  res["halted"] is True and res["a0"] == 0
                  and uart.strip() == "1.5",
                  f"halted={res['halted']} a0={res['a0']} uart={uart!r}")

        print("kernel size gate (0 words)")
        out = os.path.join(td, "kernel_unified")
        r = run(FORGE + ["--python", "build", KERNEL, "--target", "big32",
                         "--freestanding", "-o", out], ROOT, timeout=300)
        check("kernel builds", r.returncode == 0,
              f"err={r.stderr.strip()[:200]!r}")
        if r.returncode == 0:
            s = open(out + ".s").read()
            check("kernel .s has no crash-dump code",
                  "forge_crash_dump" not in s
                  and "forge_print_hex" not in s
                  and "qasida: crash" not in s)
            src = open(KERNEL).read()
            check("kernel calls no fail()/assert() and has no f2i cast",
                  "fail(" not in src and "assert(" not in src
                  and " as int" not in src)
            with open(out + ".hex") as f:
                words = sum(1 for line in f if line.strip())
            print(f"  (kernel word count: {words})")
            check("kernel word count recorded", words > 0,
                  f"words={words}")

        print("rejections (pre-existing behaviour, still holds) + emit")
        path = write_prog(td, NOFAIL_PROG, "rej.fg")
        r = run(FORGE + ["build", path, "--target", "wasm",
                         "--freestanding", "-o", os.path.join(td, "w")],
                ROOT)
        check("wasm + freestanding refused",
              r.returncode != 0 and "freestanding" in r.stderr.lower(),
              f"rc={r.returncode} err={r.stderr.strip()[:120]!r}")
        r = run(FORGE + ["build", path, "--debug",
                         "--freestanding", "-o", os.path.join(td, "d")],
                ROOT)
        check("--debug + freestanding refused",
              r.returncode != 0 and "freestanding" in r.stderr.lower(),
              f"rc={r.returncode} err={r.stderr.strip()[:120]!r}")
        # NOTE: the design said hosted emit-big32 is still deferred —
        # it is not: the hosted driver emits big32 and its output is
        # byte-identical to the Python compiler's. Assert that instead.
        rh = run(FORGE + ["emit-big32", path], ROOT)
        rp = run(FORGE + ["--python", "emit-big32", path], ROOT)
        check("hosted emit-big32 works, byte-identical to python",
              rh.returncode == 0 and rp.returncode == 0
              and rh.stdout == rp.stdout,
              f"hosted_rc={rh.returncode} python_rc={rp.returncode}")

    print(f"\n{len(FAILURES)} failures" if FAILURES else "\nALL PASS")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
