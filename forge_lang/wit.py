"""WIT-first interface checking for the WASM backend (v1).

WIT is the WebAssembly Component Model's interface language: a
``.wit`` file declares a *world* — the functions a component
exports (and imports) — before the implementation is written.
This module parses a small, honest subset of WIT and checks a
Qasida program against it at compile time, so a program that
does not match its declared interface fails with a clear error
instead of shipping a module whose exports surprise its host.

Supported subset:
  - ``package ns:name;`` (optional, accepted and ignored)
  - exactly one ``world NAME { ... }``
  - world items ``export NAME: func(PARAMS) -> RET;`` and
    ``import NAME: func(PARAMS) -> RET;`` (the return is
    optional, meaning void)
  - types: ``s64``, ``f64``, ``bool``, ``string``,
    ``list<T>`` (nested), and any other ``name`` or
    ``name<T, ...>`` shape, which parses but is rejected by
    the type mapping with a clear message

NOT supported (clear error, not silent acceptance):
  - interface blocks, ``use`` statements, type aliases, and
    interface references in a world (``export x: some-iface``)
  - world imports: the WASM backend emits a self-contained
    module with no imports, so a world that imports anything
    cannot be satisfied
  - component-model binary encoding: this checks the
    interface contract; the emitted module is still a core
    module, not a component (that needs a component runtime
    to verify, which is future work)

Type mapping (Qasida -> WIT): int -> s64, float -> f64,
bool -> bool, str -> string, [T] -> list<T>. Structs, enums,
Option/Result, and anything else have no mapping and fail the
check with a message naming the function and the type.
"""

from .errors import ForgeError


class WitType:
    """A parsed WIT type: name + generic arguments (possibly none)."""

    def __init__(self, name, args=None):
        self.name = name
        self.args = args or []

    def __repr__(self):
        if not self.args:
            return self.name
        return f"{self.name}<{', '.join(repr(a) for a in self.args)}>"


class WitFunc:
    def __init__(self, name, params, ret):
        self.name = name
        self.params = params  # [(param_name, WitType)]
        self.ret = ret  # WitType or None (void)


class WitWorld:
    def __init__(self, name, exports, imports):
        self.name = name
        self.exports = exports  # [WitFunc]
        self.imports = imports  # [WitFunc]


# ---------------------------------------------------------------- tokenizer

def _tokenize(text):
    toks = []  # (kind, value, line)
    i, line = 0, 1
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c in " \t\r":
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise ForgeError("unterminated block comment in WIT file", line, 0)
            line += text[i:j].count("\n")
            i = j + 2
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] in "_-"):
                j += 1
            toks.append(("IDENT", text[i:j], line))
            i = j
        elif text.startswith("->", i):
            toks.append(("ARROW", "->", line))
            i += 2
        elif c in ":;,()<> {}":
            toks.append((c, c, line))
            i += 1
        else:
            raise ForgeError(f"unexpected character {c!r} in WIT file", line, 0)
    toks.append(("EOF", "", line))
    return toks


class _Parser:
    def __init__(self, toks):
        self.toks = toks
        self.pos = 0

    def peek(self):
        return self.toks[self.pos]

    def next(self):
        t = self.toks[self.pos]
        self.pos += 1
        return t

    def expect(self, kind):
        t = self.next()
        if t[0] != kind:
            raise ForgeError(f"expected {kind!r} in WIT file, got {t[1]!r}", t[2], 0)
        return t

    def expect_ident(self, what="identifier"):
        t = self.next()
        if t[0] != "IDENT":
            raise ForgeError(f"expected {what} in WIT file, got {t[1]!r}", t[2], 0)
        return t[1]

    def at_ident(self, value):
        t = self.peek()
        return t[0] == "IDENT" and t[1] == value

    def parse_type(self):
        name = self.expect_ident("a type")
        args = []
        if self.peek()[0] == "<":
            self.next()
            args.append(self.parse_type())
            while self.peek()[0] == ",":
                self.next()
                args.append(self.parse_type())
            self.expect(">")
        return WitType(name, args)

    def parse_func(self):
        self.expect_ident("func")
        self.expect("(")
        params = []
        while self.peek()[0] != ")":
            pname = self.expect_ident("a parameter name")
            self.expect(":")
            params.append((pname, self.parse_type()))
            if self.peek()[0] == ",":
                self.next()
                if self.peek()[0] == ")":
                    break
            else:
                break
        self.expect(")")
        ret = None
        if self.peek()[0] == "ARROW":
            self.next()
            ret = self.parse_type()
        return params, ret

    def parse_world_item(self):
        kind_tok = self.next()
        kind = kind_tok[1]
        name = self.expect_ident("an export/import name")
        self.expect(":")
        if not self.at_ident("func"):
            raise ForgeError(
                f"only func exports/imports are supported in WIT worlds; "
                f"{kind} {name!r} is not a func (interface references are not "
                f"supported)", kind_tok[2], 0)
        params, ret = self.parse_func()
        self.expect(";")
        return WitFunc(name, params, ret)

    def parse(self):
        world = None
        while self.peek()[0] != "EOF":
            if self.at_ident("package"):
                self.next()
                self.expect_ident("a package name")
                if self.peek()[0] == ":":
                    self.next()
                    self.expect_ident("a package name")
                self.expect(";")
            elif self.at_ident("world"):
                wtok = self.next()
                if world is not None:
                    raise ForgeError("only one world is supported in a WIT file",
                                     wtok[2], 0)
                wname = self.expect_ident("a world name")
                self.expect("{")
                exports, imports = [], []
                while self.peek()[0] != "}":
                    if self.peek()[0] == "EOF":
                        raise ForgeError("unterminated world in WIT file",
                                         self.peek()[2], 0)
                    if self.at_ident("export"):
                        exports.append(self.parse_world_item())
                    elif self.at_ident("import"):
                        imports.append(self.parse_world_item())
                    else:
                        t = self.next()
                        raise ForgeError(
                            f"unexpected {t[1]!r} in world; only export/import "
                            f"func declarations are supported", t[2], 0)
                self.expect("}")
                world = WitWorld(wname, exports, imports)
            elif self.at_ident("interface") or self.at_ident("type") \
                    or self.at_ident("use"):
                t = self.next()
                raise ForgeError(
                    f"{t[1]} declarations are not supported in WIT files here; "
                    f"only package + one world with func exports/imports are",
                    t[2], 0)
            else:
                t = self.next()
                raise ForgeError(f"unexpected {t[1]!r} in WIT file", t[2], 0)
        if world is None:
            raise ForgeError("no world declaration found in WIT file", 0, 0)
        return world


