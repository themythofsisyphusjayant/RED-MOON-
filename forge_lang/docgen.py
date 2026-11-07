"""Forge doc generator (qasida doc <file.fg>).

Parses a file and emits Markdown: one section per struct, enum,
and function, with the // comment lines immediately above each
definition as its description. It does not need the file to check
(no main required), so it works on stdlib modules too.
"""
from .lexer import tokenize
from .parser import Parser
from . import ast_nodes as A


def _leading_comments(source, line):
    """Collect // comment lines directly above a definition line."""
    lines = source.splitlines()
    out = []
    i = line - 2  # line is 1-based; look at the line above
    while i >= 0:
        s = lines[i].strip()
        if s.startswith("//"):
            out.append(s[2:].strip())
            i -= 1
        elif s == "":
            break
        else:
            break
    return "\n".join(reversed(out))


def generate_docs(source):
    prog = Parser(tokenize(source)).parse_program()
    out = []
    for sd in (prog.structs or []):
        desc = _leading_comments(source, sd.line)
        out.append(f"## struct {sd.name}\n")
        if desc:
            out.append(desc + "\n")
        for fname, ftype in sd.fields:
            out.append(f"- `{fname}: {ftype}`\n")
        out.append("\n")
    for ed in (prog.enums or []):
        desc = _leading_comments(source, ed.line)
        out.append(f"## enum {ed.name}\n")
        if desc:
            out.append(desc + "\n")
        out.append(f"Variants: {', '.join(ed.variants)}\n\n")
    for fn in prog.funcs:
        desc = _leading_comments(source, fn.line)
        params = ", ".join(f"{n}: {t}" for n, t in fn.params)
        ret = f" -> {fn.ret}" if fn.ret != "void" else ""
        prefix = "extern " if getattr(fn, "is_extern", False) else ""
        out.append(f"## {prefix}fn {fn.name}({params}){ret}\n")
        if desc:
            out.append(desc + "\n")
        out.append("\n")
    return "".join(out)


def docs_for_file(path):
    with open(path, encoding="utf-8") as f:
        return generate_docs(f.read())
