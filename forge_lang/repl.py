"""Forge REPL (qasida repl).

Forge is compiled, so the REPL works the way Rust's evcxr-style
tools do: it keeps your `let` definitions, and for each expression
it builds a small program (your definitions + println(<expr>)),
compiles it, runs it, and prints the result. Definitions are
kept in order, so later expressions can use earlier ones.

Commands (typed at the prompt):
  :help   show this list
  :reset  forget all definitions
  :defs   print the accumulated definitions
  :quit   exit (also Ctrl-D / EOF)
Anything else starting with `let ` is a definition; anything else
is an expression to evaluate. A definition that fails to check
is not kept.
"""
import os
import subprocess
import sys
import tempfile

from .errors import ForgeError
from .compiler import compile_file


def build_program(defs, expr=None):
    # Definitions are statements inside main, not top-level items:
    # Forge top level only holds fn/struct/import.
    lines = ["fn main() -> int {"]
    for d in defs:
        lines.append(f"    {d}")
    if expr is not None:
        lines.append(f"    println({expr});")
    lines.append("    return 0;")
    lines.append("}")
    return "\n".join(lines) + "\n"


def run_program(source):
    with tempfile.TemporaryDirectory(prefix="forge_repl_") as td:
        src = os.path.join(td, "repl.fg")
        with open(src, "w", encoding="utf-8") as f:
            f.write(source)
        try:
            compile_file(src)
        except ForgeError as e:
            return 1, "", f"qasida: error: {e}\n"
        # Reuse forge.py run via a direct compile+cc, to avoid
        # importing the CLI's argparse machinery here.
        from .compiler import compile_file as _cf
        from .errors import ForgeError as _FE
        c_source, _ = _cf(src)
        c_path = os.path.join(td, "prog.c")
        exe = os.path.join(td, "prog")
        with open(c_path, "w", encoding="utf-8") as f:
            f.write(c_source)
        cc = subprocess.run(["cc", "-O2", "-std=gnu11", "-pthread", "-o", exe, c_path, "-lm"],
                            capture_output=True, text=True)
        if cc.returncode != 0:
            return 1, "", f"C compiler failed:\n{cc.stderr}"
        proc = subprocess.run([exe], capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr


def repl_loop(input_lines=None, output=None):
    out = output or sys.stdout
    defs = []
    prompt = "forge> "
    if input_lines is not None:
        iterator = iter(input_lines)
        def read_line():
            try:
                return next(iterator)
            except StopIteration:
                return None
    else:
        def read_line():
            try:
                return input(prompt)
            except EOFError:
                return None
    while True:
        if input_lines is None:
            out.write(prompt)
            out.flush()
        line = read_line()
        if line is None:
            break
        line = line.strip()
        if not line:
            continue
        if line in (":quit", ":exit", "quit", "exit"):
            break
        if line == ":help":
            out.write("Commands: :help :reset :defs :quit\n"
                      "Type `let x = ...;` to define, or an expression to evaluate.\n")
            continue
        if line == ":reset":
            defs = []
            out.write("reset\n")
            continue
        if line == ":defs":
            for d in defs:
                out.write(d + "\n")
            continue
        if line.startswith("let "):
            candidate = defs + [line]
            rc, _so, se = run_program(build_program(candidate))
            if rc != 0:
                out.write(se)
            else:
                defs = candidate
            continue
        # Expression: build a program with defs + println(expr).
        rc, so, se = run_program(build_program(defs, line))
        if rc != 0:
            out.write(se)
        else:
            out.write(so)
    return 0


if __name__ == "__main__":
    raise SystemExit(repl_loop())
