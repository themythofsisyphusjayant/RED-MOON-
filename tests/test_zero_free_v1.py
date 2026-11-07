"""Top-500 #35: zeroing on free v1 (tests/test_zero_free_v1.py).
Default-on: every heap buffer the native runtime frees is
zeroed (memset to 0) before free() — arrays (all element
types, nested, struct arrays), strs, read_bytes temp buffers,
the HTTP recv buffer, and spawn thread args. No new syntax;
big32/WASM free paths are untouched in v1 (no gate — programs
there simply do not get zeroing yet); mmap is munmap, not
free, and is out of scope.

Freed memory is unobservable from Qasida by design, so the
proof is at the C level: the emitted C must contain
memset-before-free at every site, and a C probe (plain cc,
-O0, NOT ASan — reading a just-freed buffer is the point)
built from the ACTUAL emitted preamble must read all zeros
after a sole-holder free, and must NOT zero a shared buffer
on a refcount dec.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

EXPECTED = "4\n2\n3\ntwo\n3\n20\n7\nsecret\n"

# (name, program, expected stdout) — must run clean.
OK_CASES = [
    ("int array freed at scope end",
     "fn main() {\n  let a: [int] = [1, 2, 3];\n  println(a[0] + a[2]);\n}\n",
     "4\n"),
    ("float array freed at scope end",
     "fn main() {\n  let f: [float] = [1.5, 2.5];\n  println(len(f));\n}\n",
     "2\n"),
    ("bool array freed at scope end",
     "fn main() {\n  let b: [bool] = [true, false, true];\n  println(len(b));\n}\n",
     "3\n"),
    ("str array freed at scope end",
     "fn main() {\n  let s: [str] = [\"one\", \"two\"];\n  println(s[1]);\n}\n",
     "two\n"),
    ("nested arrays freed at scope end",
     "fn main() {\n  let n: [[int]] = [[1, 2], [3, 4]];\n  println(n[1][0]);\n}\n",
     "3\n"),
    ("struct with array and str fields",
     "struct Bag { vals: [int]; name: str; }\nfn main() {\n"
     "  let bag: Bag = Bag { vals: [10, 20], name: \"bag\" };\n"
     "  println(bag.vals[1]);\n  println(bag.name);\n}\n",
     "20\nbag\n"),
    ("tuple with str element",
     "fn main() {\n  let t: (int, str) = (7, \"seven\");\n"
     "  println(t.0);\n  println(t.1);\n}\n",
     "7\nseven\n"),
    ("block-scoped free",
     "fn main() {\n  if true {\n    let a: [int] = [5, 6];\n    println(a[1]);\n  }\n  println(0);\n}\n",
     "6\n0\n"),
    ("function parameter freed at fn end",
     "fn first(xs: [int]) -> int { return xs[0]; }\nfn main() {\n"
     "  println(first([8, 9]));\n}\n",
     "8\n"),
    ("shared array freed twice, no crash",
     "fn main() {\n  let a: [int] = [1, 2];\n  let b = a;\n"
     "  println(a[0] + b[1]);\n}\n",
     "3\n"),
    ("string concat temp freed",
     "fn main() {\n  let s: str = \"ab\" + \"cd\";\n  println(s);\n}\n",
     "abcd\n"),
    ("read_bytes temp freed",
     "fn main() {\n  let wrote: bool = write_file(\"/tmp/zero_free_probe.bin\", \"Hi\");\n"
     "  let bs: [int] = read_bytes(\"/tmp/zero_free_probe.bin\");\n"
     "  println(bs[0]);\n}\n",
     "72\n"),
]

# Fragments that must appear in the emitted C of the demo.
EMIT_FRAGS = [
    "memset(a.data, 0, (size_t)a.cap * sizeof(*a.data))",
    "memset(p, 0, strlen(p) + 1)",
    "memset(raw, 0, (size_t)sz)",
    "memset(buf, 0, 8192)",
]

PROBE_MAIN = r"""
/* glibc's free() writes its own freelist metadata into the first
   16 bytes of a freed chunk (tcache next + key), so a just-freed
   buffer can only be observed past byte 16. Every buffer here is
   therefore 64 bytes or more, and only the tail is checked. The
   memset itself is also asserted in the emitted C above. */
