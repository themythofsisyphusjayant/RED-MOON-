"""Regression test: C-helper param-consumption audit (fix track).

Batch 25 fixed write_bytes by making forge_write_bytes FREE its
array parameter on all paths — but builtin callers transfer NO
hold (unlike user functions, whose non-fresh array args are
inc'd). So the fix was only right for fresh arguments:

- fresh literal: freed, correct (the only case batch 25 tested);
- sole-holder variable: the helper freed the caller's own hold,
  later use was heap-use-after-free (audit probe P1);
- shared variable: the helper dec'd below the true holder count,
  scope-end free then read freed memory (audit probe P2).

The fix makes write_bytes follow the ordinary function-parameter
rule in native gen_expr: a NON-FRESH array argument arrives
wrapped in a temp with forge_arr_inc (exactly the user-function
call pattern), which the helper frees; fresh arguments pass
as-is and are freed. The path stays borrowed, like every other
str parameter. Other helpers audited and found clean by code
reading + probes: file_exists, read_file, write_file, read_bytes,
mmap_open, parse_float/int, split (copies elements), join,
substr, trim, starts/ends_with, parallel_dot/matmul (join before
return, no frees), http_get, str_at, concat, refcount (explicit
borrow), weak_register (borrows + stores; variable args clean).

Deliberately NOT fixed here (documented limits, own follow-ups):
fresh-str-temp leaks (a fresh heap str passed to a builtin and
discarded — e.g. write_file(p, "a" + "b"), println("a" + "b"),
write_file(dst, read_file(src)) — leaks the temp); weak_new on
a fresh temp registers an entry that never dies (still-reachable,
not ASan-flagged).

NO push for this fix (PUSH HOLD 3 Nov 2026).
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PROGS = [
    ("var_sole",
     "fn main() {\n"
     "  let d = [72, 105];\n"
     "  let ok = write_bytes(\"/tmp/chelp_var.bin\", d);\n"
     "  println(ok);\n"
     "  println(d[0]);\n"
     "  println(len(d));\n"
     "}\n",
     "true\n72\n2\n"),
    ("var_shared",
     "fn main() {\n"
     "  let d = [1, 2];\n"
     "  let e = d;\n"
     "  let ok = write_bytes(\"/tmp/chelp_shared.bin\", d);\n"
     "  println(ok);\n"
     "  println(e[0]);\n"
     "  println(e[1]);\n"
     "}\n",
     "true\n1\n2\n"),
    ("fresh",
     "fn main() {\n"
     "  let ok = write_bytes(\"/tmp/chelp_fresh.bin\", [72, 105]);\n"
     "  println(ok);\n"
     "  let back = read_bytes(\"/tmp/chelp_fresh.bin\");\n"
     "  println(back[0]);\n"
     "  println(back[1]);\n"
     "}\n",
     "true\n72\n105\n"),
    ("field",
     "struct Bag {\n"
     "  items: [int];\n"
     "}\n"
     "fn main() {\n"
     "  let b = Bag { items: [7, 8] };\n"
     "  let ok = write_bytes(\"/tmp/chelp_field.bin\", b.items);\n"
     "  println(ok);\n"
     "  println(b.items[0]);\n"
     "}\n",
     "true\n7\n"),
    ("move_arg",
     "fn main() {\n"
     "  let d = [72, 105];\n"
     "  let ok = write_bytes(\"/tmp/chelp_move.bin\", move(d));\n"
     "  println(ok);\n"
     "  let back = read_bytes(\"/tmp/chelp_move.bin\");\n"
     "  println(back[0]);\n"
     "}\n",
     "true\n72\n"),
    ("nested_elem",
     "fn main() {\n"
     "  let m = [[9, 8], [7, 6]];\n"
     "  let ok = write_bytes(\"/tmp/chelp_nested.bin\", m[0]);\n"
     "  println(ok);\n"
     "  println(m[0][0]);\n"
     "  println(m[1][0]);\n"
     "}\n",
     "true\n9\n7\n"),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          timeout=30)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    forge = [sys.executable, os.path.join(ROOT, "forge.py")]
    with tempfile.TemporaryDirectory() as td:
        for name, prog, expected in PROGS:
            p = os.path.join(td, name + ".fg")
            with open(p, "w") as f:
                f.write(prog)
            r = run(forge + ["run", p], ROOT)
            if not check(name + " runs", r.returncode == 0,
                         r.stderr.strip().splitlines()[-1] if r.stderr else ""):
                failures.append(name + " runs")
                continue
            if not check(name + " results", r.stdout == expected,
                         repr(r.stdout)):
                failures.append(name + " results")
                continue
            r = run(forge + ["fmt", p], ROOT)
            if not check(name + " fmt", r.returncode == 0,
                         r.stderr.strip().splitlines()[-1] if r.stderr else ""):
                failures.append(name + " fmt")
                continue
            r = run(forge + ["run", p], ROOT)
            if not check(name + " after fmt", r.stdout == expected,
                         repr(r.stdout)):
                failures.append(name + " after fmt")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
