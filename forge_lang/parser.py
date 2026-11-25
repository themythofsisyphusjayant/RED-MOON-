"""Recursive-descent parser for Qasida.

Precedence: || -> && -> == != -> < <= > >= -> + - -> * / % -> unary -> postfix -> primary
Postfix: indexing a[i], cast expr as float
"""

from .errors import ForgeError
from .lexer import tokenize
from . import ast_nodes as A

# Top-500 #70 (comptime if): the fixed predicate set. Valued atoms
# compare a compile-time fact against one of the listed values;
# bare atoms are booleans. Anything else is a named error (§4.5).
PRED_VALUES = {
    "target": ("native", "big32", "wasm"),
    "arch": ("x86_64", "riscv32", "wasm32"),
    "os": ("linux", "none", "wasm"),
    "mode": ("safe", "fast"),
}
PRED_NOUNS = {
    "target": "a target",
    "arch": "an architecture",
    "os": "an OS",
    "mode": "a mode",
}
PRED_NAMES = ("target", "arch", "os", "mode", "debug", "freestanding")


class Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.pos = 0

    def peek(self, k=0):
        return self.toks[min(self.pos + k, len(self.toks) - 1)]

    def next(self):
        tok = self.toks[self.pos]
        if tok.kind != "EOF":
            self.pos += 1
        return tok

    def at_op(self, v):
        t = self.peek()
        return t.kind == "OP" and t.value == v

    def at_kw(self, v):
        t = self.peek()
        return t.kind == "KEYWORD" and t.value == v

    def looks_like_struct_lit(self):
        # Current token is "{". A struct literal is "{" IDENT ":" ...
        # or "{" "}". This lookahead is essential: without it,
        # `for v in xs {` would be misread as a struct literal for xs.
        if not self.at_op("{"):
            return False
        nxt = self.peek(1)
        if nxt.kind == "OP" and nxt.value == "}":
            return True
        after = self.peek(2)
        return (nxt.kind == "IDENT" and after.kind == "OP" and after.value == ":")

    def expect_op(self, v):
        t = self.peek()
        if not (t.kind == "OP" and t.value == v):
            raise ForgeError(f"expected '{v}', got {self._d(t)}", t.line, t.col)
        return self.next()

    def expect_kw(self, v):
        t = self.peek()
        if not (t.kind == "KEYWORD" and t.value == v):
            raise ForgeError(f"expected '{v}', got {self._d(t)}", t.line, t.col)
        return self.next()

    def expect_ident(self):
        t = self.peek()
        if t.kind != "IDENT":
            raise ForgeError(f"expected a name, got {self._d(t)}", t.line, t.col)
        return self.next()

    def parse_comptime_pred(self):
        """Parse a comptime-if predicate (Top-500 #70): `||` -> `&&`
        -> `!` -> atom. Atoms are the fixed set only — a call, a
        variable, or any other expression fails here with a named
        error (arbitrary comptime expressions need #462)."""
        return self._parse_comptime_or()

    def _parse_comptime_or(self):
        left = self._parse_comptime_and()
        while self.at_op("||"):
            op = self.next()
            right = self._parse_comptime_and()
            left = A.Pred("or", "", None, [left, right], op.line, op.col)
        return left

    def _parse_comptime_and(self):
        left = self._parse_comptime_not()
        while self.at_op("&&"):
            op = self.next()
            right = self._parse_comptime_not()
            left = A.Pred("and", "", None, [left, right], op.line, op.col)
        return left

    def _parse_comptime_not(self):
        if self.at_op("!"):
            op = self.next()
            operand = self._parse_comptime_not()
            return A.Pred("not", "", None, [operand], op.line, op.col)
        return self._parse_comptime_atom()

    def _parse_comptime_atom(self):
        t = self.peek()
        if self.at_op("("):
            self.next()
            pred = self.parse_comptime_pred()
            self.expect_op(")")
            return pred
        if t.kind != "IDENT":
            raise ForgeError(
                "comptime if needs a target predicate; arbitrary "
                "expressions need comptime evaluation (#462)",
                t.line, t.col)
        self.next()
        name = t.value
        if name in ("debug", "freestanding"):
            if self.at_op("==") or self.at_op("!="):
                raise ForgeError(
                    f"comptime predicate '{name}' takes no value; "
                    f"write '{name}' or '!{name}'",
                    t.line, t.col)
            return A.Pred(name, "", None, None, t.line, t.col)
        if name not in PRED_VALUES:
            raise ForgeError(
                f"comptime condition uses unknown predicate '{name}'; "
                f"allowed: {', '.join(PRED_NAMES)}",
                t.line, t.col)
        if not (self.at_op("==") or self.at_op("!=")):
            first = PRED_VALUES[name][0]
            raise ForgeError(
                f"comptime predicate '{name}' needs a comparison, "
                f"e.g. {name} == \"{first}\"",
                t.line, t.col)
        op = self.next()
        v = self.peek()
        if v.kind != "STR":
            first = PRED_VALUES[name][0]
            raise ForgeError(
                f"comptime predicate '{name}' needs a string value, "
                f"e.g. {name} == \"{first}\"",
                v.line, v.col)
        self.next()
        allowed = PRED_VALUES[name]
        if v.value not in allowed:
            raise ForgeError(
                f"comptime {name} \"{v.value}\" is not "
                f"{PRED_NOUNS[name]}; allowed: {', '.join(allowed)}",
                v.line, v.col)
        return A.Pred(name, op.value, v.value, None, t.line, t.col)

    def parse_pattern(self):
        """Parse one match-arm pattern (Top-500 #69: value patterns).

        v1 shapes: `_` (wildcard), an identifier (enum variant or
        union member name), an int literal (optionally `-` + INT),
        a bool literal, a string literal, or a struct pattern
        `Name { field: <pattern>, ... }` where each field pattern
        is a literal, a binding, or `_`. Float, range, tuple/array
        and type patterns, `|` alternation and guards are not in
        v1 and fail here with a named error.
        """
        t = self.peek()
        if t.kind == "INT":
            self.next()
            return A.Pattern("lit_int", t.value, None, None, t.line, t.col)
        if t.kind == "STR":
            self.next()
            return A.Pattern("lit_str", t.value, None, None, t.line, t.col)
        if t.kind == "FLOAT":
            raise ForgeError("float literal patterns are not supported in v1",
                             t.line, t.col)
        if t.kind == "OP" and t.value == "-":
            self.next()
            n = self.peek()
            if n.kind != "INT":
                raise ForgeError(f"expected an integer literal after '-', got {self._d(n)}",
                                 n.line, n.col)
            self.next()
            return A.Pattern("lit_int", -n.value, None, None, t.line, t.col)
        if t.kind == "KEYWORD" and t.value in ("true", "false"):
            self.next()
            return A.Pattern("lit_bool", t.value == "true", None, None, t.line, t.col)
        if t.kind != "IDENT":
            raise ForgeError(f"expected a pattern, got {self._d(t)}", t.line, t.col)
        self.next()
        if t.value == "_":
            return A.Pattern("wildcard", "", None, None, t.line, t.col)
        if self.at_op("{"):
            return self.parse_struct_pattern(t)
        return A.Pattern("variant", t.value, None, None, t.line, t.col)

    def parse_struct_pattern(self, name_tok):
        """Parse the `{ field: <pattern>, ... }` tail of a struct
        pattern after its name (Top-500 #69). Field patterns are
        literals, bindings, or `_`; nested struct patterns are not
        in v1."""
        self.next()  # consume "{"
        fields = []
        seen = set()
        if self.at_op("}"):
            self.next()
            return A.Pattern("struct", name_tok.value, fields, None,
                             name_tok.line, name_tok.col)
        while True:
            ft = self.peek()
            if ft.kind != "IDENT" or ft.value == "_":
                raise ForgeError(f"expected a field name in a struct pattern, got {self._d(ft)}",
                                 ft.line, ft.col)
            self.next()
            if ft.value in seen:
                raise ForgeError(f"duplicate field '{ft.value}' in a struct pattern",
                                 ft.line, ft.col)
            seen.add(ft.value)
            self.expect_op(":")
            fp = self.parse_field_pattern()
            fields.append((ft.value, fp))
            if self.at_op(","):
                self.next()
                continue
            self.expect_op("}")
            break
        return A.Pattern("struct", name_tok.value, fields, None,
                         name_tok.line, name_tok.col)

    def parse_field_pattern(self):
        """Parse one field pattern inside a struct pattern (Top-500
        #69): an int/bool/string literal, a binding identifier, or
        `_`. Nested struct patterns are not in v1."""
        t = self.peek()
        if t.kind == "INT":
            self.next()
            return A.Pattern("lit_int", t.value, None, None, t.line, t.col)
        if t.kind == "STR":
            self.next()
            return A.Pattern("lit_str", t.value, None, None, t.line, t.col)
        if t.kind == "FLOAT":
            raise ForgeError("float literal patterns are not supported in v1",
                             t.line, t.col)
        if t.kind == "OP" and t.value == "-":
            self.next()
            n = self.peek()
            if n.kind != "INT":
                raise ForgeError(f"expected an integer literal after '-', got {self._d(n)}",
                                 n.line, n.col)
            self.next()
            return A.Pattern("lit_int", -n.value, None, None, t.line, t.col)
        if t.kind == "KEYWORD" and t.value in ("true", "false"):
            self.next()
            return A.Pattern("lit_bool", t.value == "true", None, None, t.line, t.col)
        if t.kind == "IDENT":
            self.next()
            if t.value == "_":
                return A.Pattern("wildcard", "", None, None, t.line, t.col)
            if self.at_op("{"):
                raise ForgeError("nested struct patterns are not supported in v1",
                                 t.line, t.col)
            return A.Pattern("binding", t.value, None, None, t.line, t.col)
        raise ForgeError(f"expected a pattern, got {self._d(t)}", t.line, t.col)

    @staticmethod
    def _d(tok):
        return "end of file" if tok.kind == "EOF" else repr(tok.value)

    def parse_program(self):
        imports = []
        funcs = []
        structs = []
        enums = []
        traits = []
        impls = []
        aliases = []
        newtypes = []
        while self.peek().kind != "EOF":
            if self.at_kw("import"):
                self.next()
                tok = self.peek()
                if tok.kind != "STR":
                    raise ForgeError("import needs a string path", tok.line, tok.col)
                self.next()
                imports.append(tok.value)
                self.expect_op(";")
            elif self.at_kw("struct"):
                structs.append(self.parse_struct())
            elif self.at_kw("enum"):
                enums.append(self.parse_enum())
            elif self.at_kw("trait"):
                traits.append(self.parse_trait())
            elif self.at_kw("impl"):
                impls.append(self.parse_impl())
            elif self.at_kw("type"):
                aliases.append(self.parse_alias())
            elif self.at_kw("newtype"):
                newtypes.append(self.parse_newtype())
            elif self.at_kw("extern"):
                funcs.append(self.parse_extern())
            elif (self.peek().kind == "IDENT" and self.peek().value == "comptime"
                    and self.peek(1).kind == "KEYWORD" and self.peek(1).value == "if"):
                # Top-500 #70: comptime if is function-body only in
                # v1; top-level (incl. gated imports) is v2.
                t = self.peek()
                raise ForgeError(
                    "comptime if is only allowed inside functions in v1",
                    t.line, t.col)
            else:
                funcs.append(self.parse_func())
        return A.Program(imports, funcs, structs, enums, traits, impls,
                         aliases, newtypes)

    def parse_enum(self):
        kw = self.expect_kw("enum")
        name = self.expect_ident()
        type_params = self.parse_type_params()
        self.expect_op("{")
        variants = []
        payloads = {}
        while not self.at_op("}"):
            if self.peek().kind == "EOF":
                raise ForgeError("unterminated enum", self.peek().line, self.peek().col)
            v = self.expect_ident()
            variants.append(v.value)
            if self.at_op("("):
                self.next()
                payload = self.parse_type()
                if self.at_op(","):
                    raise ForgeError("enum variants take at most one payload type in v1",
                                     self.peek().line, self.peek().col)
                self.expect_op(")")
                payloads[v.value] = payload
            else:
                payloads[v.value] = None
            if self.at_op(",") or self.at_op(";"):
                self.next()
                continue
            if self.at_op("}"):
                break
            raise ForgeError("expected ',' or ';' between enum variants",
                             self.peek().line, self.peek().col)
        self.expect_op("}")
        ed = A.EnumDef(name.value, variants, kw.line, kw.col)
        ed.type_params = type_params
        ed.variant_payloads = payloads
        return ed

    def parse_extern(self):
        kw = self.expect_kw("extern")
        self.expect_kw("fn")
        name = self.expect_ident()
        self.expect_op("(")
        params = []
        if not self.at_op(")"):
            while True:
                pname = self.expect_ident()
                self.expect_op(":")
                ptype = self.parse_type()
                params.append((pname.value, ptype))
                if self.at_op(","):
                    self.next()
                    if self.at_op(")"):
                        break
                    continue
                break
        self.expect_op(")")
        ret = "void"
        if self.at_op("->"):
            self.next()
            ret = self.parse_type()
        self.expect_op(";")
        return A.FuncDef(name.value, params, ret, A.Block([]),
                         kw.line, kw.col, is_extern=True)

    def parse_type_params(self):
        """Parse <T, U> after a fn/struct name; return [] if absent."""
        if not self.at_op("<"):
            return []
        self.next()
        params = []
        while True:
            params.append(self.expect_ident().value)
            if self.at_op(","):
                self.next()
                if self.at_op(">"):
                    break
                continue
            break
        self.expect_op(">")
        return params

    def parse_struct(self):
        kw = self.expect_kw("struct")
        name = self.expect_ident()
        type_params = self.parse_type_params()
        self.expect_op("{")
        fields = []
        while not self.at_op("}"):
            if self.peek().kind == "EOF":
                raise ForgeError("unterminated struct", self.peek().line, self.peek().col)
            fname = self.expect_ident()
            self.expect_op(":")
            ftype = self.parse_type()
            fields.append((fname.value, ftype))
            if self.at_op(",") or self.at_op(";"):
                self.next()
                continue
            if self.at_op("}"):
                break
            raise ForgeError("expected ',' or ';' between struct fields",
                             self.peek().line, self.peek().col)
        self.expect_op("}")
        return A.StructDef(name.value, fields, kw.line, kw.col, type_params)

    def parse_type(self, allow_union=True):
        # Union members are joined with " | ". A cast target parses
        # with allow_union=False: `x as int | y` is a cast to int
        # followed by a bitwise-or, not a cast to `int | y`. Nested
        # unions (inside [] or <>) are unambiguous and always
        # allowed, because the closing bracket ends them.
        if self.at_op("["):
            self.next()
            inner = self.parse_type()
            if self.at_op(";"):
                # Sized array: [T; N] with a literal size.
                self.next()
                tok = self.peek()
                if tok.kind != "INT":
                    raise ForgeError("sized array size must be an integer literal",
                                     tok.line, tok.col)
                self.next()
                self.expect_op("]")
                base = f"[{inner}; {tok.value}]"
            else:
                self.expect_op("]")
                base = f"[{inner}]"
        elif self.at_op("("):
            # Tuple type: (T1, T2, ...) with at least two
            # elements. A single parenthesised type is not a
            # 1-tuple in v1 (and () is not the unit type).
            self.next()
            elems = []
            if not self.at_op(")"):
                while True:
                    elems.append(self.parse_type())
                    if self.at_op(","):
                        self.next()
                        if self.at_op(")"):
                            break
                        continue
                    break
            tok = self.peek()
            self.expect_op(")")
            if len(elems) < 2:
                raise ForgeError("tuple types need at least two elements",
                                 tok.line, tok.col)
            base = f"({', '.join(elems)})"
        elif self.at_kw("opaque"):
            # `opaque Trait`: the trait name is part of the type.
            self.next()
            base = f"opaque {self.expect_ident().value}"
        elif self.at_kw("fn"):
            # Fn type (Top-500 #103): fn(P1, P2, ...) -> R, with
            # the `-> R` optional (defaults to void, as in fn
            # declarations). The return type parses with the same
            # allow_union threading as the caller, so
            # `fn(int) -> int | str` is one string — the checker
            # rejects unions inside fn types (FN-C6).
            self.next()
            self.expect_op("(")
            params = []
            if not self.at_op(")"):
                while True:
                    params.append(self.parse_type())
                    if self.at_op(","):
                        self.next()
                        if self.at_op(")"):
                            break
                        continue
                    break
            self.expect_op(")")
            ret = "void"
            if self.at_op("->"):
                self.next()
                ret = self.parse_type()
            base = f"fn({', '.join(params)}) -> {ret}"
        elif self.at_kw("readonly"):
            # `readonly [T]`: a read-only view of an array. The
            # inner type must be a plain array (nesting and
            # non-arrays are rejected here, with a clear message,
            # rather than surfacing as an unknown type later).
            self.next()
            if self.at_kw("readonly"):
                tok = self.peek()
                raise ForgeError("readonly cannot be nested",
                                 tok.line, tok.col)
            inner = self.parse_type()
            if not (inner.startswith("[") and inner.endswith("]")):
                tok = self.peek()
                raise ForgeError("readonly only applies to array types",
                                 tok.line, tok.col)
            base = f"readonly {inner}"
        else:
            name = self.expect_ident().value
            if name == "i64":
                # i64 is int, not a separate type: normalising here
                # (the single funnel for type spellings) keeps the
                # two names from forming a parallel universe.
                name = "int"
            if self.at_op("<"):
                self.next()
                args = []
                while True:
                    args.append(self.parse_type())
                    if self.at_op(","):
                        self.next()
                        if self.at_op(">"):
                            break
                        continue
                    break
                self.expect_op(">")
                base = f"{name}<{', '.join(args)}>"
            else:
                base = name
        parts = [base]
        while allow_union and self.at_op("|"):
            self.next()
            parts.append(self.parse_type(allow_union=False))
        return " | ".join(parts)

    def parse_trait(self):
        # trait Shape { fn area() -> int; fn name() -> str; }
        # Signatures only, no bodies: the contract an impl must meet.
        # Generic traits are a later slice (v1 rejects them plainly).
        kw = self.expect_kw("trait")
        name = self.expect_ident()
        type_params = self.parse_type_params()
        if type_params:
            raise ForgeError("generic traits are not supported in v1",
                             kw.line, kw.col)
        self.expect_op("{")
        methods = []
        while not self.at_op("}"):
            if self.peek().kind == "EOF":
                raise ForgeError("unterminated trait", self.peek().line, self.peek().col)
            self.expect_kw("fn")
            mname = self.expect_ident()
            self.expect_op("(")
            params = []
            if not self.at_op(")"):
                while True:
                    pname = self.expect_ident()
                    self.expect_op(":")
                    ptype = self.parse_type()
                    params.append((pname.value, ptype))
                    if self.at_op(","):
                        self.next()
                        if self.at_op(")"):
                            break
                        continue
                    break
            self.expect_op(")")
            ret = "void"
            if self.at_op("->"):
                self.next()
                ret = self.parse_type()
            self.expect_op(";")
            methods.append((mname.value, params, ret, mname.line, mname.col))
        self.expect_op("}")
        return A.TraitDef(name.value, methods, kw.line, kw.col)

    def parse_impl(self):
        # impl Shape for Rect { fn area(r: Rect) -> int { ... } }
        # or an inherent impl with no trait: impl Rect { ... }.
        # Each method takes the receiver as its first parameter.
        kw = self.expect_kw("impl")
        first = self.expect_ident()
        trait = None
        struct = first.value
        if self.at_kw("for"):
            self.next()
            trait = first.value
            struct = self.expect_ident().value
        self.expect_op("{")
        methods = []
        while not self.at_op("}"):
            if self.peek().kind == "EOF":
                raise ForgeError("unterminated impl", self.peek().line, self.peek().col)
            m = self.parse_func()
            if m.type_params:
                raise ForgeError("generic methods are not supported in "
                                 "traits v1", m.line, m.col)
            methods.append(m)
        self.expect_op("}")
        return A.ImplDef(trait, struct, methods, kw.line, kw.col)

    def parse_alias(self):
        # type UserId = int;  type Scores = [int];  type IntBox = Box<int>;
        # Transparent: the name is a shorthand for the target type,
        # expanded by the checker before any other checking runs.
        kw = self.expect_kw("type")
        name = self.expect_ident()
        self.expect_op("=")
        target = self.parse_type()
        self.expect_op(";")
        return A.AliasDef(name.value, target, kw.line, kw.col)

    def parse_newtype(self):
        # newtype UserId = int;
        # DISTINCT from an alias: UserId is its own type, never
        # equal to int, and values cross only via explicit casts.
        kw = self.expect_kw("newtype")
        name = self.expect_ident()
        self.expect_op("=")
        target = self.parse_type()
        self.expect_op(";")
        return A.NewtypeDef(name.value, target, kw.line, kw.col)

    def parse_param_list(self):
        """`(name: type, ...)` — shared by fn declarations and
        lambda expressions (Top-500 #101). Params must be
        annotated; there is no inference from context in v1."""
        self.expect_op("(")
        params = []
        if not self.at_op(")"):
            while True:
                pname = self.expect_ident()
                self.expect_op(":")
                ptype = self.parse_type()
                params.append((pname.value, ptype))
                if self.at_op(","):
                    self.next()
                    if self.at_op(")"):
                        break
                    continue
                break
        self.expect_op(")")
        return params

    def parse_func(self):
        kw = self.expect_kw("fn")
        name = self.expect_ident()
        type_params = self.parse_type_params()
        params = self.parse_param_list()
        ret = "void"
        if self.at_op("->"):
            self.next()
            ret = self.parse_type()
        body = self.parse_block()
        return A.FuncDef(name.value, params, ret, body, kw.line, kw.col,
                         type_params=type_params)

    def parse_block(self):
        self.expect_op("{")
        stmts = []
        while not self.at_op("}"):
            if self.peek().kind == "EOF":
                raise ForgeError("unterminated block", self.peek().line, self.peek().col)
            stmts.append(self.parse_stmt())
        self.expect_op("}")
        return A.Block(stmts)

    def parse_stmt(self):
        # Top-500 #62: a label prefix on a loop (`outer: for ...`,
        # `outer: while ...`). `ident:` at statement position is
        # otherwise a parse error, so the prefix is free: claim it
        # only when a loop keyword follows, else name the misuse.
        label = None
        if (self.peek().kind == "IDENT" and self.peek(1).kind == "OP"
                and self.peek(1).value == ":"):
            name_tok = self.next()
            self.next()  # ':'
            if not (self.at_kw("while") or self.at_kw("for")):
                raise ForgeError(
                    f"label '{name_tok.value}' must prefix a 'while' or "
                    f"'for' loop (labels attach to loops only in v1)",
                    name_tok.line, name_tok.col)
            label = name_tok.value
        # Top-500 #70: `comptime if <pred> { } else { }`. `comptime`
        # stays an ordinary identifier everywhere else: only
        # `comptime` immediately followed by `if` at statement
        # position takes this branch, so `let comptime = 3;`,
        # `comptime = 5;`, and `comptime();` all still parse as
        # before (p12). `else comptime if` chains like `else if`.
        if (self.peek().kind == "IDENT" and self.peek().value == "comptime"
                and self.peek(1).kind == "KEYWORD" and self.peek(1).value == "if"):
            kw = self.next()
            self.next()  # 'if'
            pred = self.parse_comptime_pred()
            then = self.parse_block()
            els = None
            if self.at_kw("else"):
                self.next()
                if (self.peek().kind == "IDENT" and self.peek().value == "comptime"
                        and self.peek(1).kind == "KEYWORD" and self.peek(1).value == "if"):
                    els = A.Block([self.parse_stmt()])
                else:
                    els = self.parse_block()
            return A.ComptimeIf(pred, then, els, kw.line, kw.col)
        if self.at_kw("let"):
            kw = self.next()
            mutable = False
            if self.at_kw("mut"):
                self.next()
                mutable = True
            name = self.expect_ident()
            ann = None
            if self.at_op(":"):
                self.next()
                ann = self.parse_type()
            self.expect_op("=")
            expr = self.parse_expr()
            self.expect_op(";")
            return A.Let(name.value, mutable, ann, expr, kw.line, kw.col)
        if self.at_kw("if"):
            kw = self.next()
            cond = self.parse_expr()
            then = self.parse_block()
            els = None
            if self.at_kw("else"):
                self.next()
                if self.at_kw("if"):
                    els = A.Block([self.parse_stmt()])
                else:
                    els = self.parse_block()
            return A.If(cond, then, els, kw.line, kw.col)
        if self.at_kw("while"):
            kw = self.next()
            cond = self.parse_expr()
            body = self.parse_block()
            return A.While(cond, body, kw.line, kw.col, label)
        if self.at_kw("for"):
            kw = self.next()
            name = self.expect_ident()
            self.expect_kw("in")
            expr = self.parse_expr()
            body = self.parse_block()
            return A.For(name.value, expr, body, kw.line, kw.col, label)
        if self.at_kw("return"):
            tok = self.next()
            expr = None
            if not self.at_op(";"):
                expr = self.parse_expr()
            self.expect_op(";")
            return A.Return(expr, tok.line, tok.col)
        if self.at_kw("break"):
            tok = self.next()
            blabel = None
            if self.peek().kind == "IDENT":
                blabel = self.next().value
            self.expect_op(";")
            return A.Break(tok.line, tok.col, blabel)
        if self.at_kw("continue"):
            tok = self.next()
            clabel = None
            if self.peek().kind == "IDENT":
                clabel = self.next().value
            self.expect_op(";")
            return A.Continue(tok.line, tok.col, clabel)
        if self.at_kw("defer"):
            kw = self.next()
            expr = self.parse_expr()
            self.expect_op(";")
            if not isinstance(expr, (A.Call, A.MethodCall)):
                raise ForgeError("defer needs a call", kw.line, kw.col)
            return A.Defer(expr, kw.line, kw.col)
        if self.at_kw("match"):
            kw = self.next()
            expr = self.parse_expr()
            self.expect_op("{")
            arms = []
            while not self.at_op("}"):
                if self.peek().kind == "EOF":
                    raise ForgeError("unterminated match", self.peek().line, self.peek().col)
                pat = self.parse_pattern()
                if pat.kind == "wildcard" and self.at_op("("):
                    raise ForgeError("wildcard arm cannot bind a value",
                                     pat.line, pat.col)
                if pat.kind == "struct" and self.at_op("("):
                    raise ForgeError("only variant patterns can bind a value",
                                     pat.line, pat.col)
                if pat.kind == "variant" and self.at_op("("):
                    self.next()
                    b = self.expect_ident()
                    if b.value == "_":
                        raise ForgeError("wildcard arm cannot bind a value",
                                         b.line, b.col)
                    self.expect_op(")")
                    pat.binding = b.value
                self.expect_op("=>")
                body = self.parse_block()
                arms.append((pat, body))
                if self.at_op(","):
                    self.next()
            self.expect_op("}")
            return A.Match(expr, arms, kw.line, kw.col)
        if self.at_kw("spawn"):
            kw = self.next()
            expr = self.parse_expr()
            self.expect_op(";")
            if not isinstance(expr, A.Call):
                raise ForgeError("spawn needs a function call", kw.line, kw.col)
            return A.Spawn(expr, kw.line, kw.col)
        # Structured concurrency: `scope { ... }` joins every task
        # spawned inside (directly or transitively) at the closing
        # brace. `scope` stays an ordinary identifier everywhere
        # else: only `scope` immediately followed by `{` at statement
        # position takes this branch, so `scope = 5;`, `scope();`,
        # and `let scope = ...;` all still parse as before.
        if (self.peek().kind == "IDENT" and self.peek().value == "scope"
                and self.peek(1).kind == "OP" and self.peek(1).value == "{"):
            kw = self.next()
            body = self.parse_block()
            return A.Scope(body, kw.line, kw.col)
        if self.at_op("{"):
            return self.parse_block()
        # General case: parse an expression, then either '=' (assignment)
        # or ';' (expression statement).
        tok = self.peek()
        expr = self.parse_expr()
        if self.at_op("="):
            self.next()
            rhs = self.parse_expr()
            self.expect_op(";")
            if isinstance(expr, A.Var):
                return A.Assign(expr.name, rhs, expr.line, expr.col)
            if isinstance(expr, A.Index):
                return A.IndexAssign(expr, rhs, expr.line, expr.col)
            if isinstance(expr, A.FieldAccess):
                return A.FieldAssign(expr, rhs, expr.line, expr.col)
            raise ForgeError("assignment target must be a variable, an index, or a field",
                             expr.line, expr.col)
        self.expect_op(";")
        return A.ExprStmt(expr, tok.line, tok.col)

    def parse_expr(self):
        # Ranges bind loosest: `1 + 2..3 + 4` is (1 + 2)..(3 + 4).
        # The right side is a plain binary expression, so chained
        # ranges (`a..b..c`) fail on the second `..`.
        left = self.parse_or()
        if self.at_op(".."):
            op = self.next()
            right = self.parse_or()
            return A.RangeLit(left, right, op.line, op.col)
        return left

    def _level(self, sub, ops):
        left = sub()
        while self.peek().kind == "OP" and self.peek().value in ops:
            op = self.next()
            right = sub()
            left = A.BinOp(op.value, left, right, op.line, op.col)
        return left

    def parse_or(self):
        return self._level(self.parse_and, {"||"})

    def parse_and(self):
        return self._level(self.parse_bitor, {"&&"})

    def parse_bitor(self):
        return self._level(self.parse_bitxor, {"|"})

    def parse_bitxor(self):
        return self._level(self.parse_bitand, {"^"})

    def parse_bitand(self):
        return self._level(self.parse_equality, {"&"})

    def parse_equality(self):
        return self._level(self.parse_comparison, {"==", "!="})

    def parse_comparison(self):
        return self._level(self.parse_shift, {"<", "<=", ">", ">="})

    def parse_shift(self):
        return self._level(self.parse_additive, {"<<", ">>"})

    def parse_additive(self):
        return self._level(self.parse_multiplicative, {"+", "-"})

    def parse_multiplicative(self):
        return self._level(self.parse_unary, {"*", "/", "%"})

    def parse_unary(self):
        tok = self.peek()
        if tok.kind == "OP" and tok.value in ("-", "!", "~"):
            self.next()
            return A.UnaryOp(tok.value, self.parse_unary(), tok.line, tok.col)
        return self.parse_postfix()

    def parse_postfix(self):
        expr = self.parse_primary()
        while True:
            if self.at_op("(") and isinstance(expr, A.FieldAccess):
                # value.method(args): a method call, not a field read.
                # Field access followed by '(' is unambiguous here:
                # a field can never itself be called (a fn-typed
                # field is read into a local first — Top-500 #103,
                # FN-C1c), so this stays a method call.
                tok = self.next()
                args = []
                if not self.at_op(")"):
                    while True:
                        args.append(self.parse_expr())
                        if self.at_op(","):
                            self.next()
                            if self.at_op(")"):
                                break
                            continue
                        break
                self.expect_op(")")
                expr = A.MethodCall(expr.base, expr.field, args,
                                    tok.line, tok.col)
                continue
            if self.at_op("("):
                # Calling through a computed fn value: handlers[i](x),
                # make()(x), (f)(x) (Top-500 #103). A bare Var followed
                # by '(' never reaches here — parse_primary makes it a
                # Call — so every '(' here is an indirect call through
                # a computed value, checked against the callee's fn type.
                tok = self.next()
                args = []
                if not self.at_op(")"):
                    while True:
                        args.append(self.parse_expr())
                        if self.at_op(","):
                            self.next()
                            if self.at_op(")"):
                                break
                            continue
                        break
                self.expect_op(")")
                expr = A.IndirectCall(expr, args, tok.line, tok.col)
                continue
            if self.at_op("?"):
                tok = self.next()
                expr = A.Try(expr, tok.line, tok.col)
                continue
            if self.at_op("["):
                tok = self.next()
                idx = self.parse_expr()
                self.expect_op("]")
                expr = A.Index(expr, idx, tok.line, tok.col)
                continue
            if self.at_op("."):
                tok = self.next()
                if self.peek().kind == "INT":
                    # Tuple element read: t.0, t.1, ...
                    idx = self.next()
                    expr = A.TupleIndex(expr, int(idx.value),
                                        tok.line, tok.col)
                    continue
                field = self.expect_ident()
                expr = A.FieldAccess(expr, field.value, tok.line, tok.col)
                continue
            if self.at_kw("as"):
                tok = self.next()
                # No top-level union in a cast target: `x as int | y`
                # is a cast to int followed by a bitwise-or.
                target = self.parse_type(allow_union=False)
                expr = A.Cast(expr, target, tok.line, tok.col)
                continue
            break
        return expr

    def parse_primary(self):
        tok = self.peek()
        if tok.kind == "INT":
            self.next()
            return A.IntLit(tok.value, tok.line, tok.col)
        if tok.kind == "FLOAT":
            self.next()
            return A.FloatLit(tok.value, tok.line, tok.col)
        if tok.kind == "STR":
            self.next()
            return A.StrLit(tok.value, tok.line, tok.col)
        if tok.kind == "KEYWORD" and tok.value in ("true", "false"):
            self.next()
            return A.BoolLit(tok.value == "true", tok.line, tok.col)
        if self.at_kw("fn"):
            # Lambda expression (Top-500 #101): fn(params) -> ret
            # { body } — the fn-declaration shape minus the name.
            # No lexer change: `fn` never starts any other
            # expression form, so this branch is unambiguous.
            kw = self.next()
            params = self.parse_param_list()
            ret = "void"
            if self.at_op("->"):
                self.next()
                ret = self.parse_type()
            body = self.parse_block()
            return A.Lambda(params, ret, body, kw.line, kw.col)
        if tok.kind == "IDENT":
            self.next()
            if self.at_op("("):
                self.next()
                args = []
                if not self.at_op(")"):
                    while True:
                        args.append(self.parse_expr())
                        if self.at_op(","):
                            self.next()
                            if self.at_op(")"):
                                break
                            continue
                        break
                self.expect_op(")")
                return A.Call(tok.value, args, tok.line, tok.col)
            if self.looks_like_struct_lit():
                # Struct literal: Name { field: value, ... }
                self.next()
                fields = []
                if not self.at_op("}"):
                    while True:
                        fname = self.expect_ident()
                        self.expect_op(":")
                        fexpr = self.parse_expr()
                        fields.append((fname.value, fexpr))
                        if self.at_op(","):
                            self.next()
                            if self.at_op("}"):
                                break
                            continue
                        break
                self.expect_op("}")
                return A.StructLit(tok.value, fields, tok.line, tok.col)
            return A.Var(tok.value, tok.line, tok.col)
        if self.at_op("("):
            tok = self.next()
            first = self.parse_expr()
            if self.at_op(","):
                # Tuple literal: (v1, v2, ...) with >= 2 elements.
                elems = [first]
                while self.at_op(","):
                    self.next()
                    if self.at_op(")"):
                        break
                    elems.append(self.parse_expr())
                if len(elems) < 2:
                    raise ForgeError("tuple literals need at least two elements",
                                     tok.line, tok.col)
                self.expect_op(")")
                return A.TupleLit(elems, tok.line, tok.col)
            self.expect_op(")")
            return first
        if self.at_op("["):
            self.next()
            elems = []
            if not self.at_op("]"):
                while True:
                    elems.append(self.parse_expr())
                    if self.at_op(","):
                        self.next()
                        if self.at_op("]"):
                            break
                        continue
                    break
            self.expect_op("]")
            return A.ArrayLit(elems, tok.line, tok.col)
        raise ForgeError(f"expected an expression, got {self._d(tok)}", tok.line, tok.col)


def parse(source):
    return Parser(tokenize(source)).parse_program()
