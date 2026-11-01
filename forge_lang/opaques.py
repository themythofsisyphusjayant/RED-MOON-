"""Opaque types (Top-500 #8, v1).

``opaque Trait`` hides a concrete implementation behind its trait
interface: the caller can call the trait's methods on the value and
pass it around, but cannot see, name, or construct the concrete
type, and cannot match on it. This is the existential reading (any
value implementing the trait), not Rust's per-function distinct
``impl Trait``: two opaque values of the same trait mix freely.

At runtime an opaque value is a tagged struct: the tag selects the
concrete implementation (in impl-block order for the trait), and
the payload is a union over the implementing structs. Method calls
dispatch by switching on the tag. Copying and freeing dispatch the
same way, through generated helpers, so an implementation struct
with string fields is owned correctly.

v1 limits: opaque types appear in function returns, parameters,
and let annotations (and anywhere a value of opaque type flows:
assignment, arguments, returns). Struct fields cannot be opaque,
arrays of opaque values cannot be built (their literals and push
checks stay strict), and big32/WASM reject opaque programs.
"""

from . import ast_nodes as A


def is_opaque_type(t):
    """True when t is an opaque spelling ('opaque Trait')."""
    return isinstance(t, str) and t.startswith("opaque ") and len(t) > 7 \
        and " " not in t[7:] and "|" not in t and "<" not in t \
        and "[" not in t


def opaque_trait(t):
    """The trait name of an opaque type spelling."""
    return t[len("opaque "):]


def opaque_c_name(t):
    """C struct name for an opaque type: Opaque_Shape."""
    return "Opaque_" + opaque_trait(t)


def impls_for_trait(program, trait):
    """Implementing struct names for a trait, in impl-block order."""
    out = []
    for idf in getattr(program, "impls", None) or []:
        if getattr(idf, "trait", None) == trait and idf.struct not in out:
            out.append(idf.struct)
    return out


def find_opaques(program):
    """Every opaque type spelling used in a program, sorted.

    Same type positions as find_unions: signatures, struct fields,
    enum payloads, trait signatures, impl methods, and inside
    bodies the let annotations and cast targets.
    """
    found = set()

    def add(t):
        if isinstance(t, str) and is_opaque_type(t):
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
