"""Forge formatter (forge fmt).

Parses a .fg file and re-emits it in canonical style: 4-space
indentation, one space around binary operators, `else if` chains
kept as chains, struct literals on one line. The output is
idempotent: formatting formatted code gives the same text.
Only the language constructs in SPEC_V2.md are supported; a file
that does not parse is left untouched and the parse error is
reported by the caller.
"""
from .errors import ForgeError
from .lexer import tokenize
from .parser import Parser
from . import ast_nodes as A

PREC = {"||": 1, "&&": 2, "|": 3, "^": 4, "&": 5,
        "==": 6, "!=": 6,
        "<": 7, "<=": 7, ">": 7, ">=": 7,
        "<<": 8, ">>": 8,
        "+": 9, "-": 9, "*": 10, "/": 10, "%": 10}


def escape_str(value):
    out = []
    for ch in value:
        mapping = {"\n": "\\n", "\t": "\\t", "\r": "\\r",
                   "\\": "\\\\", '"': '\\"', "\0": "\\0"}
        out.append(mapping.get(ch, ch))
    return '"' + "".join(out) + '"'


def expr_prec(expr):
    if isinstance(expr, A.BinOp):
        return PREC[expr.op]
    return 99


def fmt_expr(expr, parent_prec=0):
    if isinstance(expr, A.IntLit):
        return str(expr.value)
    if isinstance(expr, A.FloatLit):
        # Keep a decimal point so the value stays a float literal.
        s = repr(float(expr.value))
        return s if "." in s or "e" in s else s + ".0"
    if isinstance(expr, A.StrLit):
        return escape_str(expr.value)
    if isinstance(expr, A.BoolLit):
        return "true" if expr.value else "false"
    if isinstance(expr, A.Var):
        return expr.name
    if isinstance(expr, A.ArrayLit):
        return "[" + ", ".join(fmt_expr(e) for e in expr.elems) + "]"
    if isinstance(expr, A.TupleLit):
        return "(" + ", ".join(fmt_expr(e) for e in expr.elems) + ")"
    if isinstance(expr, A.StructLit):
        inner = ", ".join(f"{f}: {fmt_expr(e)}" for f, e in expr.fields)
        return f"{expr.name} {{ {inner} }}" if inner else f"{expr.name} {{}}"
    if isinstance(expr, A.FieldAccess):
        return f"{fmt_expr(expr.base, 99)}.{expr.field}"
    if isinstance(expr, A.TupleIndex):
        return f"{fmt_expr(expr.base, 99)}.{expr.index}"
    if isinstance(expr, A.RangeLit):
        return f"{fmt_expr(expr.start, 99)}..{fmt_expr(expr.end, 99)}"
    if isinstance(expr, A.MethodCall):
        return (f"{fmt_expr(expr.base, 99)}.{expr.method}"
                f"({', '.join(fmt_expr(a) for a in expr.args)})")
    if isinstance(expr, A.Index):
        return f"{fmt_expr(expr.base, 99)}[{fmt_expr(expr.index)}]"
    if isinstance(expr, A.Cast):
        return f"{fmt_expr(expr.expr, 99)} as {expr.target}"
    if isinstance(expr, A.UnaryOp):
        return f"{expr.op}{fmt_expr(expr.expr, 99)}"
    if isinstance(expr, A.BinOp):
        p = PREC[expr.op]
        left = fmt_expr(expr.left, p)
        # Right operand needs parens at equal precedence too: for
        # non-associative ops (int division, float rounding, checked
        # overflow) a * (b / c) is not a * b / c.
        right = fmt_expr(expr.right, p + 1)
        text = f"{left} {expr.op} {right}"
        return f"({text})" if p < parent_prec else text
    if isinstance(expr, A.Call):
        return f"{expr.name}({', '.join(fmt_expr(a) for a in expr.args)})"
    if isinstance(expr, A.Try):
        return f"{fmt_expr(expr.expr, 99)}?"
    raise ForgeError(f"formatter: unsupported expression {type(expr).__name__}")


