"""Tuple types (Top-500 #19, v1).

A tuple type is spelled ``(T1, T2, ...)`` with at least two
elements; a tuple value is written ``(v1, v2, ...)`` and its
elements are read as ``t.0``, ``t.1``, and so on. Tuples are
fixed-arity, heterogeneous, and ordered: ``(int, str)`` and
``(str, int)`` are different types, and there is no conversion
between tuple types of different arity or element types.

Representation: a tuple is a C struct with fields ``_0``,
``_1``, ... in element order, named ``ForgeTuple_<elems>``
with structure-preserving element names (so a nested tuple's
name embeds its own tuple name, and no two different tuple
types collide). Like structs, tuple values are owned: string
elements are copied, array elements gain a reference, and
nested struct/tuple elements are made independent, with the
matching frees at scope end.

v1 limits: at least two elements (no 1-tuples, no unit ``()``
value); no destructuring (``let (a, b) = t`` is a later
slice); no equality or printing on tuples (like unions).
big32 and WASM reject tuple programs with named errors.
"""


def split_top_level(s, sep=","):
    """Split s on sep at nesting depth 0 over (), [], and <>."""
    parts = []
    depth_paren = depth_brack = depth_angle = 0
    cur = []
    for ch in s:
        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren -= 1
        elif ch == "[":
            depth_brack += 1
        elif ch == "]":
            depth_brack -= 1
        elif ch == "<":
            depth_angle += 1
        elif ch == ">":
            depth_angle -= 1
        if ch == sep and depth_paren == 0 and depth_brack == 0 and depth_angle == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur).strip())
    return parts


def is_tuple_type(t):
    """True for a '(T1, T2, ...)' spelling with >= 2 elements."""
    if not (isinstance(t, str) and t.startswith("(") and t.endswith(")")):
        return False
    inner = t[1:-1].strip()
    if not inner:
        return False
    return len(split_top_level(inner)) >= 2


def tuple_elems(t):
    """Element type spellings of a tuple type, in order."""
    return split_top_level(t[1:-1].strip())


def _elem_c_name(t):
    """Structure-preserving C-name fragment for one element."""
    if is_tuple_type(t):
        return tuple_c_name(t)
    if t.startswith("[") and t.endswith("]"):
        from .sizedarrays import is_sized_array, sized_elem
        if is_sized_array(t):
            return "Arr_" + _elem_c_name(f"[{sized_elem(t)}]")
        return "Arr_" + _elem_c_name(t[1:-1])
    if t.startswith("readonly "):
        from .readonly import readonly_inner
        return "RO_" + _elem_c_name(readonly_inner(t))
    if t.startswith("opaque "):
        return "Opaque_" + t[len("opaque "):]
    if " | " in t:
        return "Union_" + "_".join(_elem_c_name(m) for m in t.split(" | "))
    if "<" in t and t.endswith(">"):
        base = t[:t.find("<")]
        args = split_top_level(t[t.find("<") + 1:-1])
        return base + "_" + "_".join(_elem_c_name(a) for a in args)
    return t


def tuple_c_name(t):
    """C struct name for a tuple type."""
    return "ForgeTuple_" + "_".join(_elem_c_name(e) for e in tuple_elems(t))


def find_tuples(program):
    """Every tuple type spelling used in a program, sorted by
    increasing length so nested tuples' inner types come first
    (an outer tuple's struct contains the inner's struct).
    Mirrors the union/fixed/sized/readonly/never walks."""
    from . import ast_nodes as A
    found = set()

    def add(t):
        if isinstance(t, str) and is_tuple_type(t):
            found.add(t)
            for e in tuple_elems(t):
                add(e)

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
            walk_expr(getattr(s, "expr", None))

    def walk_expr(e):
        if e is None:
            return
        if isinstance(e, A.Cast):
            add(getattr(e, "target", None))
        for v in vars(e).values():
            if isinstance(v, list):
                for item in v:
                    if hasattr(item, "__dict__"):
                        walk_expr(item)
            elif hasattr(v, "__dict__"):
                walk_expr(v)

    for fn in getattr(program, "funcs", []) or []:
        for _n, pt in getattr(fn, "params", []) or []:
            add(pt)
        add(getattr(fn, "ret", None))
        if getattr(fn, "body", None) is not None:
            walk_block(fn.body)
    for sd in getattr(program, "structs", None) or []:
        fields = sd.fields
        pairs = fields.items() if isinstance(fields, dict) else fields
        for _fname, ft in pairs:
            add(ft)
    for ed in getattr(program, "enums", None) or []:
        for pt in (getattr(ed, "variant_payloads", None) or {}).values():
            add(pt)
    for td in getattr(program, "traits", None) or []:
        for _name, params, ret, _line, _col in getattr(td, "methods", []) or []:
            for _pn, pt in params:
                add(pt)
            add(ret)
    for impl in getattr(program, "impls", None) or []:
        for m in getattr(impl, "methods", []) or []:
            for _n, pt in getattr(m, "params", []) or []:
                add(pt)
            add(getattr(m, "ret", None))
            if getattr(m, "body", None) is not None:
                walk_block(m.body)
    return sorted(found, key=lambda t: (len(t), t))
