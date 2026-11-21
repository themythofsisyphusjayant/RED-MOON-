#!/usr/bin/env python3
"""Daily-ten 21 Nov 2026 — library sprint batch 8 (20 items).

Runs each demo under `forge.py run` with BOTH compilers (hosted
default + QASIDA_COMPILER=python) and compares stdout to the
expected transcript exactly. Expected values were hand-derived
BEFORE the first run (independent Python replica;
~/workspace/blackmoon-iso/daily-20261121-batch8/replica_20261121h.py),
including import sorting by ASCII rank, complexity counts,
call-hierarchy edges, doc-comment extraction, TODO/FIXME
marks, case-style rules, FFI bindings, proto structs, SIMD
chunks, grapheme clusters, dtype-checked tensors, the new
div/exp/log backward rules (also checked against central
finite differences in the replica), ONNX params, the FNV-1a
signature, docgen cross-links, stream watermarks and typed
channels. No demo writes files; every demo runs with stdin
as /dev/null so no demo can block.

Usage:
  python3 tests/test_daily_20261121h.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE_PY = os.environ.get(
    "FORGE_PY", os.path.expanduser("~/workspace/forge-v2/forge.py"))
FORGE = [sys.executable, FORGE_PY]
FAILURES = []

EXPECTED = {
    'imporg_demo': '4\nautograd.fg\nnn.fg\ntensor.fg\nzlib.fg\n-1\n1\n0\n',
    'complexity_demo': '6\n5\ntrue\nfalse\n1\ntrue\n',
    'unsafecheck_demo': '3\ntrue\nraw_ptr\nunchecked_add\nraw_ptr\n1\nraw_ptr\n',
    'docsym_demo': '3\n2\nmain\nadd\nmul\nfn main @ 3\nstruct Tensor @ 10\nfn add @ 15\nfn mul @ 20\nstruct Node @ 25\n',
    'callhier_demo': '2\nmain\ntest\n1\nlex\n1\nparse\n1\nparse\n',
    'wsym_demo': '1\ntensor.fg:tensor_add\n2\nmain.fg:main\nutil.fg:main_loop\n0\n',
    'doccomment_demo': '2\nadd\nAdds two numbers. Pure function.\ngreet\nGreets.\n',
    'todotrack_demo': '3\n2\n1\na.fg:1 TODO // TODO fix this\na.fg:3 FIXME // FIXME: handle empty\nb.fg:1 TODO // TODO add tests\n',
    'casestyle_demo': 'true\ntrue\n2\nMyFunc\nbad__name\n2\ntensor\nMy_Type\n',
    'ffibind_demo': 'extern fn add(a: int, b: int) -> int;\nextern fn reset() -> void;\nextern fn mix(x: float, n: int) -> float;\nextern fn greet(name: str) -> str;\n',
    'schemagen_demo': 'struct Point {\n    x: int;\n    y: int;\n}\nfalse\nstruct User {\n    name: str;\n    age: int;\n    active: bool;\n}\ntrue\n',
    'simd_demo': '4\n11\n11\n10\n10\n220\n',
    'grapheme_demo': '5\n1\n2\n1\n1\n1\n1\n2\n1\n3\n2\n1\n1\ntrue\nfalse\n',
    'tensor2_demo': '6\nf32\n7\n7\n3\n2\n3\n2\n4\n6\n',
    'autograd2_demo': '2\n3\n7.38906\n20.0855\n2\n3\n0.25\n-0.25\n0.166667\n0.5\n-0.5\n2\n6\n-4\n-9\n9\n17\n3\n6\n',
    'onnx_demo': '58\n5\n512\nMatMul,Add,Relu,MatMul,Add\n',
    'signrel_demo': 'sig-2842604388\ntrue\nfalse\nfalse\nqasida==2.3.0 #abc123 sig-2842604388\n',
    'docgen2_demo': '# add\n\n`add(a: int, b: int) -> int`\n\nAdds two numbers.\n## Example: add\n```qasida\nadd(2, 3) // 5\n```\n[#mul]\nSee [#add] and [#mul] and [[nope]].\n',
    'bpstream_demo': '3\n1\n3\n1\ntrue\n2\n2\n3\n5\n3\n1\n2\n',
    'typedchan_demo': '1.5\n2\n2.5\n1\ntrue\n2\nfalse\ntrue\n',
}

INPUT = {}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_one(name, expected, env_extra):
    path = os.path.join(ROOT, "examples", name + ".fg")
    env = dict(os.environ)
    env.update(env_extra)
    kwargs = {"capture_output": True, "text": True, "cwd": ROOT,
              "env": env, "timeout": 180}
    if name in INPUT:
        kwargs["input"] = INPUT[name]
    else:
        kwargs["stdin"] = subprocess.DEVNULL
    try:
        r = subprocess.run(FORGE + ["run", path], **kwargs)
    except subprocess.TimeoutExpired:
        check(f"{name} runs", False, "TIMEOUT after 180s")
        return
    check(f"{name} runs rc=0", r.returncode == 0, r.stderr[-300:])
    check(f"{name} exact stdout", r.stdout == expected,
          "" if r.stdout == expected else f"got: {r.stdout!r}")


def main():
    print("daily-ten 21 Nov 2026 — library sprint batch 8 (20 items x 2 compilers)")
    for name, expected in EXPECTED.items():
        print(f"{name} (hosted):")
        run_one(name, expected, {})
        print(f"{name} (python):")
        run_one(name, expected, {"QASIDA_COMPILER": "python"})
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
