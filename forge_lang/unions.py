"""Union types (Top-500 #7, v1).

A union type is a type spelling like ``int | str``: a value of the
union holds exactly one member value, tagged by its member index.
v1 members are the four scalars (int, float, bool, str); struct,
enum, array, and generic members are a later slice. Values enter a
union only through assignment, arguments, returns, and struct fields
(a member value is wrapped at the site), and leave it only through
``match`` arms named by member type, which bind the narrowed value.
Arrays of unions and subset conversions are later slices too.

Type spellings flow through the compiler as plain strings, so unions
are recognised by shape: a top-level ``|`` (outside ``[]`` and
``<>``). This module is the single place that knows that shape.
"""

from . import ast_nodes as A

UNION_MEMBERS_V1 = ("int", "float", "bool", "str")


def _split_top_level(t):
    """Split a type spelling on top-level ``|`` (depth 0 in [] and <>)."""
    parts = []
    depth = 0
    cur = []
    for ch in t:
        if ch in "[<":
            depth += 1
            cur.append(ch)
        elif ch in "]>":
            depth -= 1
            cur.append(ch)
        elif ch == "|" and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur).strip())
    return parts


def is_union_type(t):
    """True when t is a union spelling (a top-level |)."""
    return isinstance(t, str) and len(_split_top_level(t)) > 1


def union_members(t):
    """Member type spellings of a union, in declared order."""
    return _split_top_level(t)


def union_c_name(t):
    """C struct name for a union type: ForgeUnion_int_str."""
    return "ForgeUnion_" + "_".join(union_members(t))


def union_str_index(t):
    """Index of the str member of a union, or None when it has none."""
    members = union_members(t)
    return members.index("str") if "str" in members else None


def find_unions(program):
    """Every union type spelling used in a program, sorted.

    Walks the type positions only: function signatures, struct
    fields, enum payloads, trait signatures, impl methods, and
    inside bodies the let annotations and cast targets. Bodies are
    walked generically so nested blocks, branches, loops, and
    match arms are all covered.
    """
    found = set()

    def add(t):
        if isinstance(t, str) and is_union_type(t):
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
            # Expressions nested in statements (calls, literals,
            # field assignments) can carry cast targets too.
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