int main(void) {
    int fails = 0;
    /* Sole-holder int array: tail must read zero. */
    ForgeIntArray a;
    a.len = 8; a.cap = 8; a.ref = forge_arr_ref_new();
    a.data = (long long *)malloc(8 * sizeof(long long));
    for (int i = 0; i < 8; i++) a.data[i] = 0x4141414141414141LL;
    long long *ad = a.data;
    forge_int_array_free(a);
    for (int i = 2; i < 8; i++) if (ad[i] != 0) { printf("FAIL int-array not zeroed\n"); fails++; break; }
    /* Shared array: a dec from 2 to 1 must NOT zero the data. */
    ForgeIntArray s;
    s.len = 8; s.cap = 8; s.ref = forge_arr_ref_new(); forge_arr_inc(s.ref);
    s.data = (long long *)malloc(8 * sizeof(long long));
    for (int i = 0; i < 8; i++) s.data[i] = 0x4141414141414141LL;
    forge_int_array_free(s);
    for (int i = 0; i < 8; i++) if (s.data[i] != 0x4141414141414141LL) { printf("FAIL shared array zeroed early\n"); fails++; break; }
    forge_int_array_free(s);
    for (int i = 2; i < 8; i++) if (s.data[i] != 0) { printf("FAIL shared array not zeroed at last free\n"); fails++; break; }
    /* Str: tail bytes (incl. NUL) must read zero. The string is
       37 chars, so the memset covers bytes 0..37 only. */
    char *str = forge_copy_str("secret-secret-secret-secret-secret-se");
    char *sp = str;
    forge_free_str(str);
    for (int i = 16; i <= 37; i++) if (sp[i] != 0) { printf("FAIL str not zeroed\n"); fails++; break; }
    /* Float array: tail bytes must read zero. */
    ForgeFloatArray f;
    f.len = 8; f.cap = 8; f.ref = forge_arr_ref_new();
    f.data = (double *)malloc(8 * sizeof(double));
    for (int i = 0; i < 8; i++) f.data[i] = 2.5;
    double *fd = f.data;
    forge_float_array_free(f);
    for (int i = 2; i < 8; i++) if (fd[i] != 0.0) { printf("FAIL float array not zeroed\n"); fails++; break; }
    /* Str array: element-string tails and the pointer-array tail zeroed. */
    ForgeStrArray sa;
    sa.len = 4; sa.cap = 4; sa.ref = forge_arr_ref_new();
    sa.data = (char **)malloc(4 * sizeof(char *));
    for (int i = 0; i < 4; i++) sa.data[i] = forge_copy_str("secret-secret-secret-secret-secret-se");
    char *e0 = sa.data[0]; char *e3 = sa.data[3]; char **sd = sa.data;
    forge_str_array_free(sa);
    for (int i = 16; i <= 37; i++) if (e0[i] != 0 || e3[i] != 0) { printf("FAIL str array not zeroed\n"); fails++; break; }
    if (sd[2] != NULL || sd[3] != NULL) { printf("FAIL str pointer array not zeroed\n"); fails++; }
    if (fails == 0) printf("PROBE-OK\n");
    return fails != 0;
}
"""


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    demo = os.path.join(ROOT, "examples", "zero_free_demo.fg")
    r = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", demo],
            ROOT)
    if not check("zero-free demo runs", r.returncode == 0,
                 r.stderr.strip().splitlines()[-1] if r.stderr else ""):
        failures.append("zero-free demo runs")
    elif not check("zero-free demo results", r.stdout == EXPECTED,
                   repr(r.stdout)):
        failures.append("zero-free demo results")
    with tempfile.TemporaryDirectory() as td:
        for name, prog, want in OK_CASES:
            p = os.path.join(td, "c.fg")
            with open(p, "w") as f:
                f.write(prog)
            rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "run", p],
                     ROOT)
            ok = rr.returncode == 0 and rr.stdout == want
            if not check(f"{name} runs", ok,
                         repr(rr.stdout) + (rr.stderr.strip().splitlines() or [""])[-1]):
                failures.append(name)
        # Emitted C must zero before free at every site.
        rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit", demo],
                 ROOT)
        if not check("emit runs", rr.returncode == 0, rr.stderr.strip()):
            failures.append("emit runs")
        else:
            for frag in EMIT_FRAGS:
                if not check(f"emitted C has {frag[:40]}", frag in rr.stdout,
                             "missing"):
                    failures.append(f"emit: {frag[:40]}")
            # Nested-array and struct-array inline frees zero too.
            nested = os.path.join(td, "n.fg")
            with open(nested, "w") as f:
                f.write("struct B { vals: [int]; }\nfn main() {\n"
                        "  let n: [[int]] = [[1, 2], [3, 4]];\n"
                        "  let bs: [B] = [B { vals: [7] }];\n"
                        "  println(n[0][0] + bs[0].vals[0]);\n}\n")
            rn = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit", nested],
                     ROOT)
            # Nested free: the outer buffer is memset after the
            # element frees. Struct-array free: the generator names
            # its parameter `a`, so check the memset inside the
            # forge_B_array_free body, not a `bs.data` fragment.
            ok = (rn.returncode == 0
                  and "memset(n.data, 0, (size_t)n.cap * sizeof(*n.data))" in rn.stdout)
            bi = rn.stdout.find("forge_B_array_free")
            ok = ok and bi >= 0 and "memset(a.data, 0, (size_t)a.cap * sizeof(*a.data))" in rn.stdout[bi:bi + 800]
            if not check("nested/struct-array inline frees zero", ok,
                         rn.stderr.strip().splitlines()[-1] if rn.stderr else ""):
                failures.append("nested/struct-array inline frees")
            # Spawn thread-arg free zeroes.
            sp = os.path.join(td, "s.fg")
            with open(sp, "w") as f:
                f.write("fn work(v: int) -> void { println(v); }\n"
                        "fn main() {\n  spawn work(1);\n  println(1);\n}\n")
            rs = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit", sp],
                     ROOT)
            if not check("spawn arg free zeroes",
                         rs.returncode == 0
                         and "memset(arg, 0, sizeof(long long))" in rs.stdout,
                         rs.stderr.strip().splitlines()[-1] if rs.stderr else ""):
                failures.append("spawn arg free")
        # C probe: build from the ACTUAL emitted preamble (truncate
        # the demo's C at main, append the probe main), -O0, no ASan.
        rr = run([sys.executable, os.path.join(ROOT, "forge.py"), "emit", demo],
                 ROOT)
        if rr.returncode == 0:
            cut = rr.stdout.rfind("\nint main(")
            if cut < 0:
                if not check("probe: main found in emitted C", False, ""):
                    failures.append("probe main")
            else:
                probe_c = os.path.join(td, "probe.c")
                with open(probe_c, "w") as f:
                    f.write(rr.stdout[:cut] + "\n" + PROBE_MAIN)
                cc = run(["cc", "-O0", "-std=gnu11", "-pthread", "-o",
                          os.path.join(td, "probe"), probe_c,
                          "-lm", "-lssl", "-lcrypto"], td)
                if not check("probe compiles", cc.returncode == 0,
                             cc.stderr.strip().splitlines()[-1] if cc.stderr else ""):
                    failures.append("probe compiles")
                else:
                    pr = run([os.path.join(td, "probe")], td)
                    if not check("probe: freed buffers read zero",
                                 pr.returncode == 0 and "PROBE-OK" in pr.stdout,
                                 pr.stdout.strip()):
                        failures.append("probe zeroed")
        try:
            os.remove("/tmp/zero_free_probe.bin")
        except OSError:
            pass
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