class Formatter:
    def __init__(self):
        self.lines = []

    def emit(self, indent, text=""):
        self.lines.append(("    " * indent + text) if text else "")

    def fmt_program(self, prog):
        for imp in prog.imports:
            self.emit(0, f'import {escape_str(imp)};')
        if prog.imports and (prog.structs or prog.funcs or prog.enums):
            self.emit(0)
        for sd in (prog.structs or []):
            tp = f"<{', '.join(sd.type_params)}>" if getattr(sd, "type_params", None) else ""
            self.emit(0, f"struct {sd.name}{tp} {{")
            for fname, ftype in sd.fields:
                self.emit(1, f"{fname}: {ftype};")
            self.emit(0, "}")
            self.emit(0)
        for ed in (prog.enums or []):
            tp = f"<{', '.join(ed.type_params)}>" if getattr(ed, "type_params", None) else ""
            payloads = getattr(ed, "variant_payloads", None) or {}
            parts = []
            for v in ed.variants:
                pt = payloads.get(v)
                parts.append(f"{v}({pt})" if pt is not None else v)
            self.emit(0, f"enum {ed.name}{tp} {{ {', '.join(parts)} }}")
            self.emit(0)
        for td in (getattr(prog, "traits", None) or []):
            self.emit(0, f"trait {td.name} {{")
            for (mname, params, ret, _ml, _mc) in td.methods:
                ps = ", ".join(f"{n}: {t}" for n, t in params)
                rs = f" -> {ret}" if ret != "void" else ""
                self.emit(1, f"fn {mname}({ps}){rs};")
            self.emit(0, "}")
            self.emit(0)
        for idf in (getattr(prog, "impls", None) or []):
            head = (f"impl {idf.trait} for {idf.struct} {{"
                    if idf.trait is not None else f"impl {idf.struct} {{")
            self.emit(0, head)
            for i, fn in enumerate(idf.methods):
                params = ", ".join(f"{n}: {t}" for n, t in fn.params)
                ret = f" -> {fn.ret}" if fn.ret != "void" else ""
                self.emit(1, f"fn {fn.name}({params}){ret} {{")
                self.fmt_block(fn.body, 2)
                self.emit(1, "}")
                if i < len(idf.methods) - 1:
                    self.emit(1)
            self.emit(0, "}")
            self.emit(0)
        for ad in (getattr(prog, "aliases", None) or []):
            self.emit(0, f"type {ad.name} = {ad.target};")
            self.emit(0)
        for nd in (getattr(prog, "newtypes", None) or []):
            self.emit(0, f"newtype {nd.name} = {nd.target};")
            self.emit(0)
        for i, fn in enumerate(prog.funcs):
            params = ", ".join(f"{n}: {t}" for n, t in fn.params)
            ret = f" -> {fn.ret}" if fn.ret != "void" else ""
            tp = f"<{', '.join(fn.type_params)}>" if getattr(fn, "type_params", None) else ""
            if getattr(fn, "is_extern", False):
                self.emit(0, f"extern fn {fn.name}({params}){ret};")
            else:
                self.emit(0, f"fn {fn.name}{tp}({params}){ret} {{")
                self.fmt_block(fn.body, 1)
                self.emit(0, "}")
            if i < len(prog.funcs) - 1:
                self.emit(0)
        # Trim trailing blank lines, keep one final newline.
        while self.lines and self.lines[-1] == "":
            self.lines.pop()
        return "\n".join(self.lines) + "\n"

    def fmt_block(self, block, indent):
        for stmt in block.stmts:
            self.fmt_stmt(stmt, indent)

    def fmt_stmt(self, stmt, indent):
        if isinstance(stmt, A.Block):
            self.emit(indent, "{")
            self.fmt_block(stmt, indent + 1)
            self.emit(indent, "}")
            return
        if isinstance(stmt, A.Let):
            mut = " mut" if stmt.mutable else ""
            ann = f": {stmt.ann}" if stmt.ann else ""
            self.emit(indent, f"let{mut} {stmt.name}{ann} = {fmt_expr(stmt.expr)};")
            return
        if isinstance(stmt, A.Assign):
            self.emit(indent, f"{stmt.name} = {fmt_expr(stmt.expr)};")
            return
        if isinstance(stmt, A.IndexAssign):
            self.emit(indent, f"{fmt_expr(stmt.base)} = {fmt_expr(stmt.expr)};")
            return
        if isinstance(stmt, A.FieldAssign):
            self.emit(indent, f"{fmt_expr(stmt.target)} = {fmt_expr(stmt.expr)};")
            return
        if isinstance(stmt, A.Match):
            self.emit(indent, f"match {fmt_expr(stmt.expr)} {{")
            for pat, binding, body in stmt.arms:
                pat_text = f"{pat}({binding})" if binding else pat
                self.emit(indent + 1, f"{pat_text} => {{")
                self.fmt_block(body, indent + 2)
                self.emit(indent + 1, "}")
            self.emit(indent, "}")
            return
        if isinstance(stmt, A.Spawn):
            self.emit(indent, f"spawn {fmt_expr(stmt.call)};")
            return
        if isinstance(stmt, A.Defer):
            self.emit(indent, f"defer {fmt_expr(stmt.call)};")
            return
        if isinstance(stmt, A.Scope):
            self.emit(indent, "scope {")
            self.fmt_block(stmt.body, indent + 1)
            self.emit(indent, "}")
            return
        if isinstance(stmt, A.If):
            self.emit(indent, f"if {fmt_expr(stmt.cond)} {{")
            self.fmt_block(stmt.then, indent + 1)
            if stmt.els is None:
                self.emit(indent, "}")
            elif len(stmt.els.stmts) == 1 and isinstance(stmt.els.stmts[0], A.If):
                # else-if chain: emit '} else if ... {' as its own line,
                # then the inner then-block, then the chain tail.
                inner = stmt.els.stmts[0]
                self.emit(indent, f"}} else if {fmt_expr(inner.cond)} {{")
                self.fmt_block(inner.then, indent + 1)
                if inner.els is not None:
                    self.fmt_else(inner.els, indent)
                else:
                    self.emit(indent, "}")
            else:
                self.emit(indent, "} else {")
                self.fmt_block(stmt.els, indent + 1)
                self.emit(indent, "}")
            return
        if isinstance(stmt, A.While):
            self.emit(indent, f"while {fmt_expr(stmt.cond)} {{")
            self.fmt_block(stmt.body, indent + 1)
            self.emit(indent, "}")
            return
        if isinstance(stmt, A.For):
            self.emit(indent, f"for {stmt.name} in {fmt_expr(stmt.expr)} {{")
            self.fmt_block(stmt.body, indent + 1)
            self.emit(indent, "}")
            return
        if isinstance(stmt, A.Break):
            self.emit(indent, "break;")
            return
        if isinstance(stmt, A.Continue):
            self.emit(indent, "continue;")
            return
        if isinstance(stmt, A.Return):
            if stmt.expr is None:
                self.emit(indent, "return;")
            else:
                self.emit(indent, f"return {fmt_expr(stmt.expr)};")
            return
        if isinstance(stmt, A.ExprStmt):
            self.emit(indent, f"{fmt_expr(stmt.expr)};")
            return
        raise ForgeError(f"formatter: unsupported statement {type(stmt).__name__}")

    def fmt_else(self, els, indent):
        # Used for the tail of an else-if chain.
        if len(els.stmts) == 1 and isinstance(els.stmts[0], A.If):
            inner = els.stmts[0]
            self.emit(indent, f"}} else if {fmt_expr(inner.cond)} {{")
            self.fmt_block(inner.then, indent + 1)
            if inner.els is not None:
                self.fmt_else(inner.els, indent)
            else:
                self.emit(indent, "}")
        else:
            self.emit(indent, "} else {")
            self.fmt_block(els, indent + 1)
            self.emit(indent, "}")


def format_source(source):
    prog = Parser(tokenize(source)).parse_program()
    return Formatter().fmt_program(prog)


def format_file(path):
    with open(path, encoding="utf-8") as f:
        return format_source(f.read())