def parse_wit(text):
    """Parse WIT source text into a WitWorld (ForgeError on failure)."""
    return _Parser(_tokenize(text)).parse()


# ---------------------------------------------------------------- checking

def forge_type_to_wit(t, fn_name):
    """Map a Qasida type to its WIT type tuple, or raise ForgeError."""
    if t == "int":
        return ("s64",)
    if t == "float":
        return ("f64",)
    if t == "bool":
        return ("bool",)
    if t == "str":
        return ("string",)
    if t.startswith("[") and t.endswith("]"):
        return ("list", forge_type_to_wit(t[1:-1], fn_name))
    raise ForgeError(
        f"function {fn_name!r} uses type {t!r}, which has no WIT mapping "
        f"on the WASM backend", 0, 0)


def wit_type_to_tuple(wt):
    """A parsed WitType as a comparable tuple, or raise ForgeError."""
    if wt.name in ("s64", "f64", "bool", "string") and not wt.args:
        return (wt.name,)
    if wt.name == "list" and len(wt.args) == 1:
        return ("list", wit_type_to_tuple(wt.args[0]))
    raise ForgeError(
        f"WIT type {wt!r} has no Qasida equivalent on the WASM backend",
        0, 0)


def _fmt_wit_tuple(t):
    if t[0] == "list":
        return f"list<{_fmt_wit_tuple(t[1])}>"
    return t[0]


def check_world(world, program_funcs):
    """Check program functions against a parsed WIT world.

    program_funcs: the program's functions (FuncDef nodes). Generic
    functions are skipped (the WASM backend skips them too) and
    ``main`` is exempt: it is the entrypoint, not an interface
    function. Every other function must be declared in the world,
    and every world export must match its function exactly
    (arity, parameter types in order, return type).
    """
    if world.imports:
        names = ", ".join(f.name for f in world.imports)
        raise ForgeError(
            f"WIT imports are not supported: the WASM backend emits a "
            f"self-contained module with no imports (world imports: {names})",
            0, 0)
    prog = {}
    for fn in program_funcs:
        if getattr(fn, "type_params", None):
            continue
        if fn.name == "main":
            continue
        params = [forge_type_to_wit(pt, fn.name) for _pn, pt in fn.params]
        ret = None if fn.ret == "void" else forge_type_to_wit(fn.ret, fn.name)
        prog[fn.name] = (params, ret)
    for wf in world.exports:
        if wf.name not in prog:
            raise ForgeError(
                f"world exports {wf.name!r} but the program has no such "
                f"function", 0, 0)
        params, ret = prog[wf.name]
        if len(wf.params) != len(params):
            raise ForgeError(
                f"world export {wf.name!r} declares {len(wf.params)} "
                f"parameter(s) but the function takes {len(params)}", 0, 0)
        for i, (_pname, wtype) in enumerate(wf.params):
            wt = wit_type_to_tuple(wtype)
            if wt != params[i]:
                raise ForgeError(
                    f"world export {wf.name!r} parameter {i + 1}: WIT type "
                    f"{_fmt_wit_tuple(wt)} but the function takes "
                    f"{_fmt_wit_tuple(params[i])}", 0, 0)
        if wf.ret is None:
            if ret is not None:
                raise ForgeError(
                    f"world export {wf.name!r} returns nothing but the "
                    f"function returns {_fmt_wit_tuple(ret)}", 0, 0)
        else:
            wt = wit_type_to_tuple(wf.ret)
            if ret is None:
                raise ForgeError(
                    f"world export {wf.name!r} returns {_fmt_wit_tuple(wt)} "
                    f"but the function returns nothing", 0, 0)
            if wt != ret:
                raise ForgeError(
                    f"world export {wf.name!r} returns {_fmt_wit_tuple(wt)} "
                    f"but the function returns {_fmt_wit_tuple(ret)}", 0, 0)
    declared = {wf.name for wf in world.exports}
    for name in prog:
        if name not in declared:
            raise ForgeError(
                f"function {name!r} is not declared in the world's exports "
                f"(add it to the world or remove it from the program)", 0, 0)
