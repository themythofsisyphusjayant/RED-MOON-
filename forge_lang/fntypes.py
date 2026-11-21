"""Function-value types (Top-500 #103).

A fn type is a plain string, like every other Qasida type:
    "fn(int, str) -> bool"
    "fn(int)"             -- -> void is the default, as in fn declarations
    "fn() -> void"
    "fn(fn(int) -> int) -> int"

The parser (parser.py::parse_type) is the single funnel that
produces these spellings; everything here consumes them.
"""

FN_PREFIX = "fn("


def is_fn_type(t):
    """True when t is a fn-type string."""
    return isinstance(t, str) and t.startswith(FN_PREFIX)


def fn_type_string(params, ret):
    """Build the canonical fn-type string.

    params is a list of (name, type) pairs (the FuncDef.params
    shape) or a list of type strings; ret is the return type
    string (\"void\" when the function returns nothing).
    """
    types = []
    for p in params:
        types.append(p[1] if isinstance(p, tuple) else p)
    return "fn(" + ", ".join(types) + ") -> " + ret


def _split_top_level_commas(s):
    """Split s on top-level commas, tracking (), [], <> depth.

    The fn-type arrow `->` is a single token: its `>` must not
    count as an angle-bracket close, or a fn type with a comma
    after its arrow mis-splits.
    """
    out = []
    depth_p = depth_a = depth_b = 0
    cur = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "-" and i + 1 < len(s) and s[i + 1] == ">":
            cur.append("->")
            i += 2
            continue
        if ch == "(":
            depth_p += 1
        elif ch == ")":
            depth_p -= 1
        elif ch == "<":
            depth_a += 1
        elif ch == ">":
            depth_a -= 1
        elif ch == "[":
            depth_b += 1
        elif ch == "]":
            depth_b -= 1
        if ch == "," and depth_p == 0 and depth_a == 0 and depth_b == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur).strip())
    return [o for o in out if o]


def fn_parts(t):
    """Split a fn-type string into (params, ret), or None.

    params is a list of type strings, ret a type string. Returns
    None when t is not a fn type or is malformed (unbalanced
    parens, missing '->'). Never raises: callers treat None as
    \"not a fn type\".
    """
    if not is_fn_type(t):
        return None
    # Find the closing paren of the parameter list, depth-aware.
    depth = 0
    close = -1
    for i, ch in enumerate(t):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                close = i
                break
    if close < 0:
        return None
    inner = t[len(FN_PREFIX):close]
    rest = t[close + 1:].strip()
    if not rest.startswith("->"):
        return None
    ret = rest[2:].strip()
    if not ret:
        return None
    params = _split_top_level_commas(inner) if inner.strip() else []
    return params, ret


def fn_mangle(t):
    """C identifier fragment for a fn type.

    fn(int, str) -> bool  ->  ForgeFn_int_str_bool
    fn() -> bool          ->  ForgeFn_void_bool  (empty params = void)
    fn(int) -> void       ->  ForgeFn_int_void
    Nested fn types recurse: fn(fn(int) -> int) -> int becomes
    ForgeFn_ForgeFn_int_int_int. Array fragments use mangle_type
    ([int] -> Array_int); struct names pass through.
    """
    parts = fn_parts(t)
    if parts is None:
        raise ValueError(f"not a fn type: {t!r}")
    params, ret = parts
    from .generics import mangle_type
    frags = [mangle_type(p) if p != "void" else "void" for p in params]
    if not frags:
        frags = ["void"]
    return "ForgeFn_" + "_".join(frags + [mangle_type(ret)])


def fn_c_name(t):
    """Typedef name for a fn type (alias for fn_mangle)."""
    return fn_mangle(t)


def fn_depth(t):
    """Nesting depth of fn types inside t (for typedef order)."""
    return t.count("fn(") if isinstance(t, str) else 0


def extract_fn_types(t, out):
    """Add every fn type occurring in type string t to set out.

    Recurses into fn params/ret, array elements, tuple elements,
    and generic arguments, so nested fn types get their own
    typedefs too.
    """
    if not isinstance(t, str) or "fn(" not in t:
        return
    if is_fn_type(t):
        out.add(t)
        params, ret = fn_parts(t)
        for p in params:
            extract_fn_types(p, out)
        extract_fn_types(ret, out)
        return
    if t.startswith("[") and t.endswith("]"):
        extract_fn_types(t[1:-1], out)
        return
    if t.startswith("(") and t.endswith(")"):
        from .tuples import is_tuple_type, tuple_elems
        if is_tuple_type(t):
            for e in tuple_elems(t):
                extract_fn_types(e, out)
        return
    from .generics import parse_generic
    g = parse_generic(t)
    if g is not None:
        for a in g[1]:
            extract_fn_types(a, out)


def find_fn_types(program, extra_types=None):
    """Every fn type used in a program, inner typedefs first.

    Walks the type positions only: function signatures, struct
    fields, enum payloads, and inside bodies the let annotations
    and cast targets. extra_types (the infer pass's per-node types)
    covers fn types that only ever flow through inference — a
    `let f = add_one;` with no annotation and no fn-typed
    parameter still needs its typedef. Returns a list sorted by
    (nesting depth, name) so an inner fn typedef is always emitted
    before an outer one that references it. Mirrors find_unions.
    """
    from . import ast_nodes as A
    found = set()

    def add(t):
        extract_fn_types(t, found)

    def walk_block(block):
        for s in getattr(block, "stmts", []) or []:
            if isinstance(s, A.Let):
                add(s.ann)
            if isinstance(s, A.Cast):
                add(getattr(s, "target", None))
            if isinstance(s, A.Block):
                walk_block(s)
            for attr in ("body", "then", "els"):
                b = getattr(s, attr, None)
                if b is not None:
                    walk_block(b)
            for _pat, _bind, arm_body in getattr(s, "arms", []) or []:
                walk_block(arm_body)
            for attr in ("expr", "cond"):
                e = getattr(s, attr, None)
                if e is not None:
                    walk_expr(e)

    def walk_expr(e):
        if e is None:
            return
        for attr in ("args", "elems"):
            for child in getattr(e, attr, []) or []:
                walk_expr(child)
        for attr in ("expr", "callee", "base", "left", "right", "index", "start", "end"):
            walk_expr(getattr(e, attr, None))
        if isinstance(e, A.Cast):
            add(getattr(e, "target", None))

    for fn in getattr(program, "funcs", []) or []:
        if getattr(fn, "type_params", None):
            # Generic template: its fn types mention type params
            # (fn(T) -> T) and have no C typedef. The check epilogue
            # appends every concrete instantiation to program.funcs,
            # and those are the ones codegen emits.
            continue
        for _n, pt in fn.params:
            add(pt)
        add(fn.ret)
        if getattr(fn, "body", None) is not None:
            walk_block(fn.body)
    for sd in getattr(program, "structs", None) or []:
        if getattr(sd, "type_params", None):
            continue
        fields = sd.fields
        pairs = fields.items() if isinstance(fields, dict) else fields
        for _fname, ft in pairs:
            add(ft)
    for ed in getattr(program, "enums", None) or []:
        if getattr(ed, "type_params", None):
            continue
        for _v, pt in (getattr(ed, "variant_payloads", None) or {}).items():
            add(pt)
    for t in extra_types or []:
        add(t)
    return sorted(found, key=lambda t: (fn_depth(t), t))
