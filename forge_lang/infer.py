"""Type inference for codegen (program already checked)."""

from . import ast_nodes as A


class Infer:
    def __init__(self, program):
        self.funcs = {fn.name: fn for fn in program.funcs}
        structs = getattr(program, "structs", None) or []
        self.structs = {sd.name: dict(sd.fields) for sd in structs}
        # Concrete generic structs are appended by the checker with
        # mangled names; also map the generic spelling to those fields.
        from .generics import mangle_type, parse_generic
        self._mangle = mangle_type
        self._parse_generic = parse_generic
        enums = getattr(program, "enums", None) or []
        self.enum_variants = {}
        self.enum_params = {}
        self.enum_payloads = {}
        for ed in enums:
            for v in ed.variants:
                self.enum_variants[v] = ed.name
            self.enum_params[ed.name] = list(getattr(ed, "type_params", None) or [])
            payloads = getattr(ed, "variant_payloads", None) or {}
            self.enum_payloads[ed.name] = {v: payloads.get(v) for v in ed.variants}
        traits = getattr(program, "traits", None) or []
        self.trait_sigs = {}
        for td in traits:
            self.trait_sigs[td.name] = {m: (params, ret)
                                        for (m, params, ret, _l, _c) in td.methods}
        self.types = {}
        self.scopes = []
        self.current_ret = "void"

    def run(self, program):
        for fn in program.funcs:
            if getattr(fn, "is_extern", False):
                continue
            if getattr(fn, "type_params", None):
                continue
            self.current_ret = fn.ret
            self.scopes = [{n: t for n, t in fn.params}]
            self.walk_block(fn.body)
            self.scopes = []
        return self.types

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        if name in self.enum_variants:
            return self.enum_variants[name]
        return "int"

    def set(self, expr, t):
        self.types[id(expr)] = t
        return t

    def walk_block(self, block):
        self.scopes.append({})
        for stmt in block.stmts:
            self.walk_stmt(stmt)
        self.scopes.pop()

    def fill_lit(self, expr, expected):
        """Set a literal's type from context, filling holes in
        nested empty literals (fix track: nested empty array
        literals). A nested `[]` under expected `[[int]]` gets
        `[int]`, not `[?]`, so codegen never sees a hole type.
        Only ArrayLit / TupleLit nodes recurse (only they can
        carry `[?]` holes). Sized expected types recurse too
        (fix track: nested sized-literal unification): an inner
        literal under `[[int; 2]; 2]` gets `[int; 2]`, not the
        dynamic `[int]` a plain walk would assign, and codegen
        normalizes sized types to the shared heap layout."""
        self.set(expr, expected)
        if isinstance(expr, A.ArrayLit) and expr.elems:
            if expected.startswith("[") and expected.endswith("]"):
                from .sizedarrays import is_sized_array, sized_elem
                elem = (sized_elem(expected) if is_sized_array(expected)
                        else expected[1:-1])
                for e in expr.elems:
                    if isinstance(e, (A.ArrayLit, A.TupleLit)):
                        self.fill_lit(e, elem)
                    else:
                        self.walk_expr(e)
                return
            for e in expr.elems:
                self.walk_expr(e)
        elif isinstance(expr, A.TupleLit) and expr.elems:
            from .tuples import is_tuple_type, tuple_elems
            if is_tuple_type(expected):
                elems = tuple_elems(expected)
                if len(elems) == len(expr.elems):
                    for e, et in zip(expr.elems, elems):
                        if isinstance(e, (A.ArrayLit, A.TupleLit)):
                            self.fill_lit(e, et)
                        else:
                            self.walk_expr(e)
                    return
            for e in expr.elems:
                self.walk_expr(e)

    def walk_stmt(self, stmt):
        if isinstance(stmt, A.Block):
            self.walk_block(stmt)
        elif isinstance(stmt, A.Scope):
            self.walk_block(stmt.body)
        elif isinstance(stmt, A.Let):
            if isinstance(stmt.expr, (A.ArrayLit, A.TupleLit)) and stmt.ann:
                self.fill_lit(stmt.expr, stmt.ann)
                t = stmt.ann
            else:
                t = self.walk_expr(stmt.expr)
                if stmt.ann:
                    t = stmt.ann
            self.scopes[-1][stmt.name] = t
        elif isinstance(stmt, A.Assign):
            if isinstance(stmt.expr, (A.ArrayLit, A.TupleLit)):
                vt = self.lookup(stmt.name)
                from .tuples import is_tuple_type
                if vt.startswith("[") or is_tuple_type(vt):
                    self.fill_lit(stmt.expr, vt)
                else:
                    self.walk_expr(stmt.expr)
            else:
                self.walk_expr(stmt.expr)
        elif isinstance(stmt, A.Match):
            et = self.walk_expr(stmt.expr)
            from .generics import parse_generic, substitute_type
            from .unions import is_union_type, union_members
            if is_union_type(et):
                # A union arm binds the narrowed member value: the
                # arm pattern IS the member type.
                members = set(union_members(et))
                for pat, binding, body in stmt.arms:
                    if binding is not None and pat in members:
                        self.scopes.append({binding: pat})
                        try:
                            self.walk_block(body)
                        finally:
                            self.scopes.pop()
                    else:
                        self.walk_block(body)
                return
            g = parse_generic(et)
            base = g[0] if g else et
            bindings = {}
            if g:
                params = self.enum_params.get(base, [])
                if len(params) == len(g[1]):
                    bindings = dict(zip(params, g[1]))
            for pat, binding, body in stmt.arms:
                if binding is not None:
                    pt = self.enum_payloads.get(base, {}).get(pat)
                    concrete_pt = substitute_type(pt, bindings) if pt is not None else "int"
                    self.scopes.append({binding: concrete_pt})
                    try:
                        self.walk_block(body)
                    finally:
                        self.scopes.pop()
                else:
                    self.walk_block(body)
        elif isinstance(stmt, A.Spawn):
            self.walk_expr(stmt.call)
        elif isinstance(stmt, A.Defer):
            self.walk_expr(stmt.call)
        elif isinstance(stmt, A.FieldAssign):
            self.walk_expr(stmt.target)
            self.walk_expr(stmt.expr)
        elif isinstance(stmt, A.IndexAssign):
            self.walk_expr(stmt.base)
            self.walk_expr(stmt.expr)
        elif isinstance(stmt, A.If):
            self.walk_expr(stmt.cond)
            self.walk_block(stmt.then)
            if stmt.els is not None:
                self.walk_block(stmt.els)
        elif isinstance(stmt, A.While):
            self.walk_expr(stmt.cond)
            self.walk_block(stmt.body)
        elif isinstance(stmt, A.For):
            at = self.walk_expr(stmt.expr)
            et = at[1:-1] if at.startswith("[") else "int"
            self.scopes.append({stmt.name: et})
            for s in stmt.body.stmts:
                self.walk_stmt(s)
            self.scopes.pop()
        elif isinstance(stmt, A.Return):
            if stmt.expr is not None:
                if isinstance(stmt.expr, A.ArrayLit) and self.current_ret.startswith("["):
                    self.fill_lit(stmt.expr, self.current_ret)
                elif isinstance(stmt.expr, A.TupleLit):
                    from .tuples import is_tuple_type
                    if is_tuple_type(self.current_ret):
                        self.fill_lit(stmt.expr, self.current_ret)
                    else:
                        self.walk_expr(stmt.expr)
                else:
                    self.walk_expr(stmt.expr)
        elif isinstance(stmt, A.ExprStmt):
            self.walk_expr(stmt.expr)

    def walk_expr(self, expr):
        if isinstance(expr, A.IntLit):
            return self.set(expr, "int")
        if isinstance(expr, A.FloatLit):
            return self.set(expr, "float")
        if isinstance(expr, A.StrLit):
            return self.set(expr, "str")
        if isinstance(expr, A.BoolLit):
            return self.set(expr, "bool")
        if isinstance(expr, A.Var):
            return self.set(expr, self.lookup(expr.name))
        if isinstance(expr, A.ArrayLit):
            if expr.elems:
                t0 = self.walk_expr(expr.elems[0])
                for e in expr.elems[1:]:
                    self.walk_expr(e)
                return self.set(expr, f"[{t0}]")
            return self.set(expr, "[?]")
        if isinstance(expr, A.TupleLit):
            types = [self.walk_expr(e) for e in expr.elems]
            return self.set(expr, f"({', '.join(types)})")
        if isinstance(expr, A.TupleIndex):
            bt = self.walk_expr(expr.base)
            from .tuples import is_tuple_type, tuple_elems
            if is_tuple_type(bt):
                elems = tuple_elems(bt)
                if expr.index < len(elems):
                    return self.set(expr, elems[expr.index])
        if isinstance(expr, A.RangeLit):
            self.walk_expr(expr.start)
            self.walk_expr(expr.end)
            return self.set(expr, "range")
            return self.set(expr, "int")
        if isinstance(expr, A.StructLit):
            concrete = getattr(expr, "concrete_type", None) or expr.name
            mangled = self._mangle(concrete) if self._parse_generic(concrete) else concrete
            fields = self.structs.get(mangled, self.structs.get(expr.name, {}))
            for fname, fexpr in expr.fields:
                if isinstance(fexpr, (A.ArrayLit, A.TupleLit)) and fields.get(fname):
                    self.fill_lit(fexpr, fields[fname])
                else:
                    self.walk_expr(fexpr)
            return self.set(expr, concrete)
        if isinstance(expr, A.FieldAccess):
            bt = self.walk_expr(expr.base)
            mangled = self._mangle(bt) if self._parse_generic(bt) else bt
            ft = self.structs.get(mangled, self.structs.get(bt, {})).get(expr.field, "int")
            return self.set(expr, ft)
        if isinstance(expr, A.Index):
            bt = self.walk_expr(expr.base)
            self.walk_expr(expr.index)
            if bt == "str":
                return self.set(expr, "str")
            from .sizedarrays import array_elem
            et = array_elem(bt) if bt.startswith("[") else "int"
            return self.set(expr, et)
        if isinstance(expr, A.Cast):
            self.walk_expr(expr.expr)
            return self.set(expr, expr.target)
        if isinstance(expr, A.Try):
            t = self.walk_expr(expr.expr)
            g = self._parse_generic(t)
            if g is not None and len(g[1]) >= 1:
                return self.set(expr, g[1][0])
            return self.set(expr, "int")
        if isinstance(expr, A.UnaryOp):
            t = self.walk_expr(expr.expr)
            return self.set(expr, "bool" if expr.op == "!" else t)
        if isinstance(expr, A.BinOp):
            lt = self.walk_expr(expr.left)
            rt = self.walk_expr(expr.right)
            if expr.op in ("<", "<=", ">", ">=", "==", "!=", "&&", "||"):
                return self.set(expr, "bool")
            if expr.op == "+" and lt == "str":
                return self.set(expr, "str")
            # Literal adaptation mirrors the checker: a fitting
            # literal takes the other operand's fixed type.
            if lt != rt and expr.op not in ("<<", ">>"):
                from .fixedints import is_fixed_int, fixed_range, literal_value
                for fixed_t, lit_expr in ((lt, expr.right), (rt, expr.left)):
                    if is_fixed_int(fixed_t):
                        v = literal_value(lit_expr)
                        if v is not None:
                            lo, hi = fixed_range(fixed_t)
                            if lo <= v <= hi and expr.op in ("+", "-", "*", "/", "%", "&", "|", "^"):
                                return self.set(expr, fixed_t)
            return self.set(expr, lt)
        if isinstance(expr, A.MethodCall):
            # Receiver type -> mangled function (the checker already
            # validated the call; this only assigns its type).
            from .traits import mangle
            from .opaques import is_opaque_type, opaque_trait
            rt = self.walk_expr(expr.base)
            if is_opaque_type(rt):
                sigs = self.trait_sigs.get(opaque_trait(rt), {})
                if expr.method in sigs:
                    params, ret = sigs[expr.method]
                    for arg, (_pn, pt) in zip(expr.args, params):
                        from .tuples import is_tuple_type as _is_tup
                        if isinstance(arg, (A.ArrayLit, A.TupleLit)) and (pt.startswith("[") or _is_tup(pt)):
                            self.fill_lit(arg, pt)
                        else:
                            self.walk_expr(arg)
                    return self.set(expr, ret)
                for a in expr.args:
                    self.walk_expr(a)
                return self.set(expr, "int")
            fn = self.funcs.get(mangle(rt, expr.method)) if rt in self.structs else None
            if fn:
                for arg, (_pn, pt) in zip(expr.args, fn.params[1:]):
                    from .tuples import is_tuple_type as _is_tup
                    if isinstance(arg, (A.ArrayLit, A.TupleLit)) and (pt.startswith("[") or _is_tup(pt)):
                        self.fill_lit(arg, pt)
                    else:
                        self.walk_expr(arg)
                return self.set(expr, fn.ret)
            for a in expr.args:
                self.walk_expr(a)
            return self.set(expr, "int")
        if isinstance(expr, A.Call):
            if getattr(expr, "concrete_type", None):
                for a in expr.args:
                    self.walk_expr(a)
                return self.set(expr, expr.concrete_type)
            if expr.name in self.enum_variants:
                for a in expr.args:
                    self.walk_expr(a)
                return self.set(expr, self.enum_variants[expr.name])
            # Array literals in arguments take the parameter type.
            if expr.name not in ("print", "println", "push", "fail", "fail_compile", "eprintln"):
                fn = self.funcs.get(expr.name)
                if fn:
                    for arg, (_pn, pt) in zip(expr.args, fn.params):
                        from .tuples import is_tuple_type as _is_tup
                        if isinstance(arg, (A.ArrayLit, A.TupleLit)) and (pt.startswith("[") or _is_tup(pt)):
                            self.fill_lit(arg, pt)
                        else:
                            self.walk_expr(arg)
                    return self.set(expr, fn.ret)
            for a in expr.args:
                self.walk_expr(a)
            if expr.name in ("len", "clock_micros", "abs", "parse_int", "run_command", "alloc_count", "free_count", "arr_alloc_count", "arr_free_count", "refcount", "weak_new", "mmap_open", "mmap_get", "mmap_grow", "mmap_get32", "peek32", "csr_read", "ecall", "ecall3", "wrapping_add", "wrapping_sub", "wrapping_mul", "wrapping_neg"):
                return self.set(expr, "int")
            if expr.name == "weak_upgrade":
                for a in expr.args:
                    self.walk_expr(a)
                return self.set(expr, "(bool, [int])")
            if expr.name == "move":
                # A move returns its source's type, whether the
                # source is a variable or a struct field (move v2).
                t = self.walk_expr(expr.args[0])
                return self.set(expr, t)
            if expr.name == "parallel_dot":
                for a in expr.args:
                    self.walk_expr(a)
                return self.set(expr, "float")
            if expr.name == "parallel_matmul":
                for a in expr.args:
                    self.walk_expr(a)
                return self.set(expr, "[float]")
            if expr.name == "range":
                return self.set(expr, "[int]")
            if expr.name in ("args", "split"):
                return self.set(expr, "[str]")
            if expr.name in ("sqrt", "exp", "log", "pow", "parse_float"):
                return self.set(expr, "float")
            if expr.name in ("read_file", "read_line", "join", "substr", "trim"):
                return self.set(expr, "str")
            if expr.name == "write_file":
                return self.set(expr, "bool")
            if expr.name == "read_bytes":
                return self.set(expr, "[int]")
            if expr.name == "write_bytes":
                return self.set(expr, "bool")
            if expr.name in ("starts_with", "ends_with", "file_exists"):
                return self.set(expr, "bool")
            if expr.name == "http_get":
                return self.set(expr, "str")
            if expr.name == "http_read_request":
                return self.set(expr, "str")
            if expr.name in ("http_listen", "http_accept", "http_respond", "http_respond_status", "http_close"):
                return self.set(expr, "int")
            return self.set(expr, "void")
        return self.set(expr, "int")


def infer_types(program):
    return Infer(program).run(program)
