#!/usr/bin/env python3
"""Random-program fuzzer for Qasida.

Generates small programs that are VALID BY CONSTRUCTION
(typed expressions, tracked array lengths, bounded loops,
no recursion, no division by zero, no integer overflow
in the generated ranges), then runs each one through
`forge.py check` and `forge.py run` in safe and fast
mode and classifies the outcome:

  OK           exit 0 in both modes, identical output
  CHECK-ERROR  the checker rejected a program the
               generator believed valid (interesting:
               either a generator bug or a real
               compiler bug — investigate before
               saving it as a reproducer)
  CRASH        forge.py traceback, C compiler failure,
               signal death (e.g. segfault), timeout
  RUNTIME-FAIL any other nonzero exit from `run`
               (e.g. a safe-mode abort the generator
               failed to rule out)
  MISMATCH     safe-mode and fast-mode outputs differ
               (real bug class: checked vs unchecked
               arithmetic, or fast-mode codegen)

Usage:
  python3 tools/fuzz.py [--seeds N] [--start S]
                        [--timeout T] [--save-corpus DIR]
                        [--keep-programs DIR]

Defaults: 50 seeds from 0, 20 s timeout per run.
Failing programs are written to a temp dir (paths
printed in the summary) unless --save-corpus is given,
in which case they are also copied there. The suite
hook runs with a small seed count and no corpus dir,
so it stays hermetic.

Pure Python stdlib only. Deterministic: the same
seed always generates the same program.
"""

import argparse
import os
import random
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = os.path.join(ROOT, "forge.py")

STR_POOL = ["alpha", "beta", "lily", "hi", "a b c", "  pad  ",
            "x", "go", "sun", "rain"]
INT_LITS = list(range(-20, 21))
FLOAT_LITS = ["-2.5", "-1.25", "0.0", "0.5", "1.0", "1.5",
              "2.25", "3.0", "4.5", "7.5", "10.0"]
SEP_POOL = [",", "-", " ", "|"]


