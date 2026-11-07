"""Static checker for The Jal Pari Language.

Types: int, float, bool, str, void, and [T] dynamic arrays.
Builtins:
  statement-only: print, println, push, fail
  expression: len, range, clock_micros, sqrt, exp, log, pow, abs
Rules: no null, no implicit conversion (except int->float via `as`),
immutable by default, bool conditions only, checked calls, and a
non-void function must end with a return.
"""

import copy
import difflib

from .errors import ForgeError
from . import ast_nodes as A
from .generics import (parse_generic, mangle_type, substitute_type,
                       unify, contains_type_param)
from .unions import (is_union_type, union_members, UNION_MEMBERS_V1)
from .opaques import is_opaque_type, opaque_trait
from .fixedints import (is_fixed_int, is_int_type, fixed_range,
                        literal_value)
from .sizedarrays import is_sized_array, sized_len
from .readonly import is_readonly, readonly_inner
from .tuples import is_tuple_type, tuple_elems


def type_matches(value, expected):
    """Value type accepted where an expected type is declared.

    Exact equality, plus a member value where a union is expected:
    an int is a valid `int | str`. A union value is never accepted
    for a single member (it might hold the other member), and a
    union is never accepted for a different union (subset
    conversions are a later slice).
    """
    if value == expected:
        return True
    return is_union_type(expected) and value in union_members(expected)


def matches_up_to_unknown(value, expected):
    """Value type matches expected where empty literals leave holes.

    An empty array literal has no element type of its own, so
    checking it yields `[?]`; nested, that becomes `[[?]]` and so
    on. A hole matches any expected type in the same position,
    except a sized array (an empty literal has 0 elements, never
    the sized length) — so `[[?]]` is a valid `[[int]]` but not a
    valid `[[int; 2]]`. Holes only count inside array/tuple
    positions: a bare `?` never matches, so generic `?`
    placeholders are untouched.
    """
    if value == expected:
        return True
    if (value.startswith("[") and value.endswith("]")
            and expected.startswith("[") and expected.endswith("]")):
        if is_sized_array(value) or is_sized_array(expected):
            return False
        return matches_up_to_unknown(value[1:-1], expected[1:-1])
    if is_tuple_type(value) and is_tuple_type(expected):
        ve, ee = tuple_elems(value), tuple_elems(expected)
        return (len(ve) == len(ee)
                and all(matches_up_to_unknown(v, e)
                        for v, e in zip(ve, ee)))
    if value == "?":
        return True
    return False

SCALARS = {"int", "float", "bool", "str", "range",
           "i8", "i16", "i32", "u8", "u16", "u32", "u64", "never"}
# C keywords that are not Jal Pari keywords: user names colliding
# with these compile to invalid C on the native backend (e.g. a
# function named `double` becomes `long long double(...)`), so
# the checker rejects them with a clear message instead of
# letting the C compiler fail cryptically.
C_KEYWORDS = {"auto", "case", "char", "const", "continue", "default",
              "do", "double", "float", "goto", "inline", "int", "long",
              "register", "restrict", "short", "signed", "sizeof",
              "static", "switch", "typedef", "union", "unsigned",
              "void", "volatile", "_Bool", "_Complex", "_Imaginary"}
STMT_BUILTINS = {"print", "println", "push", "pin", "fail", "assert", "poke32",
                 "mmap_set", "mmap_close", "mmap_set32",
                 "csr_write", "csr_set", "csr_clear"}
EXPR_BUILTINS = {"len", "range", "clock_micros", "sqrt", "exp", "log", "pow", "abs",
                 "wrapping_add", "wrapping_sub", "wrapping_mul", "wrapping_neg",
                 "read_file", "read_line", "write_file", "read_bytes", "write_bytes",
                 "file_exists", "args", "parse_int", "parse_float",
                 "try_alloc",
                 "split", "join", "substr", "trim", "starts_with", "ends_with",
                 "http_get", "http_listen", "http_accept", "http_read_request",
                 "http_respond", "http_respond_status", "http_close",
                 "alloc_count", "free_count",
                 "parallel_dot", "parallel_matmul",
                 "arr_alloc_count", "arr_free_count", "refcount",
                 "weak_new", "weak_upgrade", "move",
                 "mmap_open", "mmap_get", "mmap_grow", "mmap_get32",
                 "peek32", "csr_read", "ecall", "ecall3"}
BUILTINS = STMT_BUILTINS | EXPR_BUILTINS


def suggest(name, candidates):
    """A "Did you mean ...?" suffix, or "" when nothing is close."""
    m = difflib.get_close_matches(name, sorted(candidates), n=1, cutoff=0.6)
    return f". Did you mean '{m[0]}'?" if m else ""


def cast_hint(got, want):
    """A conversion hint for int/float mismatches, or ""."""
    if got == "int" and want == "float":
        return "; convert the value with 'value as float'"
    if got == "float" and want == "int":
        return "; convert the value with 'value as int' (truncates)"
    return ""


def elem_type(arr_type):
    from .sizedarrays import is_sized_array, sized_elem
    if is_readonly(arr_type):
        return elem_type(readonly_inner(arr_type))
    if is_sized_array(arr_type):
        return sized_elem(arr_type)
    return arr_type[1:-1] if arr_type.startswith("[") else None


