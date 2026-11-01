"""Compile-time sized arrays (Top-500 #12, v1).

A sized array type is spelled ``[T; N]``: an array whose length
is part of the type. v1 semantics, all checked:

- A sized array literal must hold exactly N elements (checked
  at compile time: the literal length is known). An empty literal
  with a sized annotation is an error unless N is 0.
- Sized arrays index, report len, and iterate exactly like
  dynamic arrays, but push is rejected: the length is fixed.
- A sized array is a distinct type from the dynamic array of
  the same element type; there is no conversion between them
  in v1.
- Representation in v1 is the existing heap array (ForgeArray):
  the size is a type-level contract, enforced at construction,
  and preserved because only sized values flow into sized
  positions. A stack representation is a later slice.
- v1 limits: sized arrays over fixed-width element types are
  rejected with the same error as dynamic fixed arrays (their
  element helpers do not exist yet); big32 and WASM reject
  sized programs with named errors.
"""

import re


def _split_top_level_semicolon(inner):
    """Split an array body on its top-level ';', or None.

    Depth tracks both [] and <> so nested sized arrays
    ("[int; 2]; 3") split at the outer semicolon only.
    """
    depth = 0
    for i, ch in enumerate(inner):
        if ch in "[<":
            depth += 1
        elif ch in "]>":
            depth -= 1
        elif ch == ";" and depth == 0:
            return inner[:i].strip(), inner[i + 1:].strip()
    return None


def is_sized_array(t):
    """True for a '[T; N]' spelling (at the outermost level)."""
    if not (isinstance(t, str) and t.startswith("[") and t.endswith("]")):
        return False
    return _split_top_level_semicolon(t[1:-1]) is not None


def sized_elem(t):
    """Element type of a sized array spelling."""
    parts = _split_top_level_semicolon(t[1:-1])
    return parts[0]


def sized_len(t):
    """Length of a sized array spelling, as an int."""
    parts = _split_top_level_semicolon(t[1:-1])
    return int(parts[1])


def array_elem(t):
    """Element type of any array spelling, sized or dynamic.

    A readonly prefix is stripped first: a view of an array has
    the array's element type."""
    from .readonly import is_readonly, readonly_inner
    if is_readonly(t):
        return array_elem(readonly_inner(t))
    if is_sized_array(t):
        return sized_elem(t)
    return t[1:-1]


def contains_sized(t):
    """True when a type spelling contains a sized array anywhere
    (used by the big32/WASM gates)."""
    if not isinstance(t, str):
        return False
    depth = 0
    for ch in t:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        elif ch == ";" and depth >= 1:
            return True
    return False


def normalize_sized(t):
    """Strip every size from a type spelling: '[T; N]' -> '[T]',
    applied recursively (including nested arrays and generic
    arguments), so downstream code sees the dynamic form.

    A readonly prefix is stripped too: views share the dynamic
    array's layout, so normalization yields the plain form."""
    from .readonly import is_readonly, readonly_inner
    if is_readonly(t):
        return normalize_sized(readonly_inner(t))
    if is_sized_array(t):
        return "[" + normalize_sized(sized_elem(t)) + "]"
    if isinstance(t, str) and t.startswith("[") and t.endswith("]"):
        return "[" + normalize_sized(t[1:-1]) + "]"
    if isinstance(t, str) and "<" in t:
        from .generics import parse_generic
        g = parse_generic(t)
        if g is not None:
            base, args = g
            return base + "<" + ", ".join(normalize_sized(a) for a in args) + ">"
    return t


def find_sized(program):
    """Every type spelling using a sized array in a program,
    sorted. Mirrors the union/fixed walks: signatures, struct
    fields, enum payloads, trait signatures, impl methods, and
    inside bodies the let annotations and cast targets."""
    from . import ast_nodes as A
    found = set()

    def add(t):
        if isinstance(t, str) and contains_sized(t):
            found.add(t)

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
    return sorted(found)