class Gen:
    """Valid-by-construction program generator."""

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.seed = seed
        self.counter = 0
        # name -> type, per function; reset per function.
        self.env = {}
        # name -> length, for arrays with known length.
        self.alen = {}
        # name -> mutability.
        self.mut = {}
        # helpers defined so far: (name, [(param, type)], ret)
        self.helpers = []
        # (loop_var, bound) pairs currently in scope, for
        # safe indexing of arrays with len >= bound.
        self.index_vars = []
        # Depth of if-arm nesting: pushes inside an if
        # arm may not execute, so the generator must
        # not count them (tracked length is a LOWER
        # bound on the real length; a conditional push
        # would break that invariant and produce
        # out-of-bounds index assignments later).
        self.cond_depth = 0
        # Arrays currently being iterated by a
        # `for v in arr` loop: pushing to one inside
        # its own iteration could grow it unboundedly.
        self.iterating = []

    def fresh(self, prefix):
        self.counter += 1
        return f"{prefix}{self.counter}"

    def pick(self, xs):
        return self.rng.choice(xs)

    # ---------- typed expression generators ----------

    def int_expr(self, depth, in_loop):
        r = self.rng
        ints = [n for n, t in self.env.items() if t == "int"]
        opts = ["lit"]
        if ints:
            opts += ["var", "var"]
        if depth < 3:
            opts += ["add", "sub", "mul", "div", "mod", "abs"]
        if self.alen:
            opts += ["len"]
        helpers = [h for h in self.helpers if h[2] == "int"]
        if helpers:
            opts += ["call"]
        kind = r.choice(opts)
        if kind == "lit":
            return str(r.choice(INT_LITS))
        if kind == "var":
            return r.choice(ints)
        if kind == "len":
            return f"len({r.choice(list(self.alen))})"
        if kind == "call":
            return self.helper_call(r.choice(helpers))
        if kind == "abs":
            return f"abs({self.int_expr(depth + 1, in_loop)})"
        if kind in ("add", "sub"):
            op = "+" if kind == "add" else "-"
            return (f"({self.int_expr(depth + 1, in_loop)} {op} "
                    f"{self.int_expr(depth + 1, in_loop)})")
        if kind == "mul":
            # At least one side a small literal: keeps every
            # value far from i64 overflow (literals <= 20,
            # depth <= 3, and no multiplication at all
            # inside loop bodies, see int_stmt).
            if r.random() < 0.5:
                return (f"({self.int_expr(depth + 1, in_loop)} * "
                        f"{r.choice([-5, -3, -2, -1, 2, 3, 5])})")
            return (f"({r.choice([-5, -3, -2, -1, 2, 3, 5])} * "
                    f"{self.int_expr(depth + 1, in_loop)})")
        if kind == "div":
            return (f"({self.int_expr(depth + 1, in_loop)} / "
                    f"{r.choice([1, 2, 3, 4, 5, 7, 9])})")
        # mod: divisor is a nonzero literal, so no div-by-zero.
        return (f"({self.int_expr(depth + 1, in_loop)} % "
                f"{r.choice([2, 3, 5, 7])})")

    def float_expr(self, depth, in_loop):
        r = self.rng
        floats = [n for n, t in self.env.items() if t == "float"]
        opts = ["lit"]
        if floats:
            opts += ["var", "var"]
        if depth < 3:
            opts += ["add", "sub", "mul", "div", "sqrt", "exp",
                     "log", "pow"]
        helpers = [h for h in self.helpers if h[2] == "float"]
        if helpers:
            opts += ["call"]
        kind = r.choice(opts)
        if kind == "lit":
            return r.choice(FLOAT_LITS)
        if kind == "var":
            return r.choice(floats)
        if kind == "call":
            return self.helper_call(r.choice(helpers))
        if kind == "add":
            return (f"({self.float_expr(depth + 1, in_loop)} + "
                    f"{self.float_expr(depth + 1, in_loop)})")
        if kind == "sub":
            return (f"({self.float_expr(depth + 1, in_loop)} - "
                    f"{self.float_expr(depth + 1, in_loop)})")
        if kind == "mul":
            return (f"({self.float_expr(depth + 1, in_loop)} * "
                    f"{self.float_expr(depth + 1, in_loop)})")
        if kind == "div":
            # Nonzero literal divisor: no div-by-zero, and
            # no inf/nan from a computed zero denominator.
            return (f"({self.float_expr(depth + 1, in_loop)} / "
                    f"{r.choice(['0.5', '2.0', '4.0'])})")
        if kind == "sqrt":
            # sqrt(x*x) is always defined; sqrt of a
            # literal is restricted to nonneg literals.
            if r.random() < 0.5:
                v = self.float_expr(depth + 1, in_loop)
                return f"sqrt(({v}) * ({v}))"
            return f"sqrt({r.choice(['0.0', '0.5', '1.0', '2.25', '4.0'])})"
        if kind == "exp":
            # exp of a small literal only: exp of a
            # computed value could reach inf, which is
            # still deterministic but noisy to diff.
            return f"exp({r.choice(['-1.0', '0.0', '0.5', '1.0', '2.0'])})"
        if kind == "log":
            # log(1 + x*x) >= log(1): always defined.
            v = self.float_expr(depth + 1, in_loop)
            return f"log((1.0 + ({v}) * ({v})))"
        # pow(x, 2.0): defined for every float x.
        return f"pow({self.float_expr(depth + 1, in_loop)}, 2.0)"

    def bool_expr(self, depth, in_loop):
        r = self.rng
        bools = [n for n, t in self.env.items() if t == "bool"]
        opts = ["lit", "cmp"]
        if bools:
            opts += ["var"]
        if depth < 3:
            opts += ["and", "or", "not"]
        if self.env:
            opts += ["strpred"]
        helpers = [h for h in self.helpers if h[2] == "bool"]
        if helpers:
            opts += ["call"]
        kind = r.choice(opts)
        if kind == "lit":
            return r.choice(["true", "false"])
        if kind == "var":
            return r.choice(bools)
        if kind == "call":
            return self.helper_call(r.choice(helpers))
        if kind == "and":
            return (f"({self.bool_expr(depth + 1, in_loop)} && "
                    f"{self.bool_expr(depth + 1, in_loop)})")
        if kind == "or":
            return (f"({self.bool_expr(depth + 1, in_loop)} || "
                    f"{self.bool_expr(depth + 1, in_loop)})")
        if kind == "not":
            return f"(!{self.bool_expr(depth + 1, in_loop)})"
        if kind == "strpred":
            strs = [n for n, t in self.env.items() if t == "str"]
            if not strs:
                return self.bool_expr(depth, in_loop)
            fn = r.choice(["starts_with", "ends_with"])
            return f"{fn}({r.choice(strs)}, \"{r.choice(STR_POOL)}\")"
        # cmp: compare two exprs of the same numeric type,
        # or two strings for equality.
        which = r.random()
        if which < 0.4 and self.env:
            strs = [n for n, t in self.env.items() if t == "str"]
            if strs:
                op = r.choice(["==", "!="])
                return (f"({self.str_expr(depth + 1, in_loop)} {op} "
                        f"{self.str_expr(depth + 1, in_loop)})")
        if r.random() < 0.5:
            op = r.choice(["==", "!=", "<", ">", "<=", ">="])
            return (f"({self.int_expr(depth + 1, in_loop)} {op} "
                    f"{self.int_expr(depth + 1, in_loop)})")
        op = r.choice(["==", "!=", "<", ">", "<=", ">="])
        return (f"({self.float_expr(depth + 1, in_loop)} {op} "
                f"{self.float_expr(depth + 1, in_loop)})")

    def str_expr(self, depth, in_loop):
        r = self.rng
        strs = [n for n, t in self.env.items() if t == "str"]
        opts = ["lit"]
        if strs:
            opts += ["var", "var"]
        if depth < 3:
            opts += ["concat", "substr", "trim"]
        if self.alen:
            strarrs = [n for n, t in self.env.items()
                       if t == "[str]"]
            if strarrs:
                opts += ["index"]
        helpers = [h for h in self.helpers if h[2] == "str"]
        if helpers:
            opts += ["call"]
        kind = r.choice(opts)
        if kind == "lit":
            return f"\"{r.choice(STR_POOL)}\""
        if kind == "var":
            return r.choice(strs)
        if kind == "call":
            return self.helper_call(r.choice(helpers))
        if kind == "concat":
            return (f"({self.str_expr(depth + 1, in_loop)} + "
                    f"{self.str_expr(depth + 1, in_loop)})")
        if kind == "substr":
            # substr(s, 0, k): start 0 is always in range
            # and over-long lengths are clamped by the
            # runtime, so this is safe for any string.
            return (f"substr({self.str_expr(depth + 1, in_loop)}, "
                    f"0, {r.choice([1, 2, 3])})")
        if kind == "trim":
            return f"trim({self.str_expr(depth + 1, in_loop)})"
        # index: literal index, always < tracked length.
        arr = r.choice(strarrs)
        return f"{arr}[{r.randrange(self.alen[arr])}]"

    def helper_call(self, helper):
        name, params, _ret = helper
        args = []
        for _pname, ptype in params:
            args.append(self.expr_of_type(ptype, 3, False))
        return f"{name}({', '.join(args)})"

    def expr_of_type(self, typ, depth, in_loop):
        if typ == "int":
            return self.int_expr(depth, in_loop)
        if typ == "float":
            return self.float_expr(depth, in_loop)
        if typ == "bool":
            return self.bool_expr(depth, in_loop)
        if typ == "str":
            return self.str_expr(depth, in_loop)
        raise AssertionError(f"no scalar expr generator for {typ}")

    def scalar_of_array(self, atyp):
        return {"[int]": "int", "[float]": "float",
                "[str]": "str"}[atyp]

    # ---------- statements ----------

    def decl(self, indent, typ=None):
        """A let/let mut declaration; registers the name."""
        r = self.rng
        name = self.fresh("v")
        if typ is None:
            typ = r.choice(["int", "float", "bool", "str",
                            "[int]", "[float]", "[str]"])
        mut = r.random() < 0.7
        kw = "let mut" if mut else "let"
        if typ.startswith("["):
            n = r.randint(1, 4)
            et = self.scalar_of_array(typ)
            if et == "str":
                vals = ", ".join(f"\"{r.choice(STR_POOL)}\""
                                 for _ in range(n))
            elif et == "int":
                vals = ", ".join(str(r.choice(INT_LITS))
                                 for _ in range(n))
            else:
                vals = ", ".join(r.choice(FLOAT_LITS)
                                 for _ in range(n))
            init = f"[{vals}]"
            self.alen[name] = n
        else:
            init = self.expr_of_type(typ, 0, False)
        self.env[name] = typ
        self.mut[name] = mut
        return f"{indent}{kw} {name}: {typ} = {init};"

    def assign_stmt(self, indent, in_loop):
        """Assignment to an existing mutable var, or a push."""
        r = self.rng
        muts = [n for n, t in self.env.items() if self.mut.get(n)]
        # Only unconditional, non-iterated arrays may be
        # pushed: a push inside an if arm might not run
        # (breaking length tracking), and a push to the
        # array being iterated could loop forever.
        mutarrs = [n for n, t in self.env.items()
                   if self.mut.get(n) and t.startswith("[")
                   and self.cond_depth == 0
                   and n not in self.iterating]
        if mutarrs and r.random() < 0.25:
            arr = r.choice(mutarrs)
            et = self.scalar_of_array(self.env[arr])
            stmt = (f"{indent}push({arr}, "
                    f"{self.expr_of_type(et, 2, in_loop)});")
            self.alen[arr] += 1
            return stmt
        if not muts:
            return self.println_stmt(indent, in_loop)
        name = r.choice(muts)
        typ = self.env[name]
        if typ.startswith("["):
            # In-bounds index assignment only.
            if self.index_vars:
                iv, bound = r.choice(self.index_vars)
                if self.alen[name] >= bound:
                    idx = iv
                else:
                    idx = str(r.randrange(self.alen[name]))
            else:
                idx = str(r.randrange(self.alen[name]))
            et = self.scalar_of_array(typ)
            return (f"{indent}{name}[{idx}] = "
                    f"{self.expr_of_type(et, 2, in_loop)};")
        # In loop bodies, never multiply and never let the
        # assigned var feed its own growth unchecked:
        # `v = v + small` only, or `v = <expr not using v>`.
        if in_loop and typ == "int":
            others = [n for n, t in self.env.items()
                      if t == "int" and n != name]
            small = r.choice(["1", "2", "3", "-1", "5"])
            if others and r.random() < 0.5:
                return f"{indent}{name} = {name} + {r.choice(others)};"
            return f"{indent}{name} = {name} + {small};"
        if in_loop and typ == "float":
            small = r.choice(["0.5", "1.0", "-0.5", "2.0"])
            return f"{indent}{name} = {name} + {small};"
        if in_loop and typ == "str":
            return (f"{indent}{name} = {name} + "
                    f"\"{r.choice(STR_POOL)}\";")
        if in_loop and typ == "bool":
            return (f"{indent}{name} = "
                    f"{self.bool_expr(2, in_loop)};")
        return (f"{indent}{name} = "
                f"{self.expr_of_type(typ, 2, in_loop)};")

    def println_stmt(self, indent, in_loop):
        parts = []
        for _ in range(self.rng.randint(1, 3)):
            typ = self.rng.choice(["int", "float", "bool", "str"])
            if typ == "str" and self.rng.random() < 0.3:
                parts.append(f"\"{self.rng.choice(STR_POOL)}\"")
            else:
                parts.append(self.expr_of_type(typ, 2, in_loop))
        return f"{indent}println({', '.join(parts)});"

    def loop_body(self, indent, depth):
        """Statements for inside a loop/if: no declarations
        (keeps scoping trivially safe), no unbounded ops."""
        lines = []
        for _ in range(self.rng.randint(1, 3)):
            kind = self.rng.random()
            if kind < 0.55:
                lines.append(self.assign_stmt(indent, True))
            elif kind < 0.8:
                lines.append(self.println_stmt(indent, True))
            elif depth < 2:
                lines.append(self.nested_loop(indent, depth + 1))
            else:
                lines.append(self.assign_stmt(indent, True))
        return lines

    def nested_loop(self, indent, depth):
        r = self.rng
        if r.random() < 0.25 and self.alen:
            # for-each over an existing array. The body
            # only reads the element (plus prints and
            # accumulation into existing mut vars); the
            # array itself is never pushed inside.
            arr = r.choice(list(self.alen))
            et = self.scalar_of_array(self.env[arr])
            ev = self.fresh("e")
            lines = [f"{indent}for {ev} in {arr} {{"]
            accs = [n for n, t in self.env.items()
                    if self.mut.get(n) and t == et]
            for _ in range(r.randint(1, 2)):
                if accs and r.random() < 0.5:
                    acc = r.choice(accs)
                    lines.append(f"{indent}    {acc} = {acc} + {ev};")
                else:
                    lines.append(f"{indent}    println({ev});")
            lines.append(f"{indent}}}")
            return "\n".join(lines)
        if r.random() < 0.5:
            # Bounded for loop over a literal trip count.
            n = r.randint(1, 4)
            iv = self.fresh("i")
            self.index_vars.append((iv, n))
            lines = [f"{indent}for {iv} in range({n}) {{"]
            lines += self.loop_body(indent + "    ", depth)
            lines.append(f"{indent}}}")
            self.index_vars.pop()
            return "\n".join(lines)
        # While loop with an explicit counter.
        n = r.randint(1, 4)
        kv = self.fresh("k")
        pre = (f"{indent}let mut {kv}: int = 0;\n"
               f"{indent}while {kv} < {n} {{")
        # Deliberately NOT in env: loop bodies must not
        # touch the counter (a body assignment like
        # `kv = kv + -1` followed by the +1 increment
        # would loop forever). Bodies only see the
        # surrounding function's variables.
        body = self.loop_body(indent + "    ", depth)
        lines = [pre] + body + [f"{indent}    {kv} = {kv} + 1;",
                 f"{indent}}}"]
        return "\n".join(lines)

    def if_stmt(self, indent):
        cond = self.bool_expr(2, False)
        lines = [f"{indent}if {cond} {{"]
        self.cond_depth += 1
        lines += self.loop_body(indent + "    ", 1)
        if self.rng.random() < 0.5:
            lines.append(f"{indent}}} else {{")
            lines += self.loop_body(indent + "    ", 1)
        self.cond_depth -= 1
        lines.append(f"{indent}}}")
        return "\n".join(lines)

    def body(self, n_stmts):
        """Top-level function body: declarations plus
        assignments, prints, branches and loops."""
        lines = []
        for _ in range(n_stmts):
            kind = self.rng.random()
            if kind < 0.35 or not self.env:
                lines.append(self.decl("    "))
            elif kind < 0.55:
                lines.append(self.assign_stmt("    ", False))
            elif kind < 0.7:
                lines.append(self.println_stmt("    ", False))
            elif kind < 0.85:
                lines.append(self.if_stmt("    "))
            else:
                lines.append(self.nested_loop("    ", 0))
        return lines

    def helper_fn(self):
        r = self.rng
        name = self.fresh("h")
        nparams = r.randint(1, 2)
        params = []
        for _ in range(nparams):
            params.append((self.fresh("p"),
                           r.choice(["int", "float", "bool", "str"])))
        ret = r.choice(["int", "float", "bool", "str"])
        self.env = {p: t for p, t in params}
        self.mut = {p: False for p, _ in params}
        self.alen = {}
        lines = [f"fn {name}({', '.join(f'{p}: {t}' for p, t in params)})"
                 f" -> {ret} {{"]
        lines += self.body(r.randint(1, 3))
        lines.append(f"    return {self.expr_of_type(ret, 2, False)};")
        lines.append("}")
        self.helpers.append((name, params, ret))
        return "\n".join(lines)

    def program(self):
        r = self.rng
        parts = []
        nhelpers = r.randint(0, 2)
        for _ in range(nhelpers):
            parts.append(self.helper_fn())
        self.env = {}
        self.mut = {}
        self.alen = {}
        self.index_vars = []
        parts.append("fn main() -> int {")
        parts += self.body(r.randint(4, 8))
        parts.append("    println(\"fuzz done\");")
        parts.append("    return 0;")
        parts.append("}")
        return "\n".join(parts) + "\n"


