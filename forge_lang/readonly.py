"""Readonly collection views (Top-500 #13, v1).

A readonly view is spelled ``readonly [T]`` (or ``readonly
[T; N]`` for a sized array): a handle through which a collection
can be read (index, len, iteration) but not written (no push,
no index assignment). A mutable array coerces to a readonly
view of the same array kind (dynamic to dynamic, sized to
sized with the same length); a view never coerces back to a
mutable array, and kinds never mix.

v1 semantics, all checked:
- Shallow: the restriction is on the handle, not the data. The
  underlying array is shared (the same refcounted buffer), so
  mutations through the original mutable handle are visible
  through the view, and elements retrieved from a view of
  nested arrays are themselves mutable. Deep immutability is a
  later slice (it needs readonly propagation through element
  types).
- Representation is the existing heap array: like sized arrays,
  the view is a type-level contract over shared runtime.
- v1 limits: readonly applies to array types only (strings are
  already immutable; readonly structs are a later slice);
  big32 and WASM reject readonly programs with named errors.
"""

PREFIX = "readonly "


def is_readonly(t):
    """True for a 'readonly ...' type spelling."""
    return isinstance(t, str) and t.startswith(PREFIX)


def readonly_inner(t):
    """The array type inside a readonly view spelling."""
    return t[len(PREFIX):]


def strip_readonly(t):
    """Remove a readonly prefix if present, else return t."""
    return readonly_inner(t) if is_readonly(t) else t


def find_readonly(program):
    """Every readonly type spelling used in a program, sorted.
    Mirrors the union/fixed/sized walks."""
    from . import ast_nodes as A
    found = set()

    def add(t):
        if isinstance(t, str) and is_readonly(t):
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
