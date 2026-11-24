"""Top-500 #127: dict literals as a library (tests/test_dict_v1.py).

String-keyed dictionary as parallel key/value arrays in
forge_lang/stdlib/dict.fg (same copy-on-write shape as
counter.fg): dict_set / dict_remove return a new Dict and leave
the input untouched; dict_get returns Option<int> so a missing
key is absent, not a sentinel. DictStr is the same shape with
str values (dictstr_*). No literal syntax in v1 — that is a
parser feature; construction is via dict_set calls. Linear
lookup, string keys only.

v1 limits (named in the catalog): no literal syntax, string
keys only, int values in Dict (str values in DictStr), linear
lookup. Both compilers (Python + hosted). Runs use cwd=ROOT
(like test_errrender_v1.py): the hosted binary resolves stdlib
imports relative to the repo root (forge_lang/stdlib/), so a
temp cwd would break every import. Nothing is written to the
tree.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEMO_EXPECTED = """3
20
-1
true
false
99
3
2
false
beta
gamma
99
30
2
jayant
?
2
true
bunny
"""

# (name, program, expected stdout, expected stderr needle or "").
OK_CASES = [
    ("set/get/has/len basics",
     r"""import "dict.fg";
fn main() -> int {
  let mut d: Dict = dict_new();
  d = dict_set(d, "a", 1);
  d = dict_set(d, "b", 2);
  println(dict_len(d));
  println(opt_value_or(dict_get(d, "a"), -1));
  println(dict_has(d, "b"));
  println(dict_has(d, "c"));
  return 0;
}
""",
     """2
1
true
false
""",
     ""),
    ("overwrite keeps len, updates value",
     r"""import "dict.fg";
fn main() -> int {
  let mut d: Dict = dict_new();
  d = dict_set(d, "k", 5);
  d = dict_set(d, "k", 6);
  d = dict_set(d, "k", 7);
  println(dict_len(d));
  println(opt_value_or(dict_get(d, "k"), -1));
  return 0;
}
""",
     """1
7
""",
     ""),
    ("missing key is absent, fallback applies",
     r"""import "dict.fg";
fn main() -> int {
  let d: Dict = dict_new();
  let o: Option<int> = dict_get(d, "nope");
  println(o.present);
  println(opt_value_or(o, 42));
  return 0;
}
""",
     """false
42
""",
     ""),
    ("remove present key, remove absent is a no-op",
     r"""import "dict.fg";
fn main() -> int {
  let mut d: Dict = dict_new();
  d = dict_set(d, "a", 1);
  d = dict_set(d, "b", 2);
  d = dict_set(d, "c", 3);
  d = dict_remove(d, "b");
  println(dict_len(d));
  println(dict_has(d, "b"));
  d = dict_remove(d, "zzz");
  println(dict_len(d));
  println(opt_value_or(dict_get(d, "a"), -1));
  println(opt_value_or(dict_get(d, "c"), -1));
  return 0;
}
""",
     """2
false
2
1
3
""",
     ""),
    ("keys/values keep insertion order",
     r"""import "dict.fg";
fn main() -> int {
  let mut d: Dict = dict_new();
  d = dict_set(d, "one", 10);
  d = dict_set(d, "two", 20);
  d = dict_set(d, "three", 30);
  let ks: [str] = dict_keys(d);
  let vs: [int] = dict_values(d);
  println(ks[0]);
  println(ks[1]);
  println(ks[2]);
  println(vs[0]);
  println(vs[1]);
  println(vs[2]);
  return 0;
}
""",
     """one
two
three
10
20
30
""",
     ""),
    ("empty dict: len 0, has false, get absent",
     r"""import "dict.fg";
fn main() -> int {
  let d: Dict = dict_new();
  println(dict_len(d));
  println(dict_has(d, "x"));
  println(opt_value_or(dict_get(d, "x"), -1));
  println(len(dict_keys(d)));
  println(len(dict_values(d)));
  return 0;
}
""",
     """0
false
-1
0
0
""",
     ""),
    ("set returns a new dict; input untouched",
     r"""import "dict.fg";
fn main() -> int {
  let d: Dict = dict_new();
  let d2: Dict = dict_set(d, "a", 1);
  println(dict_len(d));
  println(dict_len(d2));
  let d3: Dict = dict_remove(d2, "a");
  println(dict_len(d2));
  println(dict_len(d3));
  return 0;
}
""",
     """0
1
1
0
""",
     ""),
    ("DictStr: str values, overwrite, missing",
     r"""import "dict.fg";
fn main() -> int {
  let mut d: DictStr = dictstr_new();
  d = dictstr_set(d, "name", "jayant");
  d = dictstr_set(d, "name", "bunny");
  println(dictstr_len(d));
  println(opt_value_or(dictstr_get(d, "name"), "?"));
  println(opt_value_or(dictstr_get(d, "nope"), "?"));
  println(dictstr_has(d, "name"));
  return 0;
}
""",
     """1
bunny
?
true
""",
     ""),
    ("DictStr remove + keys keep order",
     r"""import "dict.fg";
fn main() -> int {
  let mut d: DictStr = dictstr_new();
  d = dictstr_set(d, "a", "x");
  d = dictstr_set(d, "b", "y");
  d = dictstr_set(d, "c", "z");
  d = dictstr_remove(d, "b");
  let ks: [str] = dictstr_keys(d);
  let vs: [str] = dictstr_values(d);
  println(dictstr_len(d));
  println(ks[0]);
  println(ks[1]);
  println(vs[0]);
  println(vs[1]);
  return 0;
}
""",
     """2
a
c
x
z
""",
     ""),
]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
    return ok


def main():
    failures = []
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_STACK,
                           (65536 * 1024, resource.RLIM_INFINITY))
    except Exception:
        pass
    with tempfile.TemporaryDirectory() as td:
        _run_all(td, failures)
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL PASS")
    return 0


def _run_all(td, failures):
    demo = os.path.join(ROOT, "examples", "dict_demo.fg")
    lib = os.path.join(ROOT, "forge_lang", "stdlib", "dict.fg")
    for mode, prefix in (("hosted", []), ("python", ["--python"])):
        r = run([sys.executable, os.path.join(ROOT, "forge.py")] + prefix +
                ["run", demo], ROOT)
        if not check(f"demo runs ({mode})", r.returncode == 0,
                     r.stderr.strip().splitlines()[-1] if r.stderr else ""):
            failures.append(f"demo runs ({mode})")
        elif not check(f"demo results ({mode})", r.stdout == DEMO_EXPECTED,
                       repr(r.stdout)):
            failures.append(f"demo results ({mode})")
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
    # fmt strips // comments, so the lib (which keeps its header) is
    # not fmt-run here — demo only, same as test_errrender_v1.py.
    for target in (demo,):
        rf = run([sys.executable, os.path.join(ROOT, "forge.py"), "fmt", target],
                 ROOT)
        if not check(f"fmt runs ({os.path.basename(target)})",
                     rf.returncode == 0, rf.stderr.strip()):
            failures.append(f"fmt runs ({target})")
        else:
            rf2 = run([sys.executable, os.path.join(ROOT, "forge.py"),
                       "fmt", "--check", target], ROOT)
            if not check(f"fmt idempotent ({os.path.basename(target)})",
                         rf2.returncode == 0, rf2.stderr.strip()):
                failures.append(f"fmt idempotent ({target})")


if __name__ == "__main__":
    sys.exit(main())