# ---------- runner ----------

def run_cmd(argv, timeout):
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, cwd=ROOT)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return "TIMEOUT", "", f"timed out after {timeout}s"


def classify(seed, src, timeout, workdir):
    """Returns (outcome, detail, stdout_safe, stdout_fast)."""
    path = os.path.join(workdir, f"fuzz_{seed}.fg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    rc, _out, err = run_cmd([sys.executable, FORGE, "check", path],
                            timeout)
    if rc != 0:
        if rc == "TIMEOUT" or "Traceback" in err:
            return "CRASH", f"check phase: {err[-2000:]}", "", ""
        return "CHECK-ERROR", err.strip()[-2000:], "", ""
    rc_s, out_s, err_s = run_cmd(
        [sys.executable, FORGE, "run", path, "--mode", "safe"],
        timeout)
    if rc_s == "TIMEOUT":
        return "CRASH", "safe run timed out", "", ""
    if rc_s != 0:
        if "Traceback" in err_s or rc_s < 0 or "cc" in err_s.lower():
            return "CRASH", f"safe run: {err_s[-2000:]}", "", ""
        return "RUNTIME-FAIL", f"safe run: {err_s.strip()[-2000:]}", "", ""
    rc_f, out_f, err_f = run_cmd(
        [sys.executable, FORGE, "run", path, "--mode", "fast"],
        timeout)
    if rc_f == "TIMEOUT":
        return "CRASH", "fast run timed out", out_s, ""
    if rc_f != 0:
        if "Traceback" in err_f or rc_f < 0 or "cc" in err_f.lower():
            return "CRASH", f"fast run: {err_f[-2000:]}", out_s, ""
        return "RUNTIME-FAIL", f"fast run: {err_f.strip()[-2000:]}", out_s, ""
    if out_s != out_f:
        return "MISMATCH", "safe/fast outputs differ", out_s, out_f
    return "OK", "", out_s, out_f