class Checker:
    def __init__(self, program, freestanding=False):
        self.program = program
        self.freestanding = freestanding
        self.funcs = {}
        self.structs = {}  # name -> {field: type}
        self.struct_params = {}  # name -> [type params]
        self.enums = {}  # name -> [variants]
        self.enum_variants = {}  # variant -> enum name
        self.enum_params = {}  # enum name -> [type params]
        self.enum_payloads = {}  # enum name -> {variant: payload type or None}
        self.enum_instantiations = {}  # concrete type -> {variant: (tag, payload type)}
        self.scopes = []
        self.current_ret = "void"
        self.current_fn = None
        self.current_type_params = []
        self.loop_depth = 0
        self.branch_depth = 0
        self.moved = set()
        self.moved_fields = set()
        self.pinned = set()
        self._in_field_base = 0
        self._in_pinned_base = 0
        self._pinned_write_root = None
        self._pinned_observe = 0
        self._moved_field_target = None
        self.loop_vars = []
        self.func_instantiations = {}  # (name, bindings tuple) -> FuncDef
        self.struct_instantiations = {}  # concrete type -> {field: type}
        self._instantiating = set()
        self.unresolved = {}  # (scope id, name) -> Let node, for empty
        # array literals whose element type no later use has fixed yet.

    def _is_concrete_array(self, t):
        """A usable inference constraint: an array type with no
        unknown element (no '?' anywhere in it)."""
        return (isinstance(t, str) and t.startswith("[")
                and t.endswith("]") and "?" not in t)

    def _resolve_empty(self, name, concrete):
        """Resolve an unresolved empty-array let to a concrete
        array type: rewrite its scope entry and its AST annotation
        (so later checks, and the infer pass that runs after this
        one, see an ordinary annotated let). Returns True when
        a resolution happened."""
        if not self._is_concrete_array(concrete):
            return False
        scope = None
        for sc in reversed(self.scopes):
            if name in sc:
                scope = sc
                break
        if scope is None:
            return False
        t, mutable = scope[name]
        if t != "[?]":
            return False
        key = (id(scope), name)
        let = self.unresolved.get(key)
        if let is None:
            return False
        scope[name] = (concrete, mutable)
        let.ann = concrete
        del self.unresolved[key]
        return True

    def valid_type(self, t):
        if t in SCALARS:
            return True
        if t in self.current_type_params:
            return True
        if t in self.structs or t in self.enums:
            return True
        if t in getattr(self, "newtypes", set()):
            return True
        if is_union_type(t):
            # v1 unions: at least two distinct scalar members.
            members = union_members(t)
            return (len(members) >= 2 and len(set(members)) == len(members)
                    and all(m in UNION_MEMBERS_V1 for m in members))
        if is_opaque_type(t):
            # An opaque type needs a real trait with at least one
            # implementation: otherwise no value of it can exist.
            trait = opaque_trait(t)
            return (trait in getattr(self, "trait_names", set())
                    and len(getattr(self, "trait_impls", {}).get(trait, [])) >= 1)
        if is_readonly(t):
            # A readonly view needs a plain, valid array inside:
            # no nesting, no non-arrays (the parser already
            # rejects both, this is the safety net).
            inner = readonly_inner(t)
            return (not is_readonly(inner) and inner.startswith("[")
                    and inner.endswith("]") and self.valid_type(inner))
        if is_tuple_type(t):
            # Every element type must itself be valid (recurses
            # into nested tuples, arrays, unions, and generics).
            return all(self.valid_type(e) for e in tuple_elems(t))
        g = parse_generic(t)
        if g is not None:
            base, args = g
            if base in self.structs:
                if len(args) != len(self.struct_params.get(base, [])):
                    return False
                return all(self.valid_type(a) for a in args)
            if base in self.enums:
                if len(args) != len(self.enum_params.get(base, [])):
                    return False
                return all(self.valid_type(a) for a in args)
            return False
        if t.startswith("[") and t.endswith("]"):
            # Sized arrays: the element type recurses, and the
            # size must be a non-negative integer literal.
            from .sizedarrays import is_sized_array, sized_elem, sized_len
            if is_sized_array(t):
                try:
                    n = sized_len(t)
                except ValueError:
                    return False
                return n >= 0 and self.valid_type(sized_elem(t))
            # Element types recurse: structs, generics, and nested
            # arrays are all valid element types.
            return self.valid_type(t[1:-1])
        return False

    def enum_info_for(self, t):
        """Return (base, {variant: (tag, concrete payload type)}) for an enum type."""
        if t in self.enums and not self.enum_params.get(t):
            return t, {v: (i, self.enum_payloads[t][v])
                       for i, v in enumerate(self.enums[t])}
        g = parse_generic(t)
        if g is not None and g[0] in self.enums:
            base, args = g
            params = self.enum_params.get(base, [])
            if len(args) != len(params):
                return None
            if "?" in args:
                return None
            bindings = dict(zip(params, args))
            info = {}
            for i, v in enumerate(self.enums[base]):
                pt = self.enum_payloads[base][v]
                info[v] = (i, substitute_type(pt, bindings) if pt is not None else None)
            self.enum_instantiations[t] = info
            return base, info
        return None

    def fill_placeholder(self, provided, expected):
        """If provided is a generic type with '?' params and expected is
        the same base with concrete params, return expected; else provided."""
        gp = parse_generic(provided)
        ge = parse_generic(expected)
        if gp is not None and ge is not None and gp[0] == ge[0] and len(gp[1]) == len(ge[1]):
            if "?" in gp[1]:
                return expected
        return provided

    def struct_fields_for(self, t):
        """Concrete field dict for a struct type string, or None."""
        if t in self.structs and not self.struct_params.get(t):
            return self.structs[t]
        g = parse_generic(t)
        if g is not None:
            base, args = g
            if base not in self.structs:
                return None
            params = self.struct_params.get(base, [])
            if len(args) != len(params):
                return None
            bindings = dict(zip(params, args))
            return {f: substitute_type(ft, bindings)
                    for f, ft in self.structs[base].items()}
        return None

    def check_structs(self):
        structs = getattr(self.program, "structs", None) or []
        for sd in structs:
            if sd.name in self.structs:
                raise ForgeError(f"duplicate struct '{sd.name}'", sd.line, sd.col)
            if sd.name in C_KEYWORDS:
                raise ForgeError(f"'{sd.name}' is a C keyword and cannot be used as a "
                                 f"name; rename it", sd.line, sd.col)
            if sd.name in SCALARS or sd.name in BUILTINS:
                raise ForgeError(f"'{sd.name}' cannot be a struct name", sd.line, sd.col)
            seen = set()
            fields = {}
            for fname, ftype in sd.fields:
                if fname in seen:
                    raise ForgeError(f"duplicate field '{fname}' in struct '{sd.name}'",
                                     sd.line, sd.col)
                if fname in C_KEYWORDS:
                    raise ForgeError(f"'{fname}' is a C keyword and cannot be used as a "
                                     f"field name; rename it", sd.line, sd.col)
                seen.add(fname)
                fields[fname] = ftype
            self.structs[sd.name] = fields
            self.struct_params[sd.name] = list(getattr(sd, "type_params", None) or [])
        # Validate field types now that all struct names are known, and
        # reject recursive structs (C value fields cannot be recursive).
        for sd in structs:
            self.current_type_params = list(getattr(sd, "type_params", None) or [])
            for fname, ftype in sd.fields:
                if not self.valid_type(ftype):
                    raise ForgeError(f"unknown field type '{ftype}' in struct '{sd.name}'",
                                     sd.line, sd.col)
                if is_opaque_type(ftype):
                    raise ForgeError(f"opaque struct fields are not supported in v1; "
                                     f"struct '{sd.name}' field '{fname}' cannot be "
                                     f"'{ftype}'", sd.line, sd.col)
            self.current_type_params = []
            # Cycle check: follow struct-typed fields.
            stack = [sd.name]
            visited = set()
            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                for ftype in self.structs.get(cur, {}).values():
                    if ftype in self.structs:
                        if ftype == sd.name:
                            raise ForgeError(f"recursive struct '{sd.name}' is not supported",
                                             sd.line, sd.col)
                        stack.append(ftype)

    def check_enums(self):
        enums = getattr(self.program, "enums", None) or []
        for ed in enums:
            if ed.name in self.enums or ed.name in self.structs or ed.name in SCALARS:
                raise ForgeError(f"duplicate type '{ed.name}'", ed.line, ed.col)
            seen = set()
            for v in ed.variants:
                if v in seen or v in self.enum_variants:
                    raise ForgeError(f"duplicate enum variant '{v}'", ed.line, ed.col)
                seen.add(v)
                self.enum_variants[v] = ed.name
            self.enums[ed.name] = list(ed.variants)
            self.enum_params[ed.name] = list(getattr(ed, "type_params", None) or [])
            payloads = getattr(ed, "variant_payloads", None) or {}
            self.enum_payloads[ed.name] = {v: payloads.get(v) for v in ed.variants}
            # Validate payload types (type params of this enum are allowed).
            self.current_type_params = list(getattr(ed, "type_params", None) or [])
            for v, pt in self.enum_payloads[ed.name].items():
                if pt is not None and not self.valid_type(pt):
                    raise ForgeError(f"unknown payload type '{pt}' for variant '{v}'",
                                     ed.line, ed.col)
            self.current_type_params = []

    def collect_newtypes(self):
        """Collect `newtype` declarations (v1).

        A newtype is DISTINCT from its underlying type: only the
        name is registered here (targets are validated after the
        struct/enum tables exist, like alias targets). Chains are
        allowed: newtype B = A where A is itself a newtype.
        """
        self.newtypes = set()
        self.newtype_targets = {}
        self.newtype_lines = {}
        struct_names = {sd.name for sd in
                        (getattr(self.program, "structs", None) or [])}
        enum_names = {ed.name for ed in
                      (getattr(self.program, "enums", None) or [])}
        alias_names = {ad.name for ad in
                       (getattr(self.program, "aliases", None) or [])}
        generic_names = {}
        for sd in (getattr(self.program, "structs", None) or []):
            if getattr(sd, "type_params", None):
                generic_names[sd.name] = "struct"
        for ed in (getattr(self.program, "enums", None) or []):
            if getattr(ed, "type_params", None):
                generic_names[ed.name] = "enum"
        for nd in (getattr(self.program, "newtypes", None) or []):
            if nd.name in self.newtypes:
                raise ForgeError(f"duplicate newtype '{nd.name}'",
                                 nd.line, nd.col)
            if nd.name in SCALARS:
                raise ForgeError(f"newtype '{nd.name}' collides with the "
                                 f"built-in type '{nd.name}'", nd.line, nd.col)
            if (nd.name in struct_names or nd.name in enum_names
                    or nd.name in alias_names):
                raise ForgeError(f"newtype '{nd.name}' collides with an "
                                 f"existing type of the same name",
                                 nd.line, nd.col)
            if nd.target in generic_names:
                kind = generic_names[nd.target]
                raise ForgeError(f"newtype '{nd.name}' cannot target "
                                 f"generic {kind} '{nd.target}' without "
                                 f"type arguments; write {nd.target}<...>",
                                 nd.line, nd.col)
            self.newtypes.add(nd.name)
            self.newtype_targets[nd.name] = nd.target
            self.newtype_lines[nd.name] = (nd.line, nd.col)

    def validate_newtype_targets(self):
        for name, target in self.newtype_targets.items():
            if not self.valid_type(target):
                line, col = self.newtype_lines[name]
                raise ForgeError(f"newtype '{name}' targets unknown "
                                 f"type '{target}'", line, col)

    def collect_aliases(self):
        """Collect `type` aliases and resolve their targets (v1).

        Aliases are transparent shorthands: `type UserId = int`
        means UserId IS int everywhere. Chains resolve here, once,
        so later expansion is shallow. Cycles, collisions with
        existing type names, and bare-generic targets are errors.
        """
        raw = {}
        for ad in (getattr(self.program, "aliases", None) or []):
            if ad.name in raw:
                raise ForgeError(f"duplicate type alias '{ad.name}'",
                                 ad.line, ad.col)
            raw[ad.name] = ad
        struct_names = {sd.name for sd in
                        (getattr(self.program, "structs", None) or [])}
        enum_names = {ed.name for ed in
                      (getattr(self.program, "enums", None) or [])}
        generic_names = {}
        for sd in (getattr(self.program, "structs", None) or []):
            if getattr(sd, "type_params", None):
                generic_names[sd.name] = "struct"
        for ed in (getattr(self.program, "enums", None) or []):
            if getattr(ed, "type_params", None):
                generic_names[ed.name] = "enum"
        for name, ad in raw.items():
            if name in SCALARS:
                raise ForgeError(f"type alias '{name}' collides with the "
                                 f"built-in type '{name}'", ad.line, ad.col)
            if name in struct_names or name in enum_names:
                raise ForgeError(f"type alias '{name}' collides with an "
                                 f"existing type of the same name",
                                 ad.line, ad.col)
            if ad.target in generic_names:
                kind = generic_names[ad.target]
                raise ForgeError(f"type alias '{name}' cannot target "
                                 f"generic {kind} '{ad.target}' without "
                                 f"type arguments; write {ad.target}<...>",
                                 ad.line, ad.col)
        self.aliases = {}
        self.alias_lines = {}
        for name, ad in raw.items():
            self.aliases[name] = self._resolve_alias(ad.target, raw, {name}, ad)
            self.alias_lines[name] = (ad.line, ad.col)

    def _resolve_alias(self, target, raw, seen, ad):
        if target in raw:
            if target in seen:
                raise ForgeError(f"cyclic type alias involving '{target}'",
                                 ad.line, ad.col)
            return self._resolve_alias(raw[target].target, raw,
                                       seen | {target}, ad)
        if target.startswith("[") and target.endswith("]"):
            return "[" + self._resolve_alias(target[1:-1], raw, seen, ad) + "]"
        g = parse_generic(target)
        if g is not None:
            base, args = g
            if base in raw:
                raise ForgeError(f"type alias '{base}' takes no type "
                                 f"arguments", ad.line, ad.col)
            return base + "<" + ", ".join(
                self._resolve_alias(a, raw, seen, ad) for a in args) + ">"
        return target

    def validate_alias_targets(self):
        # After struct/enum tables exist: every resolved target must
        # name a real type, even if no code ever uses the alias.
        for name, target in (getattr(self, "aliases", None) or {}).items():
            if not self.valid_type(target):
                line, col = self.alias_lines[name]
                raise ForgeError(f"type alias '{name}' targets unknown "
                                 f"type '{target}'", line, col)

    def expand_aliases(self):
        """Rewrite every type spelling in the program through aliases.

        Runs before any other checking, so every later pass sees
        only concrete types. Type spellings live in a small set of
        positions (function signatures, struct fields, enum
        payloads, trait signatures, let annotations, cast targets,
        struct literal names); everything else is reached by
        generic recursion into blocks and expressions.
        """
        aliases = getattr(self, "aliases", None) or {}
        if not aliases:
            return

        def expand(t):
            if t in aliases:
                return aliases[t]
            from .tuples import is_tuple_type, tuple_elems
            if is_tuple_type(t):
                return "(" + ", ".join(expand(e) for e in tuple_elems(t)) + ")"
            from .sizedarrays import is_sized_array, sized_elem, sized_len
            if is_sized_array(t):
                # Sized arrays need their own branch: the plain
                # "[...]" branch below would try to expand "N; 3"
                # as one name, so an alias element survived
                # unexpanded (the batch-12 gap: "[N; 3]" reached
                # struct checking as an unknown field type). The
                # length is a literal int in v1, kept as-is.
                return (f"[{expand(sized_elem(t).strip())}; "
                        f"{sized_len(t)}]")
            if t.startswith("[") and t.endswith("]"):
                return "[" + expand(t[1:-1]) + "]"
            g = parse_generic(t)
            if g is not None:
                base, args = g
                if base in aliases:
                    raise ForgeError(f"type alias '{base}' takes no type "
                                     f"arguments")
                return base + "<" + ", ".join(expand(a) for a in args) + ">"
            return t

        def walk(node):
            if node is None or isinstance(node, (str, int, float, bool)):
                return
            if isinstance(node, (list, tuple)):
                for x in node:
                    walk(x)
                return
            if isinstance(node, A.FuncDef):
                node.params = [(n, expand(t)) for n, t in node.params]
                node.ret = expand(node.ret)
            elif isinstance(node, A.StructDef):
                node.fields = [(n, expand(t)) for n, t in node.fields]
            elif isinstance(node, A.EnumDef):
                payloads = getattr(node, "variant_payloads", None) or {}
                for v, pt in list(payloads.items()):
                    if pt is not None:
                        payloads[v] = expand(pt)
            elif isinstance(node, A.TraitDef):
                node.methods = [(mn, [(pn, expand(pt)) for pn, pt in ps],
                                 expand(rt), ml, mc)
                                for (mn, ps, rt, ml, mc) in node.methods]
            elif isinstance(node, A.Let):
                if node.ann is not None:
                    node.ann = expand(node.ann)
            elif isinstance(node, A.Cast):
                node.target = expand(node.target)
            elif isinstance(node, A.NewtypeDef):
                node.target = expand(node.target)
            elif isinstance(node, A.StructLit):
                target = aliases.get(node.name)
                if (target is not None and "<" not in target
                        and "[" not in target):
                    node.name = target
            if hasattr(node, "__dict__"):
                for v in vars(node).values():
                    walk(v)

        for decls in (self.program.funcs,
                      getattr(self.program, "structs", None) or [],
                      getattr(self.program, "enums", None) or [],
                      getattr(self.program, "traits", None) or [],
                      getattr(self.program, "impls", None) or [],
                      getattr(self.program, "newtypes", None) or []):
            for d in decls:
                walk(d)
        # The walk rewrote newtype targets in place; refresh the
        # map so it never holds a pre-expansion (alias) spelling.
        if hasattr(self, "newtype_targets"):
            for nd in (getattr(self.program, "newtypes", None) or []):
                self.newtype_targets[nd.name] = nd.target

    def check_traits(self):
        """Validate trait declarations and impl blocks (v1).

        A trait is a contract: method signatures with no bodies. An
        impl block supplies the methods for one struct, each with
        the receiver as its first parameter; a trait impl must
        implement every trait method with matching parameter types
        (after the receiver) and return type. Extra methods are
        allowed. Impl methods are then appended to program.funcs
        under mangled names (Struct__method) so their bodies get
        checked and infer/codegen see them as ordinary functions,
        exactly like generic instantiations.
        """
        from .traits import mangle
        traits = {}
        for td in (getattr(self.program, "traits", None) or []):
            if td.name in traits:
                raise ForgeError(f"duplicate trait '{td.name}'", td.line, td.col)
            sigs = {}
            for (mname, params, ret, ml, mc) in td.methods:
                if mname in sigs:
                    raise ForgeError(f"duplicate method '{mname}' in trait "
                                     f"'{td.name}'", ml, mc)
                for (_pn, pt) in params:
                    if not self.valid_type(pt):
                        raise ForgeError(f"unknown type '{pt}' in trait "
                                         f"'{td.name}' method '{mname}'",
                                         ml, mc)
                if ret != "void" and not self.valid_type(ret):
                    raise ForgeError(f"unknown return type '{ret}' in trait "
                                     f"'{td.name}' method '{mname}'", ml, mc)
                sigs[mname] = (params, ret)
            traits[td.name] = sigs
        # Trait signatures, for method calls on opaque receivers
        # (which resolve against the trait, not a concrete struct).
        self.trait_sigs = traits
        struct_params = {}
        for sd in (getattr(self.program, "structs", None) or []):
            struct_params[sd.name] = getattr(sd, "type_params", None) or []
        free_names = {fn.name for fn in self.program.funcs}
        # struct -> {method: (params after receiver, ret)} for calls.
        self.method_types = {}
        seen_trait_impls = set()
        impls = getattr(self.program, "impls", None) or []
        for idf in impls:
            if idf.struct not in struct_params:
                raise ForgeError(f"impl targets unknown struct '{idf.struct}'",
                                 idf.line, idf.col)
            if struct_params[idf.struct]:
                raise ForgeError("generic structs cannot have impl blocks "
                                 "in traits v1", idf.line, idf.col)
            if idf.trait is not None:
                if idf.trait not in traits:
                    raise ForgeError(f"impl names unknown trait '{idf.trait}'",
                                     idf.line, idf.col)
                if (idf.trait, idf.struct) in seen_trait_impls:
                    raise ForgeError(f"duplicate impl of trait '{idf.trait}' "
                                     f"for '{idf.struct}'", idf.line, idf.col)
                seen_trait_impls.add((idf.trait, idf.struct))
            methods = self.method_types.setdefault(idf.struct, {})
            for m in idf.methods:
                if m.name in methods:
                    raise ForgeError(f"duplicate method '{m.name}' for "
                                     f"struct '{idf.struct}'", m.line, m.col)
                if not m.params or m.params[0][1] != idf.struct:
                    raise ForgeError(f"first parameter of method '{m.name}' "
                                     f"must be the struct '{idf.struct}'",
                                     m.line, m.col)
                if m.name == "drop":
                    # Destructor hook (Top-500 #33): the hook is a
                    # plain method the native backend calls when an
                    # owned binding dies, so it must take only its
                    # struct as receiver and return nothing. In
                    # freestanding mode scope-end frees do not run,
                    # so a hook would silently never fire — reject.
                    if len(m.params) != 1:
                        raise ForgeError("drop must take only its struct "
                                         "as receiver", m.line, m.col)
                    if m.ret != "void":
                        raise ForgeError("drop must return void",
                                         m.line, m.col)
                    if self.freestanding:
                        raise ForgeError("drop is not supported in "
                                         "freestanding v1 (scope-end frees "
                                         "do not run there)",
                                         m.line, m.col)
                if mangle(idf.struct, m.name) in free_names:
                    raise ForgeError(f"method '{m.name}' on '{idf.struct}' "
                                     f"collides with an existing function "
                                     f"'{mangle(idf.struct, m.name)}'",
                                     m.line, m.col)
                methods[m.name] = (m.params[1:], m.ret)
            if idf.trait is not None:
                for tname, (tparams, tret) in traits[idf.trait].items():
                    if tname not in methods:
                        raise ForgeError(f"impl of trait '{idf.trait}' for "
                                         f"'{idf.struct}' is missing method "
                                         f"'{tname}'", idf.line, idf.col)
                    iparams, iret = methods[tname]
                    if ([t for (_n, t) in iparams] !=
                            [t for (_n, t) in tparams] or iret != tret):
                        raise ForgeError(
                            f"method '{tname}' in impl of trait "
                            f"'{idf.trait}' for '{idf.struct}' does not "
                            f"match the trait signature", idf.line, idf.col)
        for idf in impls:
            for m in idf.methods:
                spec = copy.deepcopy(m)
                spec.name = mangle(idf.struct, m.name)
                self.program.funcs.append(spec)

    def check_method_call(self, call):
        rt = self.check_expr(call.base)
        if rt == "range":
            # Built-in range methods: len, contains, start, end, sum.
            # A range is lazy (start/end only, no array), so these
            # are all O(1); sum uses the arithmetic-series formula.
            methods = {"len": ([], "int"), "contains": (["int"], "bool"),
                       "start": ([], "int"), "end": ([], "int"),
                       "sum": ([], "int")}
            if call.method not in methods:
                raise ForgeError(f"range has no method '{call.method}'",
                                 call.line, call.col)
            params, ret = methods[call.method]
            if len(call.args) != len(params):
                raise ForgeError(f"method '{call.method}' on 'range' takes "
                                 f"{len(params)} arguments, got {len(call.args)}",
                                 call.line, call.col)
            for arg, pt in zip(call.args, params):
                at = self.check_expr(arg)
                if at != pt:
                    raise ForgeError(f"method '{call.method}' on 'range' expects "
                                     f"{pt}, got {at}", call.line, call.col)
            return ret
        if is_opaque_type(rt):
            # An opaque receiver resolves against the trait, not a
            # concrete struct: the implementation stays hidden.
            trait = opaque_trait(rt)
            sigs = getattr(self, "trait_sigs", {}).get(trait)
            if sigs is None:
                raise ForgeError(f"no methods on type '{rt}' (unknown trait "
                                 f"'{trait}')", call.line, call.col)
            if call.method not in sigs:
                raise ForgeError(f"trait '{trait}' has no method '{call.method}'",
                                 call.line, call.col)
            params, ret = sigs[call.method]
            if len(call.args) != len(params):
                raise ForgeError(f"method '{call.method}' on '{rt}' takes "
                                 f"{len(params)} arguments, got {len(call.args)}",
                                 call.line, call.col)
            for arg, (_pn, pt) in zip(call.args, params):
                at = self.check_expr(arg)
                if not self.accepts(at, pt, arg):
                    raise ForgeError(f"method '{call.method}' on '{rt}' expects "
                                     f"{pt}, got {at}", call.line, call.col)
            return ret
        if "<" in rt or rt not in self.method_types:
            raise ForgeError(f"no methods on type '{rt}' (trait methods "
                             f"need a struct with an impl block)",
                             call.line, call.col)
        methods = self.method_types[rt]
        if call.method not in methods:
            raise ForgeError(f"struct '{rt}' has no method '{call.method}'",
                             call.line, call.col)
        params, ret = methods[call.method]
        if len(call.args) != len(params):
            raise ForgeError(f"method '{call.method}' on '{rt}' takes "
                             f"{len(params)} arguments, got {len(call.args)}",
                             call.line, call.col)
        for arg, (_pn, pt) in zip(call.args, params):
            at = self.check_expr(arg)
            if not self.accepts(at, pt, arg):
                raise ForgeError(f"method '{call.method}' on '{rt}' expects "
                                 f"{pt}, got {at}", call.line, call.col)
        return ret

    def collect_impls(self):
        """Trait names and impl-block order, before any validation.

        valid_type needs them (an opaque type requires a trait with
        at least one implementation), and it runs during
        check_structs, which precedes check_traits.
        """
        self.trait_names = set()
        for td in (getattr(self.program, "traits", None) or []):
            self.trait_names.add(td.name)
        self.trait_impls = {}
        for idf in (getattr(self.program, "impls", None) or []):
            if getattr(idf, "trait", None) is not None:
                impls = self.trait_impls.setdefault(idf.trait, [])
                if idf.struct not in impls:
                    impls.append(idf.struct)

    def accepts(self, value, expected, expr=None):
        """Value type accepted where an expected type is declared.

        Exact equality, a union member for its union, or a struct
        implementing the trait of an opaque type. A union value is
        never accepted for a single member, and an opaque value is
        never accepted for a concrete struct (the concrete type
        stays hidden). An integer literal adapts to an expected
        fixed-width type when it fits; a general int expression
        does not adapt.
        """
        if type_matches(value, expected):
            return True
        if value == "never":
            # Bottom type: a diverging expression stands in for
            # any expected type (the code after it never runs).
            return True
        if is_opaque_type(expected):
            trait = opaque_trait(expected)
            return value in getattr(self, "trait_impls", {}).get(trait, [])
        if is_readonly(expected):
            # A mutable array coerces to a readonly view of the
            # same array kind (dynamic to dynamic, sized to the
            # same sized type); a view never coerces back, and
            # kinds never mix.
            return value == expected or value == readonly_inner(expected)
        if expr is not None and is_fixed_int(expected):
            v = literal_value(expr)
            if v is not None:
                lo, hi = fixed_range(expected)
                return lo <= v <= hi
        # Empty-literal holes (Top-500 fix track): a value type
        # carrying `[?]` holes matches the expected type where
        # every hole sits in a dynamic-array/tuple position.
        if value != "?" and matches_up_to_unknown(value, expected):
            return True
        return False

    def _expr_diverges(self, e):
        """True when evaluating e necessarily diverges: it
        contains a fail call or a call to a never function.
        Only the expression itself is walked, never nested
        statement bodies (those are conditional)."""
        if e is None:
            return False
        if isinstance(e, A.Call):
            if e.name == "fail":
                return True
            fn = self.funcs.get(e.name)
            if fn is not None and fn.ret == "never":
                return True
        for v in vars(e).values():
            if isinstance(v, list):
                for item in v:
                    if hasattr(item, "__dict__") and self._expr_diverges(item):
                        return True
            elif hasattr(v, "__dict__") and self._expr_diverges(v):
                return True
        return False

    def _stmt_diverges(self, stmt):
        """True when a top-level statement necessarily diverges.

        Blocks and scopes recurse (they run unconditionally);
        if/while/for/match count only through their conditions
        and scrutinees (evaluated unconditionally), never their
        bodies (control can skip those). Returns are not
        divergers here: they are exits, handled by the return
        rule, and are rejected outright inside never functions.
        """
        if isinstance(stmt, A.Block):
            return any(self._stmt_diverges(s) for s in stmt.stmts)
        if isinstance(stmt, A.Scope):
            return self._stmt_diverges(stmt.body)
        if isinstance(stmt, A.If):
            return self._expr_diverges(stmt.cond)
        if isinstance(stmt, A.While):
            return self._expr_diverges(stmt.cond)
        if isinstance(stmt, A.For):
            return self._expr_diverges(stmt.expr)
        if isinstance(stmt, A.Match):
            return self._expr_diverges(stmt.expr)
        if isinstance(stmt, A.Return):
            return False
        for v in vars(stmt).values():
            if isinstance(v, list):
                for item in v:
                    if hasattr(item, "__dict__") and self._expr_diverges(item):
                        return True
            elif hasattr(v, "__dict__") and self._expr_diverges(v):
                return True
        return False

    def _body_diverges(self, body):
        """True when a function body cannot fall off its end:
        some top-level statement necessarily diverges."""
        return any(self._stmt_diverges(s) for s in body.stmts)

    def _has_return(self, node):
        """True when a return statement appears anywhere under
        node (including nested blocks and branches)."""
        if isinstance(node, A.Return):
            return True
        for v in vars(node).values():
            if isinstance(v, list):
                for item in v:
                    if hasattr(item, "__dict__") and self._has_return(item):
                        return True
            elif hasattr(v, "__dict__") and self._has_return(v):
                return True
        return False

    def _literal_fit_msg(self, expr, expected):
        """Specific error when a literal does not fit an expected
        fixed type, or None (the caller falls back to its generic
        mismatch message)."""
        if is_fixed_int(expected):
            v = literal_value(expr)
            if v is not None:
                lo, hi = fixed_range(expected)
                if not (lo <= v <= hi):
                    return f"integer literal {v} does not fit in {expected}"
        return None

    def _sized_literal_ok(self, expr, expected):
        """True when expr is an array literal matching a sized
        annotation at any depth.

        A length mismatch at any sized level raises its own
        precise error (the generic mismatch message would hide
        the count); an element-type mismatch returns False so
        the caller reports its generic message. Non-literals
        and expectations with no sized array anywhere return
        False without raising. Recursion handles nested sized
        literals (`[[1, 2], [3, 4]]` against `[[int; 2]; 2]`)
        and sized literals nested under a dynamic array
        (`[[1, 2]]` against `[[int; 2]]`): without it the inner
        literal checks as dynamic `[int]` and the whole literal
        is rejected. Non-literal elements (variables of a sized
        type) still go through `accepts`.
        """
        from .sizedarrays import (contains_sized, is_sized_array,
                                  sized_elem, sized_len)
        if not isinstance(expr, A.ArrayLit):
            return False
        if is_sized_array(expected):
            elem, n = sized_elem(expected), sized_len(expected)
            if len(expr.elems) != n:
                raise ForgeError(f"sized array {expected} needs {n} elements, "
                                 f"got {len(expr.elems)}", expr.line, expr.col)
        elif (isinstance(expected, str) and expected.startswith("[")
              and expected.endswith("]") and contains_sized(expected[1:-1])):
            elem = expected[1:-1]
        else:
            return False
        for e in expr.elems:
            if (isinstance(e, A.ArrayLit) and isinstance(elem, str)
                    and elem.startswith("[") and elem.endswith("]")):
                if not self._sized_literal_ok(e, elem):
                    return False
            elif not self.accepts(self.check_expr(e), elem, e):
                return False
        return True

    def check(self, require_main=True):
        self.collect_aliases()
        self.collect_newtypes()
        self.collect_impls()
        self.expand_aliases()
        self.check_structs()
        self.check_enums()
        self.validate_alias_targets()
        self.validate_newtype_targets()
        self.check_traits()
        original_funcs = list(self.program.funcs)
        for fn in original_funcs:
            if fn.name in self.funcs:
                raise ForgeError(f"duplicate function '{fn.name}'", fn.line, fn.col)
            if fn.name in BUILTINS:
                raise ForgeError(f"'{fn.name}' is a builtin and cannot be redefined", fn.line, fn.col)
            self.funcs[fn.name] = fn
        if require_main and "main" not in self.funcs:
            raise ForgeError("a Forge program must define fn main()")
        if "main" in self.funcs:
            main = self.funcs["main"]
            if main.params:
                raise ForgeError("fn main() must take no arguments", main.line, main.col)
            if main.ret not in ("int", "void"):
                raise ForgeError("fn main() must return int or nothing", main.line, main.col)
        for fn in original_funcs:
            self.check_func(fn)
        # Append every generic instantiation found during checking, so
        # infer/codegen see them as ordinary concrete functions/structs.
        for inst in self.func_instantiations.values():
            if inst not in self.program.funcs:
                self.program.funcs.append(inst)
        for ctype, fields in self.struct_instantiations.items():
            from . import ast_nodes as _A
            self.program.structs.append(
                _A.StructDef(mangle_type(ctype), list(fields.items()), 0, 0))
        return self.program

    def instantiate_func(self, fn, bindings, call_line, call_col):
        """Check a concrete copy of a generic function; return it."""
        key = (fn.name, tuple(bindings[p] for p in (fn.type_params or [])))
        if key in self.func_instantiations:
            return self.func_instantiations[key]
        if key in self._instantiating:
            # Recursive call with the same instantiation: the copy is
            # being checked; its return type is already known.
            return None
        mangled = fn.name + "_" + "_".join(mangle_type(bindings[p]) for p in (fn.type_params or []))
        spec = copy.deepcopy(fn)
        spec.name = mangled
        spec.type_params = []
        spec.params = [(n, substitute_type(t, bindings)) for n, t in fn.params]
        spec.ret = substitute_type(fn.ret, bindings)
        self._substitute_let_ann(spec.body, bindings)
        self.func_instantiations[key] = spec
        self._instantiating.add(key)
        try:
            self.check_func(spec)
        finally:
            self._instantiating.discard(key)
        return spec

    def _substitute_let_ann(self, block, bindings):
        for stmt in block.stmts:
            if isinstance(stmt, A.Let) and stmt.ann:
                stmt.ann = substitute_type(stmt.ann, bindings)
            elif isinstance(stmt, A.Block):
                self._substitute_let_ann(stmt, bindings)
            elif isinstance(stmt, A.Scope):
                self._substitute_let_ann(stmt.body, bindings)
            elif isinstance(stmt, A.If):
                self._substitute_let_ann(stmt.then, bindings)
                if stmt.els is not None:
                    self._substitute_let_ann(stmt.els, bindings)
            elif isinstance(stmt, A.While):
                self._substitute_let_ann(stmt.body, bindings)
            elif isinstance(stmt, A.For):
                self._substitute_let_ann(stmt.body, bindings)
            elif isinstance(stmt, A.Match):
                for _pat, _bind, body in stmt.arms:
                    self._substitute_let_ann(body, bindings)

    def check_func(self, fn):
        # Save outer state: checking a generic instantiation can happen
        # in the middle of checking another function (a call site), and
        # must not wipe that function's scopes/return type.
        saved = (self.scopes, self.current_ret, self.current_fn, self.current_type_params,
                 self.loop_depth, self.branch_depth, self.moved, self.unresolved,
                 self.moved_fields, self.loop_vars, self.pinned)
        try:
            if fn.name in C_KEYWORDS:
                raise ForgeError(f"'{fn.name}' is a C keyword and cannot be used as a "
                                 f"function name; rename it", fn.line, fn.col)
            self.current_type_params = list(getattr(fn, "type_params", None) or [])
            self.loop_depth = 0
            self.branch_depth = 0
            self.moved = set()
            self.moved_fields = set()
            self.pinned = set()
            self.loop_vars = []
            for pn, pt in fn.params:
                if pn in C_KEYWORDS:
                    raise ForgeError(f"'{pn}' is a C keyword and cannot be used as a "
                                     f"parameter name; rename it", fn.line, fn.col)
                if not self.valid_type(pt) or pt == "void":
                    raise ForgeError(f"parameter type '{pt}' is not a value type", fn.line, fn.col)
            if fn.ret != "void" and not self.valid_type(fn.ret):
                raise ForgeError(f"unknown return type '{fn.ret}'"
                                 f"{suggest(fn.ret, list(SCALARS) + list(self.structs) + list(self.enums))}",
                                 fn.line, fn.col)
            if getattr(fn, "is_extern", False):
                # No body to check; the C function must exist at link time.
                if self.freestanding:
                    raise ForgeError(f"extern fn '{fn.name}' needs link-time C symbols "
                                     f"(not in freestanding v1)",
                                     fn.line, fn.col)
                return
            if self.current_type_params:
                # Generic template: body is checked only on instantiation,
                # when every type parameter is concrete.
                return
            self.current_ret = fn.ret
            self.current_fn = fn
            self.scopes = [{n: (t, False) for n, t in fn.params}]
            self.unresolved = {}
            self.check_block(fn.body)
            if self.unresolved:
                # An empty array literal no use in this function
                # constrained: inference found no element type.
                let = next(iter(self.unresolved.values()))
                raise ForgeError("cannot infer the element type of an empty array "
                                 "literal; add an annotation, e.g. "
                                 "let x: [int] = []",
                                 let.line, let.col)
            if fn.ret == "never":
                if self._has_return(fn.body):
                    raise ForgeError(f"never function '{fn.name}' cannot return; "
                                     f"its body must diverge instead",
                                     fn.line, fn.col)
                if not self._body_diverges(fn.body):
                    raise ForgeError(f"never function '{fn.name}' must end with a "
                                     f"diverging statement (fail or a call to a never "
                                     f"function); its body can fall off the end",
                                     fn.line, fn.col)
            elif fn.ret != "void":
                if not fn.body.stmts or not isinstance(fn.body.stmts[-1], A.Return):
                    if not self._body_diverges(fn.body):
                        raise ForgeError(f"function '{fn.name}' returns {fn.ret} but its body "
                                         f"does not end with a return; add a return statement "
                                         f"of type {fn.ret} at the end of the function",
                                         fn.line, fn.col)
        finally:
            self.scopes, self.current_ret, self.current_fn, self.current_type_params, \
                self.loop_depth, self.branch_depth, self.moved, self.unresolved, \
                self.moved_fields, self.loop_vars, self.pinned = saved

    def lookup(self, name, line, col):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        if name in self.enum_variants:
            return (self.enum_variants[name], False)
        candidates = [n for scope in self.scopes for n in scope]
        candidates += list(self.enum_variants)
        raise ForgeError(f"undefined variable '{name}'{suggest(name, candidates)}",
                         line, col)

    def check_block(self, block):
        self.scopes.append({})
        for stmt in block.stmts:
            self.check_stmt(stmt)
        self.scopes.pop()

    def _field_path(self, expr):
        """Dotted path for a field access rooted at a variable
        ('s.vals', 's.inner.arr'), or None for any other base."""
        parts = []
        node = expr
        while isinstance(node, A.FieldAccess):
            parts.append(node.field)
            node = node.base
        if not isinstance(node, A.Var):
            return None
        parts.append(node.name)
        return ".".join(reversed(parts))

    def _join_moved(self, before_moved, before_fields, before_pinned, results):
        """Path-sensitive join for branches and loops (move v2):
        a variable is moved after the join when it is moved on
        ANY path (a use after a conditional move is unsafe on
        the path that moved it, so the checker rejects it).
        Pinning joins the same way (pin v1): a binding pinned
        on ANY path counts as pinned after the join, so a
        later move or copy is rejected on every path.
        Names declared only inside a branch are filtered out:
        they are out of scope after the join, and must not
        poison a later redeclaration of the same name."""
        visible = set()
        for scope in self.scopes:
            visible.update(scope.keys())
        moved = set(before_moved)
        fields = set(before_fields)
        pinned = set(before_pinned)
        for mset, fset, pset in results:
            for name in mset:
                if name in visible:
                    moved.add(name)
            for path in fset:
                if path.split(".")[0] in visible:
                    fields.add(path)
            for name in pset:
                if name in visible:
                    pinned.add(name)
        return moved, fields, pinned

    def _access_root(self, expr):
        """Root variable name of a Var/FieldAccess/Index/
        TupleIndex access chain, or None for any other base
        (a call result, a literal)."""
        node = expr
        while isinstance(node, (A.FieldAccess, A.Index, A.TupleIndex)):
            node = node.base
        return node.name if isinstance(node, A.Var) else None

    def _is_owned_type(self, t):
        """The move predicate (Top-500 #27): the types whose
        values carry a hold — arrays, str, structs, tuples.
        Pin reuses it: reading such a leaf out of a pinned
        binding would copy the hold."""
        return (elem_type(t) is not None or t == "str" or is_tuple_type(t)
                or t in self.structs or t in self.struct_instantiations)

    def _check_observed(self, expr):
        """check_expr for a read-only observation of a value
        (len, refcount, for-iteration over a pinned array):
        a direct access path on a pinned binding is allowed
        here — observing it moves or copies nothing — while
        any other use still goes through the pinned check.
        A call or literal argument is checked normally, so a
        pinned value hidden inside it is still rejected."""
        if isinstance(expr, (A.Var, A.FieldAccess, A.Index, A.TupleIndex)):
            self._pinned_observe += 1
            try:
                return self.check_expr(expr)
            finally:
                self._pinned_observe -= 1
        return self.check_expr(expr)

    def check_stmt(self, stmt):
        if isinstance(stmt, A.Block):
            self.check_block(stmt)
            return
        if isinstance(stmt, A.Let):
            if stmt.name in C_KEYWORDS:
                raise ForgeError(f"'{stmt.name}' is a C keyword and cannot be used as a "
                                 f"variable name; rename it", stmt.line, stmt.col)
            if stmt.name in self.scopes[-1]:
                raise ForgeError(f"variable '{stmt.name}' is already defined in this scope",
                                 stmt.line, stmt.col)
            t = self.check_expr(stmt.expr)
            if stmt.ann is None:
                # void is no value: it is allowed only as a
                # function or method return type. Binding it (or
                # a composite containing it) would compile to
                # invalid C downstream, so fail here instead.
                if t == "void":
                    if isinstance(stmt.expr, A.Call):
                        raise ForgeError(f"function '{stmt.expr.name}' returns void and has "
                                         f"no value to bind; call it as a statement instead",
                                         stmt.line, stmt.col)
                    if isinstance(stmt.expr, A.MethodCall):
                        raise ForgeError(f"method '{stmt.expr.method}' returns void and has "
                                         f"no value to bind; call it as a statement instead",
                                         stmt.line, stmt.col)
                    raise ForgeError("void has no value to bind",
                                     stmt.line, stmt.col)
                if "?" not in t and not self.valid_type(t):
                    raise ForgeError(f"type '{t}' contains void, which has no value",
                                     stmt.line, stmt.col)
            if stmt.ann is not None:
                if (isinstance(stmt.expr, A.Var)
                        and self._resolve_empty(stmt.expr.name, stmt.ann)):
                    # An annotated let constrains an unresolved
                    # array value to the annotation's type.
                    t = stmt.ann
                if not self.valid_type(stmt.ann) or stmt.ann == "void":
                    raise ForgeError(f"unknown type '{stmt.ann}'"
                                     f"{suggest(stmt.ann, list(SCALARS) + list(self.structs) + list(self.enums))}",
                                     stmt.line, stmt.col)
                # Fill a generic-enum placeholder from the annotation.
                filled = self.fill_placeholder(t, stmt.ann)
                if filled != t:
                    if isinstance(stmt.expr, A.Call):
                        stmt.expr.concrete_type = filled
                    t = filled
                elif isinstance(stmt.expr, A.Var) and stmt.expr.name in self.enum_variants:
                    enum_name = self.enum_variants[stmt.expr.name]
                    if parse_generic(stmt.ann) and parse_generic(stmt.ann)[0] == enum_name:
                        t = stmt.ann
                if t != stmt.ann:
                    # Empty array literal has no element type of its own.
                    if (not (isinstance(stmt.expr, A.ArrayLit) and not stmt.expr.elems
                             and stmt.ann.startswith("[") and not (is_sized_array(stmt.ann) and sized_len(stmt.ann) > 0)) and not self.accepts(t, stmt.ann, stmt.expr)
                            and not self._sized_literal_ok(stmt.expr, stmt.ann)):
                        raise ForgeError(self._literal_fit_msg(stmt.expr, stmt.ann)
                                         or f"variable '{stmt.name}' is declared {stmt.ann} "
                                         f"but initialised with {t}{cast_hint(t, stmt.ann)}",
                                         stmt.line, stmt.col)
                    t = stmt.ann
            self.scopes[-1][stmt.name] = (t, stmt.mutable)
            # A fresh binding is never moved, even when it shadows
            # an outer variable that was moved (move v2).
            self.moved.discard(stmt.name)
            # A fresh binding is never pinned either (pin v1):
            # shadowing a pinned outer variable pins nothing.
            self.pinned.discard(stmt.name)
            self.moved_fields = {p for p in self.moved_fields
                                 if not p.startswith(stmt.name + ".")}
            if (isinstance(stmt.expr, A.ArrayLit) and not stmt.expr.elems
                    and stmt.ann is None):
                # Empty literal, no annotation: its element type is
                # unresolved until a constraining use resolves it
                # (or check_func reports it at the end of the body).
                self.unresolved[(id(self.scopes[-1]), stmt.name)] = stmt
            return
        if isinstance(stmt, A.Assign):
            vt, mutable = self.lookup(stmt.name, stmt.line, stmt.col)
            if not mutable:
                raise ForgeError(f"cannot assign to immutable variable '{stmt.name}' "
                                 f"(declare it with 'let mut')", stmt.line, stmt.col)
            if stmt.name in self.pinned:
                raise ForgeError(f"cannot reassign pinned variable '{stmt.name}' "
                                 f"(pin forbids replacing the value; change it "
                                 f"in place through its fields or indexes)",
                                 stmt.line, stmt.col)
            et = self.check_expr(stmt.expr)
            if self._resolve_empty(stmt.name, et):
                vt, _m = self.lookup(stmt.name, stmt.line, stmt.col)
            if not self.accepts(et, vt, stmt.expr) and not self._sized_literal_ok(stmt.expr, vt):
                if not (isinstance(stmt.expr, A.ArrayLit) and not stmt.expr.elems
                        and vt.startswith("[") and not (is_sized_array(vt) and sized_len(vt) > 0)):
                    raise ForgeError(self._literal_fit_msg(stmt.expr, vt)
                                     or f"cannot assign {et} to {vt} variable '{stmt.name}'"
                                     f"{cast_hint(et, vt)}",
                                     stmt.line, stmt.col)
            # Reassignment revives a moved variable: the new value
            # is fresh, so later uses (and scope-end frees) see it
            # as live again (move v2; codegen resets the flag too).
            self.moved.discard(stmt.name)
            self.moved_fields = {p for p in self.moved_fields
                                 if not p.startswith(stmt.name + ".")}
            return
        if isinstance(stmt, A.FieldAssign):
            # Outermost variable must be mutable; field type comes from
            # checking the target FieldAccess expression itself.
            node = stmt.target
            while isinstance(node, A.FieldAccess):
                node = node.base
            if not isinstance(node, A.Var):
                raise ForgeError("field assignment target must start from a variable",
                                 stmt.line, stmt.col)
            _vt, mutable = self.lookup(node.name, stmt.line, stmt.col)
            if not mutable:
                raise ForgeError(f"cannot assign to a field of immutable variable "
                                 f"'{node.name}' (declare it with 'let mut')",
                                 stmt.line, stmt.col)
            # Assigning a field revives it after a field move, so
            # the target check alone must not reject a moved field;
            # the value check below still rejects a moved field
            # used as the new value (move v2).
            target_path = self._field_path(stmt.target)
            self._moved_field_target = target_path
            # An in-place field write is not a use of the pinned
            # value: the struct stays put, only the field changes
            # (pin v1).
            self._pinned_write_root = node.name
            try:
                ft = self.check_expr(stmt.target)
            finally:
                self._moved_field_target = None
                self._pinned_write_root = None
            vt2 = self.check_expr(stmt.expr)
            if (isinstance(stmt.expr, A.Var)
                    and self._resolve_empty(stmt.expr.name, ft)):
                # Storing an unresolved array into a concretely typed
                # field resolves it to the field's type.
                vt2 = ft
            if vt2 != ft and not self._sized_literal_ok(stmt.expr, ft):
                raise ForgeError(f"cannot assign {vt2} to field of type {ft}"
                                 f"{cast_hint(vt2, ft)}",
                                 stmt.line, stmt.col)
            if target_path is not None:
                self.moved_fields.discard(target_path)
            return
        if isinstance(stmt, A.IndexAssign):
            base = stmt.base.base
            if isinstance(base, A.Var):
                vt, _mutable = self.lookup(base.name, stmt.line, stmt.col)
                et = elem_type(vt)
            elif isinstance(base, A.FieldAccess):
                # e.g. m.vals[i] = v — array contents, not a rebinding,
                # so mutability of the struct variable is not required.
                # An in-place index write into a pinned struct's
                # array field is not a use of the pinned value.
                self._pinned_write_root = self._access_root(base)
                try:
                    vt = self.check_expr(base)
                finally:
                    self._pinned_write_root = None
                et = elem_type(vt)
            elif isinstance(base, A.Index):
                # Chained index assignment (m[i][j] = v): the inner
                # index yields the array being assigned into.
                self._pinned_write_root = self._access_root(base)
                try:
                    vt = self.check_expr(base)
                finally:
                    self._pinned_write_root = None
                et = elem_type(vt)
            else:
                raise ForgeError("index assignment target must be a variable or a field",
                                 stmt.line, stmt.col)
            if is_readonly(vt):
                raise ForgeError(f"cannot assign through a readonly view {vt}",
                                 stmt.line, stmt.col)
            if vt == "str":
                raise ForgeError("cannot assign to a string index; strings are immutable",
                                 stmt.line, stmt.col)
            if et is None:
                raise ForgeError(f"cannot index a non-array value of type {vt}",
                                 stmt.line, stmt.col)
            it = self.check_expr(stmt.base.index)
            if it != "int":
                raise ForgeError("array index must be int", stmt.line, stmt.col)
            vt2 = self.check_expr(stmt.expr)
            if (isinstance(base, A.Var) and "?" not in vt2
                    and self._resolve_empty(base.name, f"[{vt2}]")):
                # Storing a concrete element through an unresolved
                # array resolves it to an array of that element type.
                et = vt2
            if vt2 != et:
                raise ForgeError(f"cannot assign {vt2} to element of type {et}"
                                 f"{cast_hint(vt2, et)}",
                                 stmt.line, stmt.col)
            return
        if isinstance(stmt, A.Match):
            et = self.check_expr(stmt.expr)
            match_before_moved, match_before_fields = set(self.moved), set(self.moved_fields)
            match_before_pinned = set(self.pinned)
            match_results = []
            if is_union_type(et):
                # Narrowing a union: arms are member types, each
                # binding the narrowed value; exhaustiveness is over
                # the members, or a trailing wildcard.
                members = union_members(et)
                member_set = set(members)
                seen = set()
                has_wildcard = False
                for idx, (pat, binding, body) in enumerate(stmt.arms):
                    if pat == "_":
                        has_wildcard = True
                        if idx != len(stmt.arms) - 1:
                            raise ForgeError("match wildcard '_' must be the last arm",
                                             stmt.line, stmt.col)
                        if binding is not None:
                            raise ForgeError("wildcard arm cannot bind a value",
                                             stmt.line, stmt.col)
                        self.moved, self.moved_fields, self.pinned = set(match_before_moved), set(match_before_fields), set(match_before_pinned)
                        self.branch_depth += 1
                        try:
                            self.check_block(body)
                        finally:
                            self.branch_depth -= 1
                        match_results.append((set(self.moved), set(self.moved_fields), set(self.pinned)))
                        continue
                    if pat not in member_set:
                        raise ForgeError(f"'{pat}' is not a member of union '{et}'",
                                         stmt.line, stmt.col)
                    if pat in seen:
                        raise ForgeError(f"duplicate match arm '{pat}'",
                                         stmt.line, stmt.col)
                    seen.add(pat)
                    if binding is None:
                        raise ForgeError(f"member '{pat}' has a value; "
                                         f"write {pat}(name) => ...",
                                         stmt.line, stmt.col)
                    self.moved, self.moved_fields, self.pinned = set(match_before_moved), set(match_before_fields), set(match_before_pinned)
                    self.scopes.append({binding: (pat, False)})
                    try:
                        self.branch_depth += 1
                        try:
                            self.check_block(body)
                        finally:
                            self.branch_depth -= 1
                    finally:
                        self.scopes.pop()
                    match_results.append((set(self.moved), set(self.moved_fields), set(self.pinned)))
                if not has_wildcard and seen != member_set:
                    missing = sorted(member_set - seen)
                    raise ForgeError(f"match is not exhaustive; missing: {', '.join(missing)}",
                                     stmt.line, stmt.col)
                self.moved, self.moved_fields, self.pinned = self._join_moved(
                    match_before_moved, match_before_fields, match_before_pinned, match_results)
                return
            info = self.enum_info_for(et)
            if info is None:
                raise ForgeError(f"match needs an enum value, got {et}",
                                 stmt.line, stmt.col)
            _base, variant_info = info
            variants = set(variant_info.keys())
            seen = set()
            has_wildcard = False
            for idx, (pat, binding, body) in enumerate(stmt.arms):
                if pat == "_":
                    has_wildcard = True
                    if idx != len(stmt.arms) - 1:
                        raise ForgeError("match wildcard '_' must be the last arm",
                                         stmt.line, stmt.col)
                    if binding is not None:
                        raise ForgeError("wildcard arm cannot bind a value", stmt.line, stmt.col)
                    self.moved, self.moved_fields, self.pinned = set(match_before_moved), set(match_before_fields), set(match_before_pinned)
                    self.branch_depth += 1
                    try:
                        self.check_block(body)
                    finally:
                        self.branch_depth -= 1
                    match_results.append((set(self.moved), set(self.moved_fields), set(self.pinned)))
                    continue
                if pat not in variants:
                    raise ForgeError(f"'{pat}' is not a variant of enum '{et}'"
                                     f"{suggest(pat, variants)}",
                                     stmt.line, stmt.col)
                if pat in seen:
                    raise ForgeError(f"duplicate match arm '{pat}'", stmt.line, stmt.col)
                seen.add(pat)
                _tag, payload_type = variant_info[pat]
                if payload_type is None and binding is not None:
                    raise ForgeError(f"variant '{pat}' has no payload to bind",
                                     stmt.line, stmt.col)
                if payload_type is not None and binding is None:
                    raise ForgeError(f"variant '{pat}' has a payload; write {pat}(name) => ...",
                                     stmt.line, stmt.col)
                if binding is not None:
                    # Check the arm body with the binding in scope.
                    self.moved, self.moved_fields, self.pinned = set(match_before_moved), set(match_before_fields), set(match_before_pinned)
                    self.scopes.append({binding: (payload_type, False)})
                    try:
                        self.branch_depth += 1
                        try:
                            self.check_block(body)
                        finally:
                            self.branch_depth -= 1
                    finally:
                        self.scopes.pop()
                else:
                    self.moved, self.moved_fields, self.pinned = set(match_before_moved), set(match_before_fields), set(match_before_pinned)
                    self.branch_depth += 1
                    try:
                        self.check_block(body)
                    finally:
                        self.branch_depth -= 1
                match_results.append((set(self.moved), set(self.moved_fields), set(self.pinned)))
            if not has_wildcard and seen != variants:
                missing = sorted(variants - seen)
                raise ForgeError(f"match is not exhaustive; missing: {', '.join(missing)}",
                                 stmt.line, stmt.col)
            self.moved, self.moved_fields, self.pinned = self._join_moved(
                match_before_moved, match_before_fields, match_before_pinned, match_results)
            return
        if isinstance(stmt, A.Spawn):
            if self.freestanding:
                raise ForgeError("spawn needs the hosted thread runtime "
                                 "(not in freestanding v1)",
                                 stmt.line, stmt.col)
            call = stmt.call
            fn = self.funcs.get(call.name)
            if fn is None:
                raise ForgeError(f"spawn: undefined function '{call.name}'"
                                 f"{suggest(call.name, self.funcs)}",
                                 stmt.line, stmt.col)
            if fn.ret != "void":
                raise ForgeError("spawn: function must return void", stmt.line, stmt.col)
            if len(call.args) > 1:
                raise ForgeError("spawn: function must take 0 or 1 int argument",
                                 stmt.line, stmt.col)
            if call.args and self.check_expr(call.args[0]) != "int":
                raise ForgeError("spawn: argument must be int", stmt.line, stmt.col)
            if len(fn.params) != len(call.args):
                raise ForgeError("spawn: argument count does not match function",
                                 stmt.line, stmt.col)
            return
        if isinstance(stmt, A.Scope):
            if self.freestanding:
                raise ForgeError("scope needs the hosted thread runtime "
                                 "(not in freestanding v1)",
                                 stmt.line, stmt.col)
            # The block's lets are scoped to it, like any block.
            self.check_block(stmt.body)
            return
        if isinstance(stmt, A.If):
            if self.check_expr(stmt.cond) != "bool":
                raise ForgeError("if condition must be bool", stmt.line, stmt.col)
            before_moved, before_fields = set(self.moved), set(self.moved_fields)
            before_pinned = set(self.pinned)
            self.branch_depth += 1
            try:
                self.check_block(stmt.then)
                then_moved, then_fields = set(self.moved), set(self.moved_fields)
                then_pinned = set(self.pinned)
                self.moved, self.moved_fields, self.pinned = before_moved, before_fields, before_pinned
                if stmt.els is not None:
                    self.check_block(stmt.els)
                    else_moved, else_fields = set(self.moved), set(self.moved_fields)
                    else_pinned = set(self.pinned)
                else:
                    else_moved, else_fields = before_moved, before_fields
                    else_pinned = before_pinned
            finally:
                self.branch_depth -= 1
            self.moved, self.moved_fields, self.pinned = self._join_moved(
                before_moved, before_fields, before_pinned,
                [(then_moved, then_fields, then_pinned),
                 (else_moved, else_fields, else_pinned)])
            return
        if isinstance(stmt, A.While):
            if self.check_expr(stmt.cond) != "bool":
                raise ForgeError("while condition must be bool", stmt.line, stmt.col)
            before_moved, before_fields = set(self.moved), set(self.moved_fields)
            before_pinned = set(self.pinned)
            self.loop_depth += 1
            try:
                self.check_block(stmt.body)
                body_moved, body_fields = set(self.moved), set(self.moved_fields)
                body_pinned = set(self.pinned)
            finally:
                self.loop_depth -= 1
            # The body may run zero times, so after the loop a
            # variable is moved only if it was already moved
            # before, or moved in the body (maybe-moved counts
            # as moved: a later use is unsafe on the path that
            # moved it). A second execution of a move in the
            # body is caught at runtime by the moved flag.
            # Pinning joins the same way: pinned in the body
            # counts as pinned after the loop.
            self.moved, self.moved_fields, self.pinned = self._join_moved(
                before_moved, before_fields, before_pinned,
                [(body_moved, body_fields, body_pinned)])
            return
        if isinstance(stmt, A.For):
            # Iterating a pinned array reads its elements without
            # moving the array itself (pin v1: a read-only
            # observation, like len).
            at = self._check_observed(stmt.expr)
            if at == "range":
                et = "int"
            else:
                et = elem_type(at)
            if et is None:
                raise ForgeError(f"for loop needs an array or range, got {at}", stmt.line, stmt.col)
            before_moved, before_fields = set(self.moved), set(self.moved_fields)
            before_pinned = set(self.pinned)
            self.scopes.append({stmt.name: (et, False)})
            self.loop_depth += 1
            self.loop_vars.append(stmt.name)
            try:
                for s in stmt.body.stmts:
                    self.check_stmt(s)
                body_moved, body_fields = set(self.moved), set(self.moved_fields)
                body_pinned = set(self.pinned)
            finally:
                self.loop_depth -= 1
                self.loop_vars.pop()
            self.scopes.pop()
            self.moved, self.moved_fields, self.pinned = self._join_moved(
                before_moved, before_fields, before_pinned,
                [(body_moved, body_fields, body_pinned)])
            return
        if isinstance(stmt, A.Break):
            if self.loop_depth == 0:
                raise ForgeError("break outside a loop; move it inside a "
                                 "'while' or 'for' loop", stmt.line, stmt.col)
            return
        if isinstance(stmt, A.Continue):
            if self.loop_depth == 0:
                raise ForgeError("continue outside a loop; move it inside "
                                 "a 'while' or 'for' loop", stmt.line, stmt.col)
            return
        if isinstance(stmt, A.Defer):
            # The deferred call is checked like an expression
            # statement; its value (if any) is discarded at exit.
            if not isinstance(stmt.call, (A.Call, A.MethodCall)):
                raise ForgeError("defer needs a call", stmt.line, stmt.col)
            self.check_expr(stmt.call)
            return
        if isinstance(stmt, A.Return):
            if self.current_ret == "void":
                if stmt.expr is not None:
                    raise ForgeError("void function cannot return a value; "
                                     "remove the value after 'return'",
                                     stmt.line, stmt.col)
            else:
                if stmt.expr is None:
                    raise ForgeError(f"function must return {self.current_ret}; "
                                     f"add a return statement of type "
                                     f"{self.current_ret} at the end of the "
                                     f"function", stmt.line, stmt.col)
                t = self.check_expr(stmt.expr)
                if (isinstance(stmt.expr, A.Var)
                        and self._resolve_empty(stmt.expr.name, self.current_ret)):
                    # Returning an unresolved array from a concretely
                    # typed function resolves it to the return type.
                    t = self.current_ret
                filled = self.fill_placeholder(t, self.current_ret)
                if filled != t:
                    if isinstance(stmt.expr, A.Call):
                        stmt.expr.concrete_type = filled
                    t = filled
                elif isinstance(stmt.expr, A.Var) and stmt.expr.name in self.enum_variants:
                    enum_name = self.enum_variants[stmt.expr.name]
                    if parse_generic(self.current_ret) and parse_generic(self.current_ret)[0] == enum_name:
                        t = self.current_ret
                if t != self.current_ret:
                    if not (isinstance(stmt.expr, A.ArrayLit) and not stmt.expr.elems
                            and self.current_ret.startswith("[") and not (is_sized_array(self.current_ret) and sized_len(self.current_ret) > 0)) \
                            and not self.accepts(t, self.current_ret, stmt.expr) \
                            and not self._sized_literal_ok(stmt.expr, self.current_ret):
                        raise ForgeError(self._literal_fit_msg(stmt.expr, self.current_ret)
                                         or f"return type is {t}, function returns "
                                         f"{self.current_ret}{cast_hint(t, self.current_ret)}",
                                         stmt.line, stmt.col)
            return
        if isinstance(stmt, A.ExprStmt):
            if not isinstance(stmt.expr, A.Call):
                raise ForgeError("an expression statement must be a function call",
                                 stmt.line, stmt.col)
            call = stmt.expr
            if call.name in STMT_BUILTINS:
                self.check_stmt_builtin(call)
                return
            if call.name in EXPR_BUILTINS:
                raise ForgeError(f"'{call.name}' is an expression, not a statement; "
                                 f"use its value", stmt.line, stmt.col)
            self.check_expr(call)
            return
        raise ForgeError(f"unsupported statement {type(stmt).__name__}", stmt.line, stmt.col)

    def check_stmt_builtin(self, call):
        if call.name == "assert":
            if len(call.args) != 2:
                raise ForgeError("assert() takes a bool condition and a str message",
                                 call.line, call.col)
            if self.check_expr(call.args[0]) != "bool":
                raise ForgeError("assert() condition must be bool", call.line, call.col)
            if self.check_expr(call.args[1]) != "str":
                raise ForgeError("assert() message must be str", call.line, call.col)
            return
        if call.name in ("print", "println"):
            if self.freestanding:
                raise ForgeError("print/println need the hosted I/O library "
                                 "(not in freestanding v1); use poke32 for MMIO output",
                                 call.line, call.col)
            for a in call.args:
                self.check_expr(a)
            return
        if call.name == "fail":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("fail() takes exactly one str argument", call.line, call.col)
            return
        if call.name == "mmap_set":
            if self.freestanding:
                raise ForgeError("mmap needs the hosted runtime (not in freestanding v1)",
                                 call.line, call.col)
            if len(call.args) != 3:
                raise ForgeError("mmap_set() takes a mapping id, an index, and a byte value",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "int":
                    raise ForgeError("mmap_set() arguments must be int", call.line, call.col)
            return
        if call.name == "mmap_set32":
            if self.freestanding:
                raise ForgeError("mmap needs the hosted runtime (not in freestanding v1)",
                                 call.line, call.col)
            if len(call.args) != 3:
                raise ForgeError("mmap_set32() takes a mapping id, a byte offset, and a word value",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "int":
                    raise ForgeError("mmap_set32() arguments must be int", call.line, call.col)
            return
        if call.name == "mmap_close":
            if self.freestanding:
                raise ForgeError("mmap needs the hosted runtime (not in freestanding v1)",
                                 call.line, call.col)
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError("mmap_close() takes a mapping id (int)", call.line, call.col)
            return
        if call.name == "push":
            if len(call.args) != 2 or not isinstance(call.args[0], (A.Var, A.FieldAccess)):
                raise ForgeError("push() takes a variable or field and a value", call.line, call.col)
            if isinstance(call.args[0], A.Var) and call.args[0].name in self.pinned:
                raise ForgeError(f"cannot push to pinned value '{call.args[0].name}' "
                                 f"(push can reallocate the buffer; grow it "
                                 f"before pinning, then write in place)",
                                 call.line, call.col)
            if isinstance(call.args[0], A.FieldAccess):
                _proot = self._access_root(call.args[0])
                if _proot in self.pinned:
                    raise ForgeError(f"cannot push to a field of pinned value '{_proot}' "
                                     f"(push can reallocate the buffer; grow it "
                                     f"before pinning, then write in place)",
                                     call.line, call.col)
            if isinstance(call.args[0], A.Var):
                vt, _m = self.lookup(call.args[0].name, call.line, call.col)
            else:
                vt = self.check_expr(call.args[0])
            et = elem_type(vt)
            if et is None:
                raise ForgeError(f"push() needs an array, got {vt}", call.line, call.col)
            from .sizedarrays import is_sized_array
            if is_sized_array(vt):
                raise ForgeError(f"cannot push to a sized array {vt} "
                                 f"(its length is fixed)", call.line, call.col)
            if is_readonly(vt):
                raise ForgeError(f"cannot push to a readonly view {vt}",
                                 call.line, call.col)
            vt2 = self.check_expr(call.args[1])
            if (isinstance(call.args[0], A.Var) and "?" not in vt2
                    and self._resolve_empty(call.args[0].name, f"[{vt2}]")):
                # Pushing a concrete value into an unresolved array
                # resolves it to an array of the value's type.
                et = vt2
            if vt2 != et:
                raise ForgeError(f"push() value must be {et}, got {vt2}", call.line, call.col)
            return
        if call.name == "pin":
            # Pinning (Top-500 #34): `pin(x);` marks an owned
            # binding immovable for the rest of its scope — no
            # move or copy after it, only in-place field/index
            # writes and scalar reads. Compile-time only: the
            # native codegen emits nothing for the statement.
            if len(call.args) != 1:
                raise ForgeError("pin() takes exactly one argument", call.line, call.col)
            arg = call.args[0]
            if not isinstance(arg, A.Var):
                raise ForgeError("pin needs a variable in v1; pin the whole binding, "
                                 "not a field", call.line, call.col)
            if arg.name in self.loop_vars:
                raise ForgeError("pin of a for-loop variable is not supported in v1; "
                                 "copy it into a let first, then pin that",
                                 call.line, call.col)
            if arg.name in self.moved:
                raise ForgeError(f"cannot pin moved value '{arg.name}'",
                                 call.line, call.col)
            if arg.name in self.pinned:
                raise ForgeError(f"'{arg.name}' is already pinned",
                                 call.line, call.col)
            t, _m = self.lookup(arg.name, call.line, call.col)
            if not self._is_owned_type(t):
                raise ForgeError(f"pin needs an owned value (array, str, struct, tuple), "
                                 f"got {t}", call.line, call.col)
            if t in self.method_types and "drop" in self.method_types[t]:
                raise ForgeError(f"cannot pin a value of struct '{t}' with a drop "
                                 f"method in v1 (the scope-end drop hook copies "
                                 f"the value)", call.line, call.col)
            self.pinned.add(arg.name)
            return
        if call.name == "poke32":
            if len(call.args) != 2:
                raise ForgeError("poke32() takes exactly two arguments",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "int":
                    raise ForgeError("poke32() takes int arguments",
                                     call.line, call.col)
            return
        if call.name in ("csr_write", "csr_set", "csr_clear"):
            if len(call.args) != 2 or not isinstance(call.args[0], A.IntLit):
                raise ForgeError(f"{call.name}() takes a literal CSR number "
                                 f"and an int value",
                                 call.line, call.col)
            if not 0 <= call.args[0].value <= 4095:
                raise ForgeError("CSR number must be in 0..4095",
                                 call.line, call.col)
            if self.check_expr(call.args[1]) != "int":
                raise ForgeError(f"{call.name}() value must be int",
                                 call.line, call.col)
            return
        raise ForgeError(f"unknown builtin '{call.name}'", call.line, call.col)

    def check_expr(self, expr):
        if isinstance(expr, A.IntLit):
            return "int"
        if isinstance(expr, A.FloatLit):
            return "float"
        if isinstance(expr, A.StrLit):
            return "str"
        if isinstance(expr, A.BoolLit):
            return "bool"
        if isinstance(expr, A.Var):
            if expr.name in self.moved:
                raise ForgeError(f"use of moved value '{expr.name}'", expr.line, expr.col)
            if (expr.name in self.pinned and self._in_pinned_base == 0
                    and self._pinned_write_root != expr.name
                    and self._pinned_observe == 0):
                # A whole-value use of a pinned binding would move
                # or copy it. Uses inside a field/index access are
                # decided by the outermost access (a scalar leaf
                # is a plain read; an owned leaf is a copy), and
                # in-place writes and read-only observations
                # (len, refcount, for-iteration) are exempt.
                raise ForgeError(f"use of pinned value '{expr.name}' "
                                 f"(pin forbids moving or copying it; "
                                 f"change it in place through its fields "
                                 f"or indexes)", expr.line, expr.col)
            if self._in_field_base == 0:
                # A whole-value use after a field move is unsafe
                # (a copy would re-own the moved field); field
                # accesses themselves go through the FieldAccess
                # branch, which skips this check while it walks
                # the base (move v2).
                moved_field = sorted(p for p in self.moved_fields
                                     if p.startswith(expr.name + "."))
                if moved_field:
                    raise ForgeError(f"use of value '{expr.name}' with moved field "
                                     f"'{moved_field[0]}'", expr.line, expr.col)
            return self.lookup(expr.name, expr.line, expr.col)[0]
        if isinstance(expr, A.ArrayLit):
            if not expr.elems:
                return "[?]"
            t0 = self.check_expr(expr.elems[0])
            for e in expr.elems[1:]:
                te = self.check_expr(e)
                if te == t0:
                    continue
                # Empty-literal holes unify with a concrete
                # sibling type (either direction); anything else
                # is still a genuine element-type mismatch.
                if matches_up_to_unknown(te, t0):
                    continue
                if matches_up_to_unknown(t0, te):
                    t0 = te
                    continue
                raise ForgeError("array literal elements must all have the same type",
                                 e.line, e.col)
            return f"[{t0}]"
        if isinstance(expr, A.TupleLit):
            # Heterogeneous by design: each element keeps its own
            # type, and the literal's type joins them in order.
            types = [self.check_expr(e) for e in expr.elems]
            return f"({', '.join(types)})"
        if isinstance(expr, A.TupleIndex):
            outermost = self._in_pinned_base == 0
            self._in_pinned_base += 1
            try:
                bt = self.check_expr(expr.base)
            finally:
                self._in_pinned_base -= 1
            if not is_tuple_type(bt):
                raise ForgeError(f"tuple index .{expr.index} needs a tuple value, "
                                 f"got {bt}", expr.line, expr.col)
            elems = tuple_elems(bt)
            if expr.index >= len(elems):
                raise ForgeError(f"tuple index .{expr.index} out of range for "
                                 f"{bt} ({len(elems)} elements)",
                                 expr.line, expr.col)
            root = self._access_root(expr)
            if (outermost and self._pinned_observe == 0
                    and self._pinned_write_root != root
                    and root in self.pinned
                    and self._is_owned_type(elems[expr.index])):
                raise ForgeError(f"use of pinned value '{root}' "
                                 f"(pin forbids moving or copying it; "
                                 f"change it in place through its fields "
                                 f"or indexes)", expr.line, expr.col)
            return elems[expr.index]
        if isinstance(expr, A.RangeLit):
            st = self.check_expr(expr.start)
            et = self.check_expr(expr.end)
            if st != "int" or et != "int":
                raise ForgeError(f"range endpoints must be int, got {st} and {et}",
                                 expr.line, expr.col)
            return "range"
        if isinstance(expr, A.StructLit):
            if expr.name not in self.structs:
                raise ForgeError(f"undefined struct '{expr.name}'", expr.line, expr.col)
            template_fields = self.structs[expr.name]
            params = self.struct_params.get(expr.name, [])
            provided = {}
            for fname, fexpr in expr.fields:
                if fname not in template_fields:
                    raise ForgeError(f"struct '{expr.name}' has no field '{fname}'",
                                     expr.line, expr.col)
                if fname in provided:
                    raise ForgeError(f"duplicate field '{fname}' in struct literal",
                                     expr.line, expr.col)
                provided[fname] = self.check_expr(fexpr)
                if (not params and isinstance(fexpr, A.Var)
                        and self._is_concrete_array(template_fields[fname])):
                    # An unresolved array stored into a concretely
                    # typed field resolves to the field's type.
                    if self._resolve_empty(fexpr.name, template_fields[fname]):
                        provided[fname] = template_fields[fname]
            missing = [f for f in template_fields if f not in provided]
            if missing:
                raise ForgeError(f"struct literal '{expr.name}' is missing field(s): "
                                 f"{', '.join(missing)}", expr.line, expr.col)
            if params:
                # Infer the concrete type from the field values.
                bindings = {}
                for fname, ftype in template_fields.items():
                    if not unify(ftype, provided[fname], bindings, params):
                        raise ForgeError(f"field '{fname}' of '{expr.name}' must match {ftype}, "
                                         f"got {provided[fname]}", expr.line, expr.col)
                missing_p = [p for p in params if p not in bindings]
                if missing_p:
                    raise ForgeError(f"could not infer type parameter(s) {', '.join(missing_p)} "
                                     f"for struct '{expr.name}'", expr.line, expr.col)
                concrete = expr.name + "<" + ", ".join(bindings[p] for p in params) + ">"
                fields = {f: substitute_type(ft, bindings) for f, ft in template_fields.items()}
                self.struct_instantiations[concrete] = fields
                expr.concrete_type = concrete
                # Re-check field types against the concrete fields
                # (unify already ensured the type-param fields match;
                # concrete fields must match exactly, except empty arrays).
                for fname, ftype in fields.items():
                    if provided[fname] != ftype:
                        fexpr = dict(expr.fields)[fname]
                        if not (isinstance(fexpr, A.ArrayLit) and not fexpr.elems
                                and ftype.startswith("[") and not (is_sized_array(ftype) and sized_len(ftype) > 0)) \
                                and not self.accepts(provided[fname], ftype, fexpr) \
                                and not self._sized_literal_ok(fexpr, ftype):
                            raise ForgeError(f"field '{fname}' of '{expr.name}' must be {ftype}, "
                                             f"got {provided[fname]}", expr.line, expr.col)
                return concrete
            fields = template_fields
            for fname, ftype in fields.items():
                if provided[fname] != ftype:
                    # Empty array literal, like in let, takes the field type.
                    fexpr = dict(expr.fields)[fname]
                    if not (isinstance(fexpr, A.ArrayLit) and not fexpr.elems
                            and ftype.startswith("[") and not (is_sized_array(ftype) and sized_len(ftype) > 0)) \
                            and not self.accepts(provided[fname], ftype, fexpr) \
                            and not self._sized_literal_ok(fexpr, ftype):
                        raise ForgeError(f"field '{fname}' of '{expr.name}' must be {ftype}, "
                                         f"got {provided[fname]}", expr.line, expr.col)
            expr.concrete_type = expr.name
            return expr.name
        if isinstance(expr, A.FieldAccess):
            path = self._field_path(expr)
            if (path is not None and path in self.moved_fields
                    and path != self._moved_field_target):
                raise ForgeError(f"use of moved value '{path}'", expr.line, expr.col)
            outermost = self._in_pinned_base == 0
            self._in_field_base += 1
            self._in_pinned_base += 1
            try:
                bt = self.check_expr(expr.base)
            finally:
                self._in_field_base -= 1
                self._in_pinned_base -= 1
            fields = self.struct_fields_for(bt)
            if fields is None:
                raise ForgeError(f"cannot access a field on a non-struct value of type {bt}",
                                 expr.line, expr.col)
            if expr.field not in fields:
                raise ForgeError(f"struct '{bt}' has no field '{expr.field}'",
                                 expr.line, expr.col)
            root = self._access_root(expr)
            if (outermost and self._pinned_observe == 0
                    and self._pinned_write_root != root
                    and root in self.pinned
                    and self._is_owned_type(fields[expr.field])):
                # Reading an owned field out of a pinned struct
                # would copy the hold; a scalar field is a plain
                # read and stays allowed.
                raise ForgeError(f"use of pinned value '{root}' "
                                 f"(pin forbids moving or copying it; "
                                 f"change it in place through its fields "
                                 f"or indexes)", expr.line, expr.col)
            return fields[expr.field]
        if isinstance(expr, A.Index):
            outermost = self._in_pinned_base == 0
            self._in_pinned_base += 1
            try:
                bt = self.check_expr(expr.base)
            finally:
                self._in_pinned_base -= 1
            if bt == "str":
                if self.check_expr(expr.index) != "int":
                    raise ForgeError("string index must be int", expr.line, expr.col)
                root = self._access_root(expr)
                if (outermost and self._pinned_observe == 0
                        and self._pinned_write_root != root
                        and root in self.pinned):
                    # Indexing a pinned string materializes a new
                    # str (one char); read it before pinning.
                    raise ForgeError(f"use of pinned value '{root}' "
                                     f"(pin forbids moving or copying it; "
                                     f"change it in place through its fields "
                                     f"or indexes)", expr.line, expr.col)
                return "str"
            et = elem_type(bt)
            if et is None:
                raise ForgeError(f"cannot index a non-array value of type {bt}",
                                 expr.line, expr.col)
            if self.check_expr(expr.index) != "int":
                raise ForgeError("array index must be int", expr.line, expr.col)
            root = self._access_root(expr)
            if (outermost and self._pinned_observe == 0
                    and self._pinned_write_root != root
                    and root in self.pinned
                    and self._is_owned_type(et)):
                # Reading an owned element out of a pinned array
                # would copy the hold; a scalar element is a
                # plain read and stays allowed.
                raise ForgeError(f"use of pinned value '{root}' "
                                 f"(pin forbids moving or copying it; "
                                 f"change it in place through its fields "
                                 f"or indexes)", expr.line, expr.col)
            return et
        if isinstance(expr, A.Cast):
            t = self.check_expr(expr.expr)
            if not self.valid_type(expr.target) or expr.target == "void":
                raise ForgeError(f"unknown cast target '{expr.target}'", expr.line, expr.col)
            if (t, expr.target) in (("int", "float"), ("float", "int")):
                return expr.target
            # Casts between int types (int counts as i64): widening
            # is free, narrowing is range-checked at runtime.
            # Identity casts stay rejected (t != target).
            if is_int_type(t) and is_int_type(expr.target) and t != expr.target:
                return expr.target
            # Fixed-width integers convert to and from float like
            # int does (a truncating C cast from float).
            if is_int_type(t) and expr.target == "float":
                return expr.target
            if t == "float" and is_int_type(expr.target):
                return expr.target
            # A member value casts into its union: `5 as int | str`.
            # The reverse (union to member) is unsafe and rejected:
            # narrow with match instead.
            if is_union_type(expr.target) and t in union_members(expr.target):
                return expr.target
            # Newtype crossings, both directions, to the newtype's
            # own underlying type only (chains resolve: B = A = int
            # allows B <-> int and A <-> int; B <-> A needs two
            # casts, via int).
            targets = getattr(self, "newtype_targets", {})
            if t in targets and self.underlying_newtype(t) == expr.target:
                return expr.target
            if expr.target in targets and self.underlying_newtype(expr.target) == t:
                return expr.target
            raise ForgeError(f"cannot cast {t} to {expr.target}", expr.line, expr.col)
        if isinstance(expr, A.Try):
            t = self.check_expr(expr.expr)
            ret = self.current_ret
            g = parse_generic(t)
            rg = parse_generic(ret)
            if g is not None and g[0] == "Option" and rg is not None and rg[0] == "Option":
                fields = self.struct_fields_for(t)
                if not fields or fields.get("present") != "bool" or "value" not in fields:
                    raise ForgeError("? for Option needs a struct with present: bool and value fields",
                                     expr.line, expr.col)
                expr.kind = "Option"
                expr.value_type = g[1][0]
                expr.ret_type = ret
                return g[1][0]
            if g is not None and g[0] == "Result" and rg is not None and rg[0] == "Result":
                if g[1][1] != rg[1][1]:
                    raise ForgeError(f"? error type mismatch: expression is Result<_, {g[1][1]}> "
                                     f"but function returns Result<_, {rg[1][1]}>",
                                     expr.line, expr.col)
                fields = self.struct_fields_for(t)
                if not fields or fields.get("ok") != "bool" or "value" not in fields or "error" not in fields:
                    raise ForgeError("? for Result needs a struct with ok: bool, value, error fields",
                                     expr.line, expr.col)
                expr.kind = "Result"
                expr.value_type = g[1][0]
                expr.ret_type = ret
                expr.error_type = g[1][1]
                return g[1][0]
            raise ForgeError(f"? needs an Option or Result value whose type matches "
                             f"the function's return type {ret}, got {t}",
                             expr.line, expr.col)
        if isinstance(expr, A.UnaryOp):
            t = self.check_expr(expr.expr)
            if expr.op == "-" and (t in ("int", "float") or is_fixed_int(t)):
                return t
            if expr.op == "!" and t == "bool":
                return "bool"
            if expr.op == "~" and (t == "int" or is_fixed_int(t)):
                return t
            raise ForgeError(f"operator '{expr.op}' does not apply to {t}", expr.line, expr.col)
        if isinstance(expr, A.BinOp):
            return self.check_binop(expr)
        if isinstance(expr, A.MethodCall):
            return self.check_method_call(expr)
        if isinstance(expr, A.Call):
            return self.check_call(expr)
        raise ForgeError(f"unsupported expression {type(expr).__name__}", expr.line, expr.col)

    def check_call(self, call):
        if call.name in STMT_BUILTINS:
            raise ForgeError(f"'{call.name}' can only be used as a statement, not as a value",
                             call.line, call.col)
        if self.freestanding and call.name in (
                "read_file", "write_file", "read_bytes", "write_bytes",
                "file_exists", "read_line", "try_alloc",
                "mmap_open", "mmap_get", "mmap_grow", "mmap_get32",
                "http_get", "http_listen", "http_accept", "http_read_request",
                "http_respond", "http_respond_status", "http_close",
                "clock_micros", "args", "parallel_dot", "parallel_matmul",
                "sqrt", "exp", "log", "pow", "abs"):
            raise ForgeError(f"'{call.name}' needs the hosted runtime "
                             f"(not in freestanding v1)",
                             call.line, call.col)
        if call.name in self.enum_variants:
            enum_name = self.enum_variants[call.name]
            payload = self.enum_payloads[enum_name][call.name]
            params = self.enum_params.get(enum_name, [])
            if payload is None:
                if call.args:
                    raise ForgeError(f"variant '{call.name}' takes no payload", call.line, call.col)
                if params:
                    call.concrete_type = enum_name + "<" + ", ".join("?" for _ in params) + ">"
                else:
                    call.concrete_type = enum_name
                return call.concrete_type
            if len(call.args) != 1:
                raise ForgeError(f"variant '{call.name}' takes exactly one payload argument",
                                 call.line, call.col)
            at = self.check_expr(call.args[0])
            if not params:
                if at != payload:
                    raise ForgeError(f"variant '{call.name}' payload must be {payload}, got {at}",
                                     call.line, call.col)
                call.concrete_type = enum_name
                return enum_name
            bindings = {}
            if not unify(payload, at, bindings, params):
                raise ForgeError(f"variant '{call.name}' payload must match {payload}, got {at}",
                                 call.line, call.col)
            concrete_args = [bindings.get(p, "?") for p in params]
            call.concrete_type = enum_name + "<" + ", ".join(concrete_args) + ">"
            return call.concrete_type
        if call.name == "len":
            if len(call.args) != 1:
                raise ForgeError("len() takes exactly one argument", call.line, call.col)
            t = self._check_observed(call.args[0])
            if t != "str" and elem_type(t) is None:
                raise ForgeError(f"len() needs a str or array, got {t}", call.line, call.col)
            return "int"
        if call.name == "refcount":
            if len(call.args) != 1:
                raise ForgeError("refcount() takes exactly one argument", call.line, call.col)
            t = self._check_observed(call.args[0])
            if elem_type(t) is None:
                raise ForgeError(f"refcount() needs an array, got {t}", call.line, call.col)
            return "int"
        if call.name == "weak_new":
            if len(call.args) != 1:
                raise ForgeError("weak_new() takes exactly one argument", call.line, call.col)
            t = self.check_expr(call.args[0])
            if t != "[int]":
                raise ForgeError(f"weak_new() needs an [int] array in v1, got {t}", call.line, call.col)
            return "int"
        if call.name == "weak_upgrade":
            if len(call.args) != 1:
                raise ForgeError("weak_upgrade() takes exactly one argument", call.line, call.col)
            if self.check_expr(call.args[0]) != "int":
                raise ForgeError("weak_upgrade() takes a weak id (int)", call.line, call.col)
            return "(bool, [int])"
        if call.name == "move":
            if len(call.args) != 1:
                raise ForgeError("move() takes exactly one argument", call.line, call.col)
            arg = call.args[0]
            if not isinstance(arg, (A.Var, A.FieldAccess)):
                raise ForgeError("move needs a variable or field", call.line, call.col)
            in_conditional = self.loop_depth > 0 or self.branch_depth > 0
            if isinstance(arg, A.Var) and arg.name in self.loop_vars:
                raise ForgeError("move of a for-loop variable is not supported in v2; "
                                 "copy it into a let first, then move that",
                                 call.line, call.col)
            if isinstance(arg, A.Var) and arg.name in self.pinned:
                raise ForgeError(f"cannot move pinned value '{arg.name}' "
                                 f"(pin forbids moving it)",
                                 call.line, call.col)
            if isinstance(arg, A.FieldAccess):
                # Field moves are straight-line only in v2: a field
                # move in a branch or loop would need a per-field
                # runtime flag, which is a named follow-up, not
                # silently approximated (see TOP_500_PROGRESS).
                if in_conditional:
                    raise ForgeError("move of a field inside a branch or loop is not "
                                     "supported in v2; move the field in straight-line "
                                     "code", call.line, call.col)
                path = self._field_path(arg)
                if path is None:
                    raise ForgeError("move needs a variable or field", call.line, call.col)
                if path.split(".")[0] in self.pinned:
                    raise ForgeError(f"cannot move a field of pinned value "
                                     f"'{path.split('.')[0]}' (pin forbids "
                                     f"moving it)", call.line, call.col)
                t = self.check_expr(arg)
                if not (elem_type(t) is not None or t == "str" or is_tuple_type(t)
                        or t in self.structs or t in self.struct_instantiations):
                    raise ForgeError(f"move needs an owned value (array, str, struct, tuple), "
                                     f"got {t}", call.line, call.col)
                self.moved_fields.add(path)
                call.in_conditional = False
                return t
            t = self.check_expr(arg)
            if not (elem_type(t) is not None or t == "str" or is_tuple_type(t)
                    or t in self.structs or t in self.struct_instantiations):
                raise ForgeError(f"move needs an owned value (array, str, struct, tuple), "
                                 f"got {t}", call.line, call.col)
            self.moved.add(arg.name)
            # Codegen reads this: a conditional move must not
            # forget the source at compile time (the branch or
            # loop may not run); it sets a runtime moved flag
            # instead, and scope-end frees check that flag.
            call.in_conditional = in_conditional
            return t
        if call.name == "mmap_open":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("mmap_open() takes a file path (str)", call.line, call.col)
            return "int"
        if call.name == "mmap_get":
            if len(call.args) != 2:
                raise ForgeError("mmap_get() takes a mapping id and an index", call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "int":
                    raise ForgeError("mmap_get() arguments must be int", call.line, call.col)
            return "int"
        if call.name == "mmap_grow":
            if len(call.args) != 2:
                raise ForgeError("mmap_grow() takes a mapping id and a new size", call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "int":
                    raise ForgeError("mmap_grow() arguments must be int", call.line, call.col)
            return "int"
        if call.name == "mmap_get32":
            if len(call.args) != 2:
                raise ForgeError("mmap_get32() takes a mapping id and a byte offset", call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "int":
                    raise ForgeError("mmap_get32() arguments must be int", call.line, call.col)
            return "int"
        if call.name == "range":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError("range() takes exactly one int argument", call.line, call.col)
            return "[int]"
        if call.name == "clock_micros":
            if call.args:
                raise ForgeError("clock_micros() takes no arguments", call.line, call.col)
            return "int"
        if call.name in ("alloc_count", "free_count", "arr_alloc_count", "arr_free_count"):
            if call.args:
                raise ForgeError(f"{call.name}() takes no arguments", call.line, call.col)
            return "int"
        if call.name == "parallel_dot":
            if len(call.args) != 2 or self.check_expr(call.args[0]) != "[float]" or self.check_expr(call.args[1]) != "[float]":
                raise ForgeError("parallel_dot() takes two [float] arguments", call.line, call.col)
            return "float"
        if call.name == "parallel_matmul":
            if len(call.args) != 3 or self.check_expr(call.args[0]) != "[float]" or self.check_expr(call.args[1]) != "[float]" or self.check_expr(call.args[2]) != "int":
                raise ForgeError("parallel_matmul() takes [float], [float], int", call.line, call.col)
            return "[float]"
        if call.name in ("sqrt", "exp", "log"):
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "float":
                raise ForgeError(f"{call.name}() takes exactly one float argument",
                                 call.line, call.col)
            return "float"
        if call.name == "pow":
            if len(call.args) != 2:
                raise ForgeError("pow() takes exactly two arguments", call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "float":
                    raise ForgeError("pow() takes float arguments", call.line, call.col)
            return "float"
        if call.name == "abs":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError("abs() takes exactly one int argument", call.line, call.col)
            return "int"
        if call.name in ("wrapping_add", "wrapping_sub", "wrapping_mul"):
            # Defined wraparound beside the checked default: these
            # never fail, on any backend (native wraps via unsigned
            # arithmetic, big32 and WASM wrap by nature).
            if len(call.args) != 2:
                raise ForgeError(f"{call.name}() takes exactly two arguments",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "int":
                    raise ForgeError(f"{call.name}() takes int arguments",
                                     call.line, call.col)
            return "int"
        if call.name == "wrapping_neg":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError("wrapping_neg() takes exactly one int argument",
                                 call.line, call.col)
            return "int"
        if call.name == "file_exists":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("file_exists() takes exactly one str argument",
                                 call.line, call.col)
            return "bool"
        if call.name == "read_file":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("read_file() takes exactly one str argument",
                                 call.line, call.col)
            return "str"
        if call.name == "read_line":
            if len(call.args) != 0:
                raise ForgeError("read_line() takes no arguments",
                                 call.line, call.col)
            return "str"
        if call.name == "peek32":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError("peek32() takes exactly one int argument",
                                 call.line, call.col)
            return "int"
        if call.name == "csr_read":
            # RISC-V CSR instructions take a 12-bit immediate, not a
            # register, so the CSR number must be a literal.
            if len(call.args) != 1 or not isinstance(call.args[0], A.IntLit):
                raise ForgeError("csr_read() takes exactly one literal CSR number",
                                 call.line, call.col)
            if not 0 <= call.args[0].value <= 4095:
                raise ForgeError("CSR number must be in 0..4095",
                                 call.line, call.col)
            return "int"
        if call.name == "ecall":
            if len(call.args) != 2:
                raise ForgeError("ecall() takes exactly two arguments "
                                 "(extension id, argument)",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "int":
                    raise ForgeError("ecall() takes int arguments",
                                     call.line, call.col)
            return "int"
        if call.name == "ecall3":
            if len(call.args) != 3:
                raise ForgeError("ecall3() takes exactly three arguments "
                                 "(extension id, argument 0, argument 1)",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "int":
                    raise ForgeError("ecall3() takes int arguments",
                                     call.line, call.col)
            return "int"
        if call.name == "write_file":
            if len(call.args) != 2:
                raise ForgeError("write_file() takes exactly two arguments",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "str":
                    raise ForgeError("write_file() takes str arguments", call.line, call.col)
            return "bool"
        if call.name == "read_bytes":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("read_bytes() takes exactly one str argument",
                                 call.line, call.col)
            return "[int]"
        if call.name == "try_alloc":
            # Top-500 #36: fallible allocation. Returns Result<[int], str>:
            # Ok with a zero-initialised array, or Err("out of memory") /
            # Err("bad size") instead of the fatal forge_fail. The Result
            # struct comes from stdlib/result.fg, so the program must
            # import it; register the concrete instantiation here so
            # check()'s epilogue appends it to program.structs and
            # codegen emits the C struct body.
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError("try_alloc() takes exactly one int argument",
                                 call.line, call.col)
            if "Result" not in self.structs:
                raise ForgeError("try_alloc() needs import \"result.fg\" "
                                 "(it returns Result<[int], str>)",
                                 call.line, call.col)
            fields = self.struct_fields_for("Result<[int], str>")
            if fields is None:
                raise ForgeError("try_alloc() needs Result<T, E> with ok/value/error "
                                 "fields (import \"result.fg\")",
                                 call.line, call.col)
            self.struct_instantiations["Result<[int], str>"] = fields
            call.concrete_type = "Result<[int], str>"
            return "Result<[int], str>"
        if call.name == "write_bytes":
            if len(call.args) != 2:
                raise ForgeError("write_bytes() takes exactly two arguments",
                                 call.line, call.col)
            if self.check_expr(call.args[0]) != "str":
                raise ForgeError("write_bytes() takes a str path", call.line, call.col)
            if self.check_expr(call.args[1]) != "[int]":
                raise ForgeError("write_bytes() takes [int] data", call.line, call.col)
            return "bool"
        if call.name == "args":
            if call.args:
                raise ForgeError("args() takes no arguments", call.line, call.col)
            return "[str]"
        if call.name == "parse_int":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("parse_int() takes exactly one str argument",
                                 call.line, call.col)
            return "int"
        if call.name == "parse_float":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("parse_float() takes exactly one str argument",
                                 call.line, call.col)
            return "float"
        if call.name == "split":
            if len(call.args) != 2:
                raise ForgeError("split() takes exactly two arguments", call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "str":
                    raise ForgeError("split() takes str arguments", call.line, call.col)
            return "[str]"
        if call.name == "join":
            if len(call.args) != 2:
                raise ForgeError("join() takes exactly two arguments", call.line, call.col)
            if self.check_expr(call.args[0]) != "[str]":
                raise ForgeError("join() takes a [str] as its first argument",
                                 call.line, call.col)
            if self.check_expr(call.args[1]) != "str":
                raise ForgeError("join() takes a str separator", call.line, call.col)
            return "str"
        if call.name == "substr":
            if len(call.args) != 3:
                raise ForgeError("substr() takes exactly three arguments", call.line, call.col)
            if self.check_expr(call.args[0]) != "str":
                raise ForgeError("substr() takes a str as its first argument",
                                 call.line, call.col)
            for a in call.args[1:]:
                if self.check_expr(a) != "int":
                    raise ForgeError("substr() takes int start and length",
                                     call.line, call.col)
            return "str"
        if call.name == "trim":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("trim() takes exactly one str argument",
                                 call.line, call.col)
            return "str"
        if call.name in ("starts_with", "ends_with"):
            if len(call.args) != 2:
                raise ForgeError(f"{call.name}() takes exactly two arguments",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "str":
                    raise ForgeError(f"{call.name}() takes str arguments",
                                     call.line, call.col)
            return "bool"
        if call.name == "http_get":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("http_get() takes exactly one str URL argument",
                                 call.line, call.col)
            return "str"
        if call.name == "http_listen":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError("http_listen() takes exactly one int port argument",
                                 call.line, call.col)
            return "int"
        if call.name in ("http_accept", "http_close"):
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError(f"{call.name}() takes exactly one int fd argument",
                                 call.line, call.col)
            return "int"
        if call.name == "http_read_request":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "int":
                raise ForgeError("http_read_request() takes exactly one int client fd argument",
                                 call.line, call.col)
            return "str"
        if call.name == "http_respond":
            if len(call.args) != 2 or self.check_expr(call.args[0]) != "int" or self.check_expr(call.args[1]) != "str":
                raise ForgeError("http_respond() takes (int client fd, str body)",
                                 call.line, call.col)
            return "int"
        if call.name == "http_respond_status":
            if len(call.args) != 3 or self.check_expr(call.args[0]) != "int" or self.check_expr(call.args[1]) != "int" or self.check_expr(call.args[2]) != "str":
                raise ForgeError("http_respond_status() takes (int client fd, int status, str body)",
                                 call.line, call.col)
            return "int"
        fn = self.funcs.get(call.name)
        if fn is None:
            raise ForgeError(f"undefined function '{call.name}'"
                             f"{suggest(call.name, list(self.funcs) + list(BUILTINS))}",
                             call.line, call.col)
        if len(call.args) != len(fn.params):
            raise ForgeError(f"'{call.name}' takes {len(fn.params)} argument(s), "
                             f"got {len(call.args)}", call.line, call.col)
        if getattr(fn, "type_params", None):
            # Generic call: infer bindings from argument types, then
            # check the concrete copy and rewrite this call to it.
            type_params = fn.type_params
            if self.current_type_params:
                # The caller itself is generic (its body is only
                # checked on instantiation, so this call will be
                # re-checked then with concrete types).
                arg_types = [self.check_expr(a) for a in call.args]
                bindings = {}
                ok = True
                for (pn, pt), t in zip(fn.params, arg_types):
                    if not unify(pt, t, bindings, type_params):
                        ok = False
                if not ok:
                    raise ForgeError(f"argument types do not match generic function '{call.name}'",
                                     call.line, call.col)
                # Return the substituted return type for template checking;
                # the concrete call is resolved when the caller is instantiated.
                return substitute_type(fn.ret, bindings)
            arg_types = [self.check_expr(a) for a in call.args]
            for t in arg_types:
                if contains_type_param(t, self.current_type_params):
                    raise ForgeError("generic function cannot be called with an abstract type",
                                     call.line, call.col)
            bindings = {}
            for (pn, pt), t in zip(fn.params, arg_types):
                if not unify(pt, t, bindings, type_params):
                    raise ForgeError(f"argument '{pn}' of '{call.name}' must match {pt}, got {t}",
                                     call.line, call.col)
            missing = [p for p in type_params if p not in bindings]
            if missing:
                raise ForgeError(f"could not infer type parameter(s) {', '.join(missing)} "
                                 f"for '{call.name}'", call.line, call.col)
            spec = self.instantiate_func(fn, bindings, call.line, call.col)
            if spec is not None:
                call.name = spec.name
                return spec.ret
            # Recursive instantiation in progress: return substituted ret.
            return substitute_type(fn.ret, bindings)
        for arg, (pn, pt) in zip(call.args, fn.params):
            t = self.check_expr(arg)
            if (isinstance(arg, A.Var)
                    and self._resolve_empty(arg.name, pt)):
                # A concretely typed parameter constrains an
                # unresolved array argument to the parameter type.
                t = pt
            filled = self.fill_placeholder(t, pt)
            if filled != t:
                if isinstance(arg, A.Call):
                    arg.concrete_type = filled
                t = filled
            if t != pt:
                if not (isinstance(arg, A.ArrayLit) and not arg.elems and pt.startswith("[") and not (is_sized_array(pt) and sized_len(pt) > 0)) \
                        and not self.accepts(t, pt, arg) \
                        and not self._sized_literal_ok(arg, pt):
                    raise ForgeError(self._literal_fit_msg(arg, pt)
                                     or f"argument '{pn}' of '{call.name}' must be {pt}, got {t}"
                                     f"{cast_hint(t, pt)}",
                                     call.line, call.col)
        return fn.ret

    def underlying_newtype(self, t):
        """Resolve a newtype chain to its ultimate underlying type."""
        targets = getattr(self, "newtype_targets", {})
        seen = set()
        while t in targets and t not in seen:
            seen.add(t)
            t = targets[t]
        return t

    def check_binop(self, node):
        lt = self.check_expr(node.left)
        rt = self.check_expr(node.right)
        op = node.op
        # An integer literal adapts to the other operand's fixed
        # type when it fits (the same adaptation as let/argument
        # sites). Shifts are excluded: a shift count is a plain
        # int, so it never needs to fit the left type, and its
        # range is checked at runtime instead.
        if lt != rt and op not in ("<<", ">>"):
            for fixed_t, lit_expr in ((lt, node.right), (rt, node.left)):
                if is_fixed_int(fixed_t):
                    v = literal_value(lit_expr)
                    if v is not None:
                        lo, hi = fixed_range(fixed_t)
                        if lo <= v <= hi:
                            if op in ("+", "-", "*", "/", "%", "&", "|", "^"):
                                return fixed_t
                            if op in ("<", "<=", ">", ">=", "==", "!="):
                                return "bool"
                        raise ForgeError(f"integer literal {v} does not fit in {fixed_t}",
                                         node.line, node.col)
        if op in ("+", "-", "*", "/", "%"):
            if op == "+" and lt == "str" and rt == "str":
                return "str"
            if op == "%" and lt == "int" and rt == "int":
                return "int"
            if op == "%" and lt == rt and is_fixed_int(lt):
                return lt
            if op in ("+", "-", "*", "/") and lt == rt and (lt in ("int", "float")
                                                             or is_fixed_int(lt)):
                return lt
            raise ForgeError(f"operator '{op}' needs matching int or float operands "
                             f"(or str + str), got {lt} and {rt}", node.line, node.col)
        if op in ("<", "<=", ">", ">="):
            if lt == rt and (lt in ("int", "float") or is_fixed_int(lt)):
                return "bool"
            raise ForgeError(f"operator '{op}' needs matching int or float operands, "
                             f"got {lt} and {rt}", node.line, node.col)
        if op in ("==", "!="):
            if lt == rt and (lt in ("int", "float", "bool", "str")
                             or is_fixed_int(lt) or lt in self.enums):
                return "bool"
            # Same-newtype equality, when the underlying type is
            # itself comparable. Ordering and arithmetic still need
            # an explicit cast out: distinctness is about mixing
            # types, not about comparing identical ones.
            if lt == rt and lt in getattr(self, "newtypes", set()):
                under = self.underlying_newtype(lt)
                if under in ("int", "float", "bool", "str") or under in self.enums:
                    return "bool"
            raise ForgeError(f"operator '{op}' needs matching int, float, bool, str or enum "
                             f"operands, got {lt} and {rt}", node.line, node.col)
        if op in ("&&", "||"):
            if lt == "bool" and rt == "bool":
                return "bool"
            raise ForgeError(f"operator '{op}' needs bool operands, got {lt} and {rt}",
                             node.line, node.col)
        if op in ("&", "|", "^", "<<", ">>"):
            if lt == "int" and rt == "int":
                return "int"
            if op in ("&", "|", "^") and lt == rt and is_fixed_int(lt):
                return lt
            if op in ("<<", ">>") and is_fixed_int(lt) and (rt == "int" or rt == lt):
                # Shifts take a plain int count or the same width.
                return lt
            raise ForgeError(f"operator '{op}' needs int operands, got {lt} and {rt}",
                             node.line, node.col)
        raise ForgeError(f"unknown operator '{op}'", node.line, node.col)


def check(program, require_main=True, freestanding=False):
    Checker(program, freestanding).check(require_main=require_main)
