"""First-class ranges (Top-500 #18): the `range` type and its
uses in a program, for backend gates.

A program uses ranges when any type position spells `range`
(a parameter, return, struct field, let annotation, or cast
target) or when any expression is a range literal (`a..b`).
The native backend lowers ranges to a start/end struct;
big32 and WASM reject them in v1 with a named error.

Exception (#67, 25 Nov 2026): with `allow_for_source=True`, a
range literal that is the DIRECT iterable of a `for` loop is
not a range use — big32 lowers `for i in lo..hi` to the same
counted loop as `for i in range(n)`. Only the literal itself
is exempt: a range literal nested inside the endpoints is
still flagged, and a range VALUE (`let r = a..b`, `for i in r`)
still counts. WASM keeps the default (no exemption).
"""

import forge_lang.ast_nodes as A


def find_ranges(program, allow_for_source=False):
    """Sorted list of range uses: ['range'] when used, else [].

    With allow_for_source=True, a range literal that is the
    direct iterable of a `for` loop is exempt (see module docstring).
    """
    found = set()

    def add(t):
        if isinstance(t, str) and t == "range":
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
            for _pat, arm_body in getattr(s, "arms", []) or []:
                walk_block(arm_body)
            if (allow_for_source and isinstance(s, A.For)
                    and isinstance(getattr(s, "expr", None), A.RangeLit)):
                # #67: a range literal as the for-loop source is
                # exempt — but walk its endpoints, so a range
                # literal nested inside them is still flagged.
                walk_expr(s.expr.start)
                walk_expr(s.expr.end)
            else:
                walk_expr(getattr(s, "expr", None))

    def walk_expr(e):
        if e is None:
            return
        if isinstance(e, A.RangeLit):
            found.add("range")
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
        if getattr(fn, "type_params", None):
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
    return sorted(found)