def main(argv=None):
    ap = argparse.ArgumentParser(description="Qasida fuzzer")
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--save-corpus", default=None,
                    help="also copy failing programs here")
    ap.add_argument("--keep-programs", default=None,
                    help="keep every generated program here")
    args = ap.parse_args(argv)

    counts = {}
    failures = []  # (seed, outcome, path, detail)
    with tempfile.TemporaryDirectory(prefix="qasida_fuzz_") as td:
        for seed in range(args.start, args.start + args.seeds):
            src = Gen(seed).program()
            if args.keep_programs:
                os.makedirs(args.keep_programs, exist_ok=True)
                with open(os.path.join(args.keep_programs,
                                       f"fuzz_{seed}.fg"), "w") as f:
                    f.write(src)
            outcome, detail, out_s, out_f = classify(
                seed, src, args.timeout, td)
            counts[outcome] = counts.get(outcome, 0) + 1
            if outcome != "OK":
                path = os.path.join(td, f"fuzz_{seed}.fg")
                if args.save_corpus:
                    os.makedirs(args.save_corpus, exist_ok=True)
                    dest = os.path.join(args.save_corpus,
                                        f"fuzz_{seed}.fg")
                    shutil.copyfile(path, dest)
                    path = dest
                failures.append((seed, outcome, path, detail,
                                 out_s, out_f))
        print(f"seeds: {args.seeds} (start {args.start})")
        for k in ("OK", "CHECK-ERROR", "CRASH", "RUNTIME-FAIL",
                  "MISMATCH"):
            if counts.get(k):
                print(f"  {k}: {counts[k]}")
        if failures:
            print(f"failures: {len(failures)} (showing first 10)")
            for seed, outcome, path, detail, out_s, out_f in \
                    failures[:10]:
                print(f"  seed {seed} {outcome}: {path}")
                print(f"    {detail[:500]}")
                if outcome == "MISMATCH":
                    print(f"    safe: {out_s[:300]!r}")
                    print(f"    fast: {out_f[:300]!r}")
            return 1
        print("no failures")
        return 0


if __name__ == "__main__":
    sys.exit(main())
