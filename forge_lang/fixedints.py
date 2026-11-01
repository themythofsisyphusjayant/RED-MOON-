"""Fixed-width integer types (Top-500 #9, v1).

The language's ``int`` is a 64-bit signed integer. v1 adds the
other widths as distinct scalar types: i8, i16, i32, u8, u16, u32,
u64. ``i64`` is not a separate type: it is accepted as a spelling
for ``int`` (the parser normalises it), so the two names never
form a parallel universe.

Rules, all checked:
- Same-type arithmetic, comparison, and bitwise operations only;
  mixed widths need an explicit cast.
- Integer literals adapt to an expected fixed type when they fit
  (range-checked at compile time, including negative literals);
  a general int expression does not adapt.
- Arithmetic is checked, like int: +,-,* on a fixed type fail on
  overflow (computed widened, then range-checked); / fails on
  division by zero and on signed-min / -1; shifts fail on an
  out-of-range count. % and bitwise operations cannot overflow
  and need only the division-by-zero check (%).
- Casts between int types are allowed; narrowing casts fail when
  the value does not fit, widening casts are free.
- v1 limits: no arrays of fixed-width types (their literals and
  push checks stay strict, and codegen rejects the array type
  outright); big32 and WASM reject fixed-width programs.
"""

FIXED_INTS = ("i8", "i16", "i32", "u8", "u16", "u32", "u64")

FIXED_RANGES = {
    "i8": (-128, 127),
    "i16": (-32768, 32767),
    "i32": (-2147483648, 2147483647),
    "u8": (0, 255),
    "u16": (0, 65535),
    "u32": (0, 4294967295),
    "u64": (0, 18446744073709551615),
}

FIXED_WIDTHS = {
    "i8": 8, "i16": 16, "i32": 32,
    "u8": 8, "u16": 16, "u32": 32, "u64": 64,
}

FIXED_C_TYPES = {
    "i8": "int8_t", "i16": "int16_t", "i32": "int32_t",
    "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t",
    "u64": "uint64_t",
}

INT_TYPES = ("int",) + FIXED_INTS


def is_fixed_int(t):
    """True for the seven distinct fixed-width integer types."""
    return t in FIXED_RANGES


def is_int_type(t):
    """True for int and every fixed-width integer type."""
    return t == "int" or t in FIXED_RANGES


def fixed_range(t):
    """(min, max) for a fixed-width integer type."""
    return FIXED_RANGES[t]


def is_signed_fixed(t):
    """True for the signed fixed-width types."""
    return t in ("i8", "i16", "i32")


def literal_value(expr):
    """Integer value of a literal expression, or None.

    Covers direct literals and negated literals (-5 parses as a
    unary minus over a literal, not as a negative literal).
    """
    from . import ast_nodes as A
    if isinstance(expr, A.IntLit):
        return expr.value
    if isinstance(expr, A.UnaryOp) and expr.op == "-" \
            and isinstance(expr.expr, A.IntLit):
        return -expr.expr.value
    return None


def _type_tokens(t):
    """Identifier tokens inside a type spelling (split on the
    structural characters, so a struct named Bi32 never matches
    the fixed type i32 by substring)."""
    import re
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]*", t or "")


def find_fixed(program):
    """Every fixed-width integer type used in a program, sorted.

    Mirrors the union walk: function signatures, struct fields,
    enum payloads, trait signatures, impl methods, and inside
    bodies the let annotations and cast targets.
    """
    from . import ast_nodes as A
    found = set()

    def add(t):
        for tok in _type_tokens(t):
            if tok in FIXED_RANGES:
                found.add(tok)

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
