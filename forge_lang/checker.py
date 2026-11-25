"""Static checker for Qasida.

Types: int, float, bool, str, void, and [T] dynamic arrays.
Builtins:
  statement-only: print, println, push, fail, fail_compile, eprintln
  expression: len, range, clock_micros, sqrt, exp, log, pow, abs, run_command
Rules: no null, no implicit conversion (except int->float via `as`),
immutable by default, bool conditions only, checked calls, and a
non-void function must end with a return.
"""

import copy
import difflib
from dataclasses import dataclass

from .errors import ForgeError
from . import ast_nodes as A
from .generics import (parse_generic, mangle_type, substitute_type,
                       unify, contains_type_param)
from .fntypes import is_fn_type, fn_parts, fn_type_string
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
# C keywords that are not Qasida keywords: user names colliding
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
                 "csr_write", "csr_set", "csr_clear",
                 "fail_compile", "eprintln"}
EXPR_BUILTINS = {"len", "range", "clock_micros", "panicked_tasks", "last_errno", "try_read_file", "try_read_bytes", "sqrt", "exp", "log", "sin", "cos", "tan", "pow", "abs",
                 "wrapping_add", "wrapping_sub", "wrapping_mul", "wrapping_neg",
                 "read_file", "read_line", "write_file", "read_bytes", "write_bytes",
                 "file_exists", "args", "parse_int", "parse_float",
                 "run_command",
                 "try_alloc",
                 "try_call",
                 "split", "join", "substr", "trim", "starts_with", "ends_with",
                 "http_get", "http_listen", "http_accept", "http_read_request",
                 "http_respond", "http_respond_status", "http_close",
                 "alloc_count", "free_count",
                 "parallel_dot", "parallel_matmul",
                 "arr_alloc_count", "arr_free_count", "refcount",
                 "weak_new", "weak_upgrade", "move",
                 "mmap_open", "mmap_get", "mmap_grow", "mmap_get32",
                 "peek32", "csr_read", "ecall", "ecall3",
                 "mkdir", "readdir", "try_readdir", "rename", "symlink",
                 "readlink", "try_readlink", "chmod", "chown",
                 "stat_mode", "stat_uid", "stat_gid", "is_dir",
                 "str_compare"}
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


# ------------------------------------------------------------------
# Top-500 #70 (comptime if): the build target record — the one place
# that knows what the program is being compiled for. arch/os derive
# 1:1 from target; mode/debug/freestanding come from the CLI flags.
# The checker resolves `comptime if` against this record and splices
# the taken branch in place, so infer and all three codegens see
# resolved code and need no change.
# ------------------------------------------------------------------

@dataclass
class Target:
    target: str  # "native" | "big32" | "wasm"
    arch: str  # "x86_64" | "riscv32" | "wasm32"
    os: str  # "linux" | "none" | "wasm"
    mode: str  # "safe" | "fast"
    debug: bool
    freestanding: bool


_TARGET_DERIVED = {
    "native": ("x86_64", "linux"),
    "big32": ("riscv32", "none"),
    "wasm": ("wasm32", "wasm"),
}


def make_target(target, mode="safe", debug=False, freestanding=False):
    if target not in _TARGET_DERIVED:
        raise ForgeError(
            f"unknown target '{target}'; allowed: native, big32, wasm")
    arch, os_name = _TARGET_DERIVED[target]
    return Target(target, arch, os_name, mode, debug, freestanding)


class Checker:
    def __init__(self, program, freestanding=False, dump_error_sets=False,
                 target=None):
        self.program = program
        self.freestanding = freestanding
        self.dump_error_sets = dump_error_sets  # Top-500 #50: print
        # Top-500 #70: the build target this check resolves
        # `comptime if` against (default: native, from the flags).
        self.target = (target if target is not None
                       else make_target("native", freestanding=freestanding))
        # inferred error sets to stderr after checking (qasida check
        # --dump-error-sets).
        # Top-500 #50 (inferred error sets, ES-C1–ES-C9): per-function
        # summaries, name -> (enum, members) where members is a
        # frozenset of variant names, or None for TOP. The empty set
        # is real (ES-C7) and distinct from TOP.
        self.error_sets = {}
        self.value_sets = {}
        # Deferred match verdicts (ES-C5): id(stmt) -> (fn name, base
        # enum, seen arm patterns, has_wildcard). Recorded in phase 1;
        # the verdict is issued by the post-fixpoint walk.
        self._pending_matches = {}
        self._es_fn_table = {}  # name -> FuncDef (built in the 2nd pass)
        self._es_bound_hit = False  # worklist bound hit: summaries widened
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
        self.current_file = ""  # file the function being checked lives in (Top-500 #48)
        self.current_type_params = []
        self.loop_depth = 0
        self.branch_depth = 0
        # Top-500 #62: labels of the enclosing labeled loops,
        # innermost last — a separate namespace from variables, so
        # a label may share a name with one. Reset on fn entry
        # (like loop_depth): a labeled break/continue inside a
        # nested function must not see the outer fn's labels.
        self.label_stack = []
        self.moved = set()
        self.moved_fields = set()
        self.pinned = set()
        self._in_field_base = 0
        self._in_pinned_base = 0
        self._pinned_write_root = None
        self._pinned_observe = 0
        self._moved_field_target = None
        self.loop_vars = []
        # Top-500 #494: (scope-dict id, name) of loop-variable
        # scope entries, so a `let` with a loop var's name keeps
        # the duplicate error instead of becoming a rebind.
        self._loop_var_entries = set()
        # For-iterable stack (Top-500 #40): (root name, field path or
        # None) for each enclosing for loop's iterable, so a move of
        # the iterable inside the body is rejected — the loop reads
        # the buffer again on the next iteration, after the moved-to
        # binding's scope-end free.
        self._for_iterables = []
        self.func_instantiations = {}  # (name, bindings tuple) -> FuncDef
        self.struct_instantiations = {}  # concrete type -> {field: type}
        self._instantiating = set()
        # Lambda frames (Top-500 #101, CL-C1/CL-C2): a stack of
        # {"boundary": scope depth at lambda entry, "captures":
        # {name: type}} — one frame per lambda being checked.
        # The boundary is len(self.scopes) BEFORE the lambda's
        # param scope is pushed, so a name resolving to a scope
        # at index < boundary is a capture of that lambda.
        self._lambda_frames = []
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
        if is_fn_type(t):
            # Fn type (Top-500 #103): every param a valid value type
            # (not void, no union anywhere inside — a union nested in
            # a fn type would never get its C typedef emitted), the
            # ret void or a valid value type (same union rule).
            # Type params inside a fn type are valid when in scope
            # (generic map needs fn(T) -> T); they pass through the
            # recursive valid_type calls below.
            parts = fn_parts(t)
            if parts is None:
                return False
            params, ret = parts
            if any(" | " in p for p in params) or " | " in ret:
                return False
            if not all(self.valid_type(p) for p in params):
                return False
            return ret == "void" or self.valid_type(ret)
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

    def _value_pattern_key(self, pat, et, fields):
        """Validate one value pattern (Top-500 #69, VP-C1..C6) and
        return its duplicate-detection key. `et` is the scrutinee
        type; `fields` is the scrutinee struct's concrete field
        dict ({} for non-structs). Raises ForgeError on any rule
        violation. Binding/wildcard field patterns contribute the
        same key component ("any") — two struct patterns that
        differ only in binding names match the same values and
        are duplicates."""
        if pat.kind == "lit_int":
            if et != "int":
                raise ForgeError(f"int pattern '{pat.value}' does not match "
                                 f"scrutinee of type {et}", pat.line, pat.col)
            if pat.value < -(2 ** 63) or pat.value > 2 ** 63 - 1:
                raise ForgeError(f"int pattern {pat.value} does not fit in i64",
                                 pat.line, pat.col)
            return ("lit_int", pat.value)
        if pat.kind == "lit_bool":
            if et != "bool":
                raise ForgeError(f"bool pattern '{pat.value}' does not match "
                                 f"scrutinee of type {et}", pat.line, pat.col)
            return ("lit_bool", pat.value)
        if pat.kind == "lit_str":
            if et != "str":
                raise ForgeError(f"string pattern does not match "
                                 f"scrutinee of type {et}", pat.line, pat.col)
            return ("lit_str", pat.value)
        if pat.kind == "struct":
            base = parse_generic(et)[0] if parse_generic(et) else et
            if pat.value != base:
                raise ForgeError(f"struct pattern '{pat.value}' does not match "
                                 f"scrutinee of type {et}", pat.line, pat.col)
            have = {fn for fn, _fp in (pat.fields or [])}
            missing = [fn for fn in fields if fn not in have]
            if missing:
                raise ForgeError(f"struct pattern '{pat.value}' is missing "
                                 f"fields: {', '.join(missing)}", pat.line, pat.col)
            parts = []
            for fname, fp in (pat.fields or []):
                if fname not in fields:
                    raise ForgeError(f"struct '{pat.value}' has no field '{fname}'",
                                     pat.line, pat.col)
                if fp.kind in ("binding", "wildcard"):
                    parts.append((fname, "any"))
                else:
                    parts.append((fname, self._value_pattern_key(fp, fields[fname], {})))
            return ("struct", tuple(parts))
        raise ForgeError("unsupported pattern in a value match", pat.line, pat.col)

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
            elif isinstance(node, A.Lambda):
                # Lambda param/return types (Top-500 #101): aliases
                # inside them expand like fn-declaration types.
                node.params = [(n, expand(t)) for n, t in node.params]
                node.ret = expand(node.ret)
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
            if e.name in ("fail", "fail_compile"):
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
        # Top-500 #50: second pass — inferred error sets (ES-C1–ES-C9).
        # Walks already-checked bodies, computes per-function value-sets
        # and error-sets by a worklist fixpoint, then issues the deferred
        # match-exhaustiveness verdicts (ES-C5).
        self._infer_error_sets()
        return self.program

    # ------------------------------------------------------------------
    # Top-500 #50: inferred error sets (option A, ES-C1–ES-C9).
    #
    # A set is (enum, members) where members is a frozenset of variant
    # names, or None for TOP ("any variant of the enum"). The empty
    # frozenset is a real set (ES-C7: a function that only ever fail()s
    # has an EMPTY error-set), distinct from TOP. Sets are compile-time
    # only and erased at runtime (ES-C9): no codegen change.
    #
    # The walker returns a 4-tuple (typ, kind, enum, members) for every
    # expression: kind is "result" (a Result value whose error set is
    # members over enum), "enum" (a bare enum value), or "other". It
    # never re-implements check_expr: types come only from the
    # enclosing return type, let annotations, callee signatures (the
    # function table built after phase 1, which includes generic
    # instantiations — phase 1 rewrites generic call.name to the
    # mangled name), StructLit.concrete_type, and the locals table.
    # Anything it cannot type is ("?", "other", "", None); a
    # return/store of such a value in a set-bearing position falls
    # back to TOP of the enclosing/declared enum, which is sound.
    # ------------------------------------------------------------------

    def _es_union(self, a, b):
        """Union two (enum, members|None) sets; None members = TOP."""
        enum = a[0] or b[0]
        if a[1] is None or b[1] is None:
            return (enum, None)
        return (enum, a[1] | b[1])

    def _es_enum_base(self, t):
        """Base enum name for a (possibly instantiated) enum type, else None."""
        if t in self.enums and not self.enum_params.get(t):
            return t
        g = parse_generic(t)
        if g is not None and g[0] in self.enums:
            return g[0]
        return None

    def _es_result_parts(self, t):
        """(T, E) for a Result<T, E> type string, else None."""
        g = parse_generic(t)
        if g is not None and g[0] == "Result" and len(g[1]) == 2:
            return g[1][0], g[1][1]
        return None

    def _es_kind_of_type(self, t):
        """("result", E) / ("enum", E) / ("other", "") for a type string."""
        rp = self._es_result_parts(t)
        if rp is not None:
            _T, E = rp
            if self._es_enum_base(E) is not None:
                return ("result", E)
            return ("other", "")
        eb = self._es_enum_base(t)
        if eb is not None:
            return ("enum", eb)
        return ("other", "")

    def _es_summary_members(self, name, kind):
        """Members (frozenset|None) for a callee's summary; None = TOP.
        A walkable callee with no stored summary yet contributes empty
        (the fixpoint grows it); an extern/template/unknown callee is
        TOP (ES-C4)."""
        table = self.error_sets if kind == "error" else self.value_sets
        if name in table:
            return table[name][1]
        fn = self._es_fn_table.get(name)
        if fn is None or fn.is_extern or fn.body is None or getattr(fn, "type_params", None):
            return None
        return frozenset()

    def _es_local_for_ann(self, ann, t):
        """The locals-table entry for a `let`: the annotation (when
        present) fixes the kind/enum; the set comes from the
        initializer, coerced to that enum (unknown -> TOP). Without an
        annotation the initializer's tuple is used as-is."""
        if ann is None:
            return t
        kind, enum = self._es_kind_of_type(ann)
        if kind == "other":
            return (ann, "other", "", None)
        _t2, k2, e2, m2 = t
        if k2 == kind and e2 == enum:
            return (ann, kind, enum, m2)
        return (ann, kind, enum, None)

    def _es_lookup(self, name):
        """Locals-table entry for a name, or None."""
        for scope in reversed(self._es_scopes):
            if name in scope:
                return scope[name]
        return None

    def _es_acc_add_error(self, s):
        """Add a `?`-propagated error set to the enclosing accumulator
        (ES-C2b)."""
        if self._es_acc_err is None:
            return
        E = self._es_acc_err[0]
        enum, members = s
        if enum == E:
            self._es_acc_err = self._es_union(self._es_acc_err, (E, members))
        else:
            # A `?` whose E differs from the enclosing ret's E: phase 1
            # rejects this, so it cannot occur; TOP defensively.
            self._es_acc_err = (E, None)

    def _es_acc_add_return(self, t):
        """Contribute a returned expression's set to the enclosing
        function's accumulator (ES-C2a/c/d). Anything the walker
        cannot prove about the returned value widens to TOP of the
        enclosing enum (sound: phase 1 already proved the value HAS
        the return type)."""
        _typ, kind, enum, members = t
        if self._es_acc_err is not None:
            E = self._es_acc_err[0]
            if kind == "result" and enum == E:
                self._es_acc_err = self._es_union(self._es_acc_err, (E, members))
            else:
                self._es_acc_err = (E, None)
        if self._es_acc_val is not None:
            E = self._es_acc_val[0]
            if kind == "enum" and enum == E:
                self._es_acc_val = self._es_union(self._es_acc_val, (E, members))
            else:
                self._es_acc_val = (E, None)

    def _es_assign_union(self, name, t):
        """Reassignment unions the new value's set into the local
        (ES-C3: sets only grow). A value the walker cannot track
        widens the local to TOP of its enum."""
        for scope in reversed(self._es_scopes):
            if name in scope:
                _typ, kind, enum, members = scope[name]
                if kind in ("result", "enum"):
                    _t2, k2, e2, m2 = t
                    if k2 == kind and e2 == enum:
                        new_members = (members | m2) if (members is not None and m2 is not None) else None
                        scope[name] = (_typ, kind, enum, new_members)
                    else:
                        scope[name] = (_typ, kind, enum, None)
                return

    def _es_expr(self, expr):
        """(typ, kind, enum, members) for an expression. `?`
        contributions are added to the enclosing accumulator as a side
        effect (ES-C2b)."""
        if isinstance(expr, A.Var):
            v = self._es_lookup(expr.name)
            if v is not None:
                return v
            if expr.name in self.enum_variants:
                e = self.enum_variants[expr.name]
                return (e, "enum", e, frozenset([expr.name]))
            # A bare function name is a fn value (FN-C1): never an
            # enum/Result value.
            return ("?", "other", "", None)
        if isinstance(expr, A.Call):
            return self._es_call(expr)
        if isinstance(expr, A.StructLit):
            return self._es_structlit(expr)
        if isinstance(expr, A.FieldAccess):
            return self._es_fieldaccess(expr)
        if isinstance(expr, A.Try):
            _t, kind, enum, members = self._es_expr(expr.expr)
            if kind == "result" and enum:
                # ES-C2b: `?` propagates the inner Result's error set
                # to the enclosing function.
                self._es_acc_add_error((enum, members))
            return ("?", "other", "", None)
        if isinstance(expr, A.MethodCall):
            return self._es_methodcall(expr)
        if isinstance(expr, A.IndirectCall):
            return self._es_indirectcall(expr)
        if isinstance(expr, A.Lambda):
            # ES-C8: a lambda value flowing into a call contributes
            # TOP; its body summary is unobservable in v1 (a lambda is
            # only ever called indirectly, which is TOP by ES-C4), so
            # the body is not walked for the enclosing function: its
            # `?`s belong to the lambda, not the enclosing function.
            return ("?", "other", "", None)
        if isinstance(expr, A.BinOp):
            self._es_expr(expr.left)
            self._es_expr(expr.right)
            return ("?", "other", "", None)
        if isinstance(expr, A.UnaryOp):
            self._es_expr(expr.expr)
            return ("?", "other", "", None)
        if isinstance(expr, A.Cast):
            self._es_expr(expr.expr)
            kind, enum = self._es_kind_of_type(expr.target)
            return (expr.target, kind, enum, None)
        if isinstance(expr, A.Index):
            bt, _bk, _be, _bs = self._es_expr(expr.base)
            self._es_expr(expr.index)
            # Array elements widen to TOP (ES-C4); the element type
            # comes from the array type string when known.
            if bt.startswith("[") and bt.endswith("]"):
                et = bt[1:-1]
                kind, enum = self._es_kind_of_type(et)
                return (et, kind, enum, None)
            return ("?", "other", "", None)
        if isinstance(expr, A.TupleIndex):
            self._es_expr(expr.base)
            return ("?", "other", "", None)
        if isinstance(expr, (A.ArrayLit, A.TupleLit)):
            for e in expr.elems:
                self._es_expr(e)
            return ("?", "other", "", None)
        if isinstance(expr, A.RangeLit):
            self._es_expr(expr.start)
            self._es_expr(expr.end)
            return ("?", "other", "", None)
        # IntLit, FloatLit, StrLit, BoolLit (and anything else): a
        # value, never an enum/Result.
        return ("?", "other", "", None)

    def _es_call(self, call):
        # Variant construction first (mirrors check_call order).
        if call.name in self.enum_variants:
            for a in call.args:
                self._es_expr(a)
            e = self.enum_variants[call.name]
            return (e, "enum", e, frozenset([call.name]))
        if call.name == "try_call":
            # Result<R, str> — E is str, never set-bearing. Walk only
            # the value args (arg 0 is a bare fn name).
            for a in call.args[1:]:
                self._es_expr(a)
            return ("?", "other", "", None)
        fn = self._es_fn_table.get(call.name)
        if fn is not None:
            # Direct call to a known function (a same-named function
            # wins over a same-named local, as in check_call).
            for a in call.args:
                self._es_expr(a)
            self._es_callees.add(call.name)
            ret = fn.ret
            kind, enum = self._es_kind_of_type(ret)
            if kind == "result":
                return (ret, "result", enum, self._es_summary_members(call.name, "error"))
            if kind == "enum":
                return (ret, "enum", enum, self._es_summary_members(call.name, "value"))
            return (ret, "other", "", None)
        lv = self._es_lookup(call.name)
        if lv is not None and is_fn_type(lv[0]):
            # Indirect call through a fn-typed variable (FN-C2): the
            # callee is unknown at the call site — TOP (ES-C4).
            for a in call.args:
                self._es_expr(a)
            parts = fn_parts(lv[0])
            ret = parts[1] if parts else "?"
            kind, enum = self._es_kind_of_type(ret)
            return (ret, kind, enum, None)
        # Builtins (and anything unknown): never enum/Result-typed in
        # a set-bearing way. Walk args for `?`s.
        for a in call.args:
            self._es_expr(a)
        return ("?", "other", "", None)

    def _es_structlit(self, node):
        tuples = {}
        for fname, fexpr in node.fields:
            tuples[fname] = self._es_expr(fexpr)
        ct = node.concrete_type or node.name
        rp = self._es_result_parts(ct)
        if rp is None:
            return ("?", "other", "", None)
        _T, E = rp
        if self._es_enum_base(E) is None:
            return (ct, "other", "", None)
        field_nodes = dict(node.fields)
        ok_node = field_nodes.get("ok")
        if isinstance(ok_node, A.BoolLit) and ok_node.value is True:
            # Definitely an Ok: the dummy error value can never be
            # produced as an error, so this literal contributes nothing.
            return (ct, "result", E, frozenset())
        err_t = tuples.get("error")
        if err_t is None:
            return (ct, "result", E, None)
        _t, kind, enum, members = err_t
        if kind == "enum" and enum == E:
            return (ct, "result", E, members)
        # The error value is not an enum value the walker can track
        # (struct field, computed expr, ...): TOP (ES-C4).
        return (ct, "result", E, None)

    def _es_fieldaccess(self, node):
        bt, bk, be, bs = self._es_expr(node.base)
        if bk == "result" and node.field == "error":
            return (be, "enum", be, bs)
        if bk == "result":
            # .value / .ok: the Ok payload / flag — not a tracked set.
            return ("?", "other", "", None)
        if bk == "other" and bt:
            # A struct field read: look up the field's type. A Result /
            # enum field widens to TOP (ES-C4: values flowing through
            # struct fields are untracked).
            fields = self.struct_fields_for(bt)
            if fields is not None and node.field in fields:
                ft = fields[node.field]
                kind, enum = self._es_kind_of_type(ft)
                if kind != "other":
                    return (ft, kind, enum, None)
        return ("?", "other", "", None)

    def _es_methodcall(self, node):
        from .traits import mangle
        bt, _bk, _be, _bs = self._es_expr(node.base)
        for a in node.args:
            self._es_expr(a)
        if not bt or "<" in bt or bt not in self.method_types:
            return ("?", "other", "", None)
        methods = self.method_types[bt]
        if node.method not in methods:
            return ("?", "other", "", None)
        _params, ret = methods[node.method]
        mangled = mangle(bt, node.method)
        self._es_callees.add(mangled)
        kind, enum = self._es_kind_of_type(ret)
        if kind == "result":
            return (ret, "result", enum, self._es_summary_members(mangled, "error"))
        if kind == "enum":
            return (ret, "enum", enum, self._es_summary_members(mangled, "value"))
        return (ret, "other", "", None)

    def _es_indirectcall(self, node):
        # The callee is a computed fn value: unknown at the call site
        # — TOP (ES-C4). The return type comes from the checker's
        # stamped fn type when known.
        ft = node.fn_type or "?"
        ct, _ck, _ce, _cs = self._es_expr(node.callee)
        for a in node.args:
            self._es_expr(a)
        if ft == "?":
            ft = ct
        parts = fn_parts(ft) if ft and ft != "?" else None
        ret = parts[1] if parts else "?"
        kind, enum = self._es_kind_of_type(ret)
        return (ret, kind, enum, None)

    def _es_walk_block(self, block):
        self._es_scopes.append({})
        for stmt in block.stmts:
            self._es_walk_stmt(stmt)
        self._es_scopes.pop()

    def _es_branch_merge(self, before, afters):
        """Merge locals after a branch: `before` is the snapshot stack
        (list of dicts), `afters` the end-stacks, one per arm. Each name
        present before the branch ends with the union of its set across
        the arms (sets only grow, ES-C3); names declared inside an arm
        disappear."""
        merged = [dict(d) for d in before]
        for i, scope in enumerate(before):
            for name, val in scope.items():
                acc = val
                for after in afters:
                    if i < len(after) and name in after[i]:
                        other = after[i][name]
                        if acc[1] == other[1] and acc[1] in ("result", "enum"):
                            m1, m2 = acc[3], other[3]
                            acc = (acc[0], acc[1], acc[2] or other[2],
                                   (m1 | m2) if (m1 is not None and m2 is not None) else None)
                merged[i][name] = acc
        self._es_scopes = merged

    def _es_match_payload_type(self, enum_base, pat):
        """Payload type of a match arm's binding, with the scrutinee's
        concrete type args substituted when known; None when the
        variant has no payload or the enum is unknown."""
        if not enum_base or enum_base not in self.enum_payloads:
            return None
        pt = self.enum_payloads[enum_base].get(pat)
        if pt is None:
            return None
        return pt

    def _es_walk_stmt(self, stmt):
        if isinstance(stmt, A.Block):
            self._es_walk_block(stmt)
            return
        if isinstance(stmt, A.Let):
            t = self._es_expr(stmt.expr)
            self._es_scopes[-1][stmt.name] = self._es_local_for_ann(stmt.ann, t)
            return
        if isinstance(stmt, A.Assign):
            t = self._es_expr(stmt.expr)
            self._es_assign_union(stmt.name, t)
            return
        if isinstance(stmt, A.IndexAssign):
            self._es_expr(stmt.base)
            self._es_expr(stmt.expr)
            return
        if isinstance(stmt, A.FieldAssign):
            self._es_expr(stmt.target)
            self._es_expr(stmt.expr)
            return
        if isinstance(stmt, A.Return):
            if stmt.expr is not None:
                self._es_acc_add_return(self._es_expr(stmt.expr))
            return
        if isinstance(stmt, A.If):
            self._es_expr(stmt.cond)
            before = [dict(d) for d in self._es_scopes]
            self._es_scopes = [dict(d) for d in before]
            self._es_walk_block(stmt.then)
            then_end = self._es_scopes
            self._es_scopes = [dict(d) for d in before]
            if stmt.els is not None:
                self._es_walk_block(stmt.els)
                else_end = self._es_scopes
            else:
                else_end = [dict(d) for d in before]
            self._es_branch_merge(before, [then_end, else_end])
            return
        if isinstance(stmt, A.While):
            self._es_expr(stmt.cond)
            before = [dict(d) for d in self._es_scopes]
            self._es_scopes = [dict(d) for d in before]
            self._es_walk_block(stmt.body)
            self._es_branch_merge(before, [self._es_scopes])
            return
        if isinstance(stmt, A.For):
            it, _ik, _ie, _im = self._es_expr(stmt.expr)
            if it.startswith("[") and it.endswith("]"):
                et = it[1:-1]
            else:
                et = "?"
            kind, enum = self._es_kind_of_type(et)
            before = [dict(d) for d in self._es_scopes]
            self._es_scopes = [dict(d) for d in before]
            # The loop variable comes from an array element: TOP (ES-C4).
            self._es_scopes.append({stmt.name: (et, kind, enum, None)})
            self._es_walk_block(stmt.body)
            self._es_scopes.pop()
            self._es_branch_merge(before, [self._es_scopes])
            return
        if isinstance(stmt, A.Match):
            st, _sk, se, sm = self._es_expr(stmt.expr)
            rec = self._pending_matches.get(id(stmt))
            if self._es_verdicts and rec is not None:
                _fn_name, base, seen, has_wildcard = rec
                enum = se or base
                if sm is None:
                    variants = set(self.enums.get(enum, []))
                else:
                    variants = set(sm)
                if not has_wildcard:
                    missing = sorted(variants - set(seen))
                    if missing:
                        raise ForgeError(
                            f"match is not exhaustive; missing: {', '.join(missing)}",
                            stmt.line, stmt.col)
            before = [dict(d) for d in self._es_scopes]
            afters = []
            for (pat, body) in stmt.arms:
                self._es_scopes = [dict(d) for d in before]
                if pat.kind == "variant" and pat.binding:
                    # The binding is the payload of the matched variant;
                    # its set is untracked (TOP) — the scrutinee's set
                    # says which VARIANTS occur, not what payloads they
                    # carry. Its type comes from the enum payload table
                    # (generic enums: substitute the scrutinee's type
                    # args when known).
                    pt = self._es_match_payload_type(se or (rec[1] if rec else ""), pat.value)
                    if pt is not None and st:
                        g = parse_generic(st)
                        base = self._es_enum_base(st)
                        if g is not None and base:
                            params = self.enum_params.get(base, [])
                            if len(params) == len(g[1]):
                                pt = substitute_type(pt, dict(zip(params, g[1])))
                    kind, enum = self._es_kind_of_type(pt) if pt else ("other", "")
                    self._es_scopes.append({pat.binding: (pt or "?", kind, enum, None)})
                    self._es_walk_block(body)
                    self._es_scopes.pop()
                elif pat.kind == "struct":
                    # Struct-pattern field bindings (#69): in scope
                    # with the fields' (substituted) types.
                    fields = self.struct_fields_for(st) or {}
                    scope = {}
                    for fname, fp in (pat.fields or []):
                        if fp.kind == "binding" and fname in fields:
                            ft = fields[fname]
                            kind, enum = self._es_kind_of_type(ft)
                            scope[fp.value] = (ft, kind, enum, None)
                    if scope:
                        self._es_scopes.append(scope)
                    self._es_walk_block(body)
                    if scope:
                        self._es_scopes.pop()
                else:
                    self._es_walk_block(body)
                afters.append(self._es_scopes)
            self._es_branch_merge(before, afters)
            return
        if isinstance(stmt, A.Spawn):
            # Only the call's arguments are evaluated in the enclosing
            # function; the callee's own `?`s belong to the spawned task.
            for a in stmt.call.args:
                self._es_expr(a)
            return
        if isinstance(stmt, A.Scope):
            self._es_walk_block(stmt.body)
            return
        if isinstance(stmt, A.Defer):
            # The deferred call's result is discarded; its arguments'
            # `?`s are evaluated in the enclosing function.
            self._es_expr(stmt.call)
            return
        if isinstance(stmt, A.ExprStmt):
            self._es_expr(stmt.expr)
            return
        # Break / Continue: nothing to track.
        return

    def _es_walk_fn(self, fn, verdicts):
        """Walk one concrete function body. Returns (err_set, val_set,
        callees): the accumulated summaries (or None when the return
        type is not set-bearing) and the callee names encountered.
        `verdicts` issues deferred match verdicts (final walk only)."""
        ret = fn.ret
        rp = self._es_result_parts(ret)
        if rp is not None and self._es_enum_base(rp[1]) is not None:
            self._es_acc_err = (rp[1], frozenset())
            self._es_acc_val = None
        elif self._es_enum_base(ret) is not None:
            self._es_acc_err = None
            self._es_acc_val = (ret, frozenset())
        else:
            self._es_acc_err = None
            self._es_acc_val = None
        self._es_scopes = [{}]
        self._es_callees = set()
        self._es_verdicts = verdicts
        self._es_fn = fn
        for (pn, pt) in fn.params:
            # Params are untracked sources: TOP of their enum (ES-C3).
            self._es_scopes[0][pn] = self._es_local_for_ann(
                pt, ("?", "other", "", None))
        if fn.body is not None:
            self._es_walk_block(fn.body)
        err = self._es_acc_err
        val = self._es_acc_val
        callees = self._es_callees
        self._es_scopes = [{}]
        self._es_callees = set()
        self._es_verdicts = False
        return err, val, callees

    def _infer_error_sets(self):
        """Second pass (ES-C6): worklist fixpoint over the call graph,
        then the deferred match verdicts (ES-C5) and the dump flag."""
        from collections import deque
        self._es_fn_table = {fn.name: fn for fn in self.program.funcs}
        walkable = []
        for fn in self.program.funcs:
            if fn.body is None or fn.is_extern:
                continue
            if getattr(fn, "type_params", None):
                continue  # generic template: checked only on instantiation
            walkable.append(fn)
        self.error_sets = {}
        self.value_sets = {}
        callers = {}  # callee name -> set of caller names
        worklist = deque([fn.name for fn in walkable])
        in_worklist = set(worklist)
        steps = 0
        bound_hit = False
        while worklist:
            name = worklist.popleft()
            in_worklist.discard(name)
            steps += 1
            if steps > 10000:
                bound_hit = True
                break
            fn = self._es_fn_table[name]
            err, val, callees = self._es_walk_fn(fn, verdicts=False)
            for callee in callees:
                callers.setdefault(callee, set()).add(name)
            grew = False
            if err is not None:
                old = self.error_sets.get(name)
                old_members = old[1] if old is not None else frozenset()
                if err[1] != old_members:
                    grew = True
                self.error_sets[name] = err
            if val is not None:
                old = self.value_sets.get(name)
                old_members = old[1] if old is not None else frozenset()
                if val[1] != old_members:
                    grew = True
                self.value_sets[name] = val
            if grew:
                for caller in callers.get(name, ()):
                    if caller not in in_worklist:
                        worklist.append(caller)
                        in_worklist.add(caller)
        if bound_hit:
            # Widen every not-yet-stable summary to TOP (sound, ES-C4).
            self._es_bound_hit = True
            for fn in walkable:
                if fn.name in self.error_sets:
                    enum, _m = self.error_sets[fn.name]
                    self.error_sets[fn.name] = (enum, None)
                if fn.name in self.value_sets:
                    enum, _m = self.value_sets[fn.name]
                    self.value_sets[fn.name] = (enum, None)
        # Final verdict walk (ES-C5): re-walk every function holding a
        # deferred match, with final summaries, issuing verdicts.
        pending_fns = {rec[0] for rec in self._pending_matches.values() if rec[0]}
        for fn in walkable:
            if fn.name in pending_fns:
                self._es_walk_fn(fn, verdicts=True)
        if self.dump_error_sets:
            self._es_dump()

    def _es_format_set(self, enum, members):
        if members is None:
            return "TOP"
        if not members:
            return "{}"
        order = self.enums.get(enum, [])
        names = [v for v in order if v in members]
        names += sorted(m for m in members if m not in order)
        return "{" + ", ".join(names) + "}"

    def _es_dump(self):
        """Print inferred sets to stderr (qasida check --dump-error-sets):
        one line per function with a set-bearing return, in program
        order: `fn <name> -> Result<_, E>: {A, B}` or `TOP` or `{}`."""
        import sys
        for fn in self.program.funcs:
            if fn.name in self.error_sets:
                enum, members = self.error_sets[fn.name]
                _T, E = self._es_result_parts(fn.ret)
                sys.stderr.write(
                    f"fn {fn.name} -> Result<_, {E}>: "
                    f"{self._es_format_set(enum, members)}\n")
            elif fn.name in self.value_sets:
                enum, members = self.value_sets[fn.name]
                sys.stderr.write(
                    f"fn {fn.name} -> {fn.ret}: "
                    f"{self._es_format_set(enum, members)}\n")

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
                for _pat, body in stmt.arms:
                    self._substitute_let_ann(body, bindings)
        # Lambda param/return types (Top-500 #101, CL-C7): a lambda
        # inside a generic function may mention type parameters;
        # substitute them before the body is checked (the generic
        # walk reaches lambdas nested in any expression).
        def walk(node):
            if isinstance(node, A.Lambda):
                node.params = [(n, substitute_type(t, bindings))
                               for n, t in node.params]
                node.ret = substitute_type(node.ret, bindings)
            if isinstance(node, (list, tuple)):
                for x in node:
                    walk(x)
                return
            if isinstance(node, dict):
                for v in node.values():
                    walk(v)
                return
            if hasattr(node, "__dict__"):
                for v in vars(node).values():
                    walk(v)
        walk(block)

    def check_func(self, fn):
        # Save outer state: checking a generic instantiation can happen
        # in the middle of checking another function (a call site), and
        # must not wipe that function's scopes/return type.
        saved = (self.scopes, self.current_ret, self.current_fn, self.current_file, self.current_type_params,
                 self.loop_depth, self.branch_depth, self.moved, self.unresolved,
                 self.moved_fields, self.loop_vars, self.pinned,
                 self._for_iterables, self._lambda_frames, self.label_stack,
                 self._loop_var_entries)
        try:
            if fn.name in C_KEYWORDS:
                raise ForgeError(f"'{fn.name}' is a C keyword and cannot be used as a "
                                 f"function name; rename it", fn.line, fn.col)
            self.current_type_params = list(getattr(fn, "type_params", None) or [])
            self.loop_depth = 0
            self.branch_depth = 0
            self.label_stack = []
            self.moved = set()
            self.moved_fields = set()
            self.pinned = set()
            self.loop_vars = []
            self._loop_var_entries = set()
            self._for_iterables = []
            self._lambda_frames = []
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
            if fn.name == "crash_handler":
                # Top-500 #60 (stage B): the freestanding crash
                # hook. A top-level fn with this name IS the hook,
                # so its shape is enforced here, in both compilers:
                # exactly (code: int, pc: int) -> void, not generic,
                # not extern, freestanding only (hosted fail()
                # already prints and exits; there is nothing to hook).
                if getattr(fn, "type_params", None):
                    raise ForgeError("crash_handler() cannot be generic "
                                     "(the hook signature is (int, int) -> void)",
                                     fn.line, fn.col)
                if getattr(fn, "is_extern", False):
                    raise ForgeError("crash_handler() must be defined in Qasida "
                                     "(an extern declaration is not a hook)",
                                     fn.line, fn.col)
                if not self.freestanding:
                    raise ForgeError("crash_handler() is a freestanding-only hook "
                                     "(not in hosted mode)",
                                     fn.line, fn.col)
                if (len(fn.params) != 2 or fn.params[0][1] != "int"
                        or fn.params[1][1] != "int" or fn.ret != "void"):
                    raise ForgeError("crash_handler() must take exactly "
                                     "(code: int, pc: int) and return nothing",
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
            self.current_file = getattr(fn, "file", "")
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
            self.scopes, self.current_ret, self.current_fn, self.current_file, self.current_type_params, \
                self.loop_depth, self.branch_depth, self.moved, self.unresolved, \
                self.moved_fields, self.loop_vars, self.pinned, \
                self._for_iterables, self._lambda_frames, self.label_stack, \
                self._loop_var_entries = saved

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

    def _fn_value_type(self, name, line, col):
        """Fn type of a named function used as a value (FN-C1).

        A bare function name in value position has the type of its
        signature. Generic functions cannot be values (no
        instantiation from a bare name in v1); extern functions
        cannot be values (their C ABI type differs from the Qasida
        fn type, so the typedef would be the wrong signature).
        """
        fn = self.funcs[name]
        if getattr(fn, "type_params", None):
            raise ForgeError(f"generic function '{name}' cannot be used as a value; "
                             f"call it (the call instantiates it)",
                             line, col)
        if getattr(fn, "is_extern", False):
            raise ForgeError(f"extern function '{name}' cannot be used as a value "
                             f"(its C ABI type differs from the Qasida type)",
                             line, col)
        return fn_type_string(fn.params, fn.ret)

    def _eval_pred(self, pred):
        """Evaluate a comptime-if predicate against this check's
        Target (Top-500 #70). The parser admits only the fixed
        set, so every kind here is known; an undecidable condition
        is impossible by construction (F6)."""
        k = pred.kind
        if k == "and":
            return self._eval_pred(pred.kids[0]) and self._eval_pred(pred.kids[1])
        if k == "or":
            return self._eval_pred(pred.kids[0]) or self._eval_pred(pred.kids[1])
        if k == "not":
            return not self._eval_pred(pred.kids[0])
        if k == "debug":
            return self.target.debug
        if k == "freestanding":
            return self.target.freestanding
        actual = {"target": self.target.target, "arch": self.target.arch,
                  "os": self.target.os, "mode": self.target.mode}[k]
        if pred.op == "==":
            return actual == pred.value
        return actual != pred.value

    def _resolve_comptime_if(self, stmt):
        """The taken branch's statements for a ComptimeIf (Top-500
        #70): the `else comptime if` chain is a one-statement Block
        wrapping a nested ComptimeIf, so it resolves recursively.
        The discarded branch is never returned — it is parsed only,
        never checked or compiled (F1)."""
        if self._eval_pred(stmt.pred):
            return list(stmt.then.stmts)
        if stmt.els is None:
            return []
        if (len(stmt.els.stmts) == 1
                and isinstance(stmt.els.stmts[0], A.ComptimeIf)):
            return self._resolve_comptime_if(stmt.els.stmts[0])
        return list(stmt.els.stmts)

    def _check_stmts(self, stmts):
        """Check a statement list, splicing each ComptimeIf in place
        (Top-500 #70): the statement is replaced by the taken
        branch's statements, which are then checked in the SAME
        enclosing context — the same scope, the same label stack,
        the same defer frames — so a `let` in the taken branch is
        visible after the if and a spliced-in `return`/`break`
        satisfies the enclosing checks. The splice mutates the
        list object, so infer/codegen (which walk the same
        program) see resolved code and never meet a ComptimeIf."""
        i = 0
        while i < len(stmts):
            stmt = stmts[i]
            if isinstance(stmt, A.ComptimeIf):
                stmts[i:i + 1] = self._resolve_comptime_if(stmt)
                continue
            self.check_stmt(stmt)
            i += 1

    def check_block(self, block):
        self.scopes.append({})
        self._check_stmts(block.stmts)
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

    def _scope_id_for(self, name):
        """id() of the scope dict that binds `name`, or None —
        the same name in an inner scope is a different binding."""
        if name is None:
            return None
        for scope in reversed(self.scopes):
            if name in scope:
                return id(scope)
        return None

    def _scope_index_for(self, name):
        """Index into self.scopes of the innermost scope binding
        `name`, or None (Top-500 #101: capture detection compares
        this index against the lambda frames' boundaries)."""
        if name is None:
            return None
        for i in range(len(self.scopes) - 1, -1, -1):
            if name in self.scopes[i]:
                return i
        return None

    def _record_capture(self, name):
        """Record `name` as a capture of every enclosing lambda
        frame whose boundary is above the name's binding scope
        (Top-500 #101, CL-C2): the transitive chain nested lambdas
        need — an inner lambda reads the value through the outer
        env. Shared by the Var branch and check_call's indirect
        path (a call callee is a name, not a Var node, so the Var
        branch never sees it — without this, `f(x)` inside a lambda
        where `f` is an outer variable would have no env slot)."""
        scope_idx = self._scope_index_for(name)
        if scope_idx is not None:
            for frame in self._lambda_frames:
                if scope_idx < frame["boundary"]:
                    if name not in frame["captures"]:
                        frame["captures"][name] = \
                            self.scopes[scope_idx][name][0]

    def _for_iterable_conflict(self, arg):
        """True when moving `arg` would break an enclosing for
        loop that is iterating over it (Top-500 #40): the loop
        reads the iterable's buffer again on the next iteration,
        after the moved-to binding's scope-end free. The move
        target overlaps the iterable when it is the same path,
        or one contains the other (moving a struct moves its
        fields with it)."""
        if isinstance(arg, A.Var):
            root, path = arg.name, arg.name
        elif isinstance(arg, A.FieldAccess):
            path = self._field_path(arg)
            root = path.split(".")[0] if path else None
        else:
            return False
        if root is None or path is None:
            return False
        scope_id = self._scope_id_for(root)
        for iscope, name, ipath in self._for_iterables:
            if name != root or iscope != scope_id:
                continue
            if ipath is None or ipath == path \
                    or ipath.startswith(path + ".") \
                    or path.startswith(ipath + "."):
                return True
        return False

    def _is_owned_type(self, t):
        """The move predicate (Top-500 #27): the types whose
        values carry a hold — arrays, str, structs, tuples.
        Fn types join it under closures (Top-500 #101, CL-C4):
        a closure value holds its env, so it moves like an
        array and is freed when its last holder dies."""
        return (elem_type(t) is not None or t == "str" or is_tuple_type(t)
                or is_fn_type(t)
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
        if isinstance(stmt, A.ComptimeIf):
            # Top-500 #70: unreachable — _check_stmts splices
            # every ComptimeIf before check_stmt sees it. A
            # ComptimeIf here means a new statement-list walker
            # was added without going through _check_stmts.
            raise ForgeError("internal error: unresolved comptime if",
                             stmt.line, stmt.col)
        if isinstance(stmt, A.Block):
            self.check_block(stmt)
            return
        if isinstance(stmt, A.Let):
            if stmt.name in C_KEYWORDS:
                raise ForgeError(f"'{stmt.name}' is a C keyword and cannot be used as a "
                                 f"variable name; rename it", stmt.line, stmt.col)
            # Top-500 #494: a name already in this scope is a
            # rebind, not a duplicate — decided after the RHS is
            # checked (it still reads the OLD binding). EXCEPT a
            # loop variable: the For handler checks the body in
            # the loop-var scope, and `let i = i + 1` inside a
            # `for i` body would miscompile in C (the initializer
            # reads the new variable, not the loop var — the same
            # pre-existing trap as nested-block shadows that read
            # the shadowed name). Loop-var shadowing keeps the
            # old duplicate error; the hosted checker still
            # accepts it (pre-existing divergence, documented
            # in the #494 entry).
            old_entry = self.scopes[-1].get(stmt.name)
            if (old_entry is not None
                    and (id(self.scopes[-1]), stmt.name) in self._loop_var_entries):
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
            if old_entry is not None:
                # Top-500 #494: same-scope shadowing. The RHS above
                # still read the OLD binding; the new binding takes
                # over from here. Same type only in v1 (the C
                # variable keeps its declared type); a different
                # type is rejected plainly, as is shadowing a
                # pinned binding (pin forbids replacing the value).
                if stmt.name in self.pinned:
                    raise ForgeError(f"cannot shadow pinned variable '{stmt.name}' "
                                     f"(pin forbids replacing the value; change it "
                                     f"in place through its fields or indexes)",
                                     stmt.line, stmt.col)
                if (isinstance(stmt.expr, A.ArrayLit) and not stmt.expr.elems
                        and stmt.ann is None):
                    # An empty literal carries no element type for
                    # the codegen (the infer pass only propagates
                    # annotations), so a rebind needs one too —
                    # the same error as a fresh empty let.
                    raise ForgeError("cannot infer the element type of an empty array "
                                     "literal; add an annotation, e.g. let x: [int] = []",
                                     stmt.line, stmt.col)
                elif t != old_entry[0]:
                    raise ForgeError(f"cannot shadow '{stmt.name}' with a different type "
                                     f"in v1 (was {old_entry[0]}, now {t}); declare it in "
                                     f"a nested block or use a new name",
                                     stmt.line, stmt.col)
                stmt.rebind = True
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
                    and stmt.ann is None and not stmt.rebind):
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
            if self._lambda_frames:
                # Assignment to a captured binding (Top-500 #101,
                # CL-C3): closures capture by value and the binding
                # is read-only inside the lambda in v1. A name
                # resolving outside the innermost frame's boundary
                # is a capture of that lambda.
                scope_idx = self._scope_index_for(stmt.name)
                if (scope_idx is not None
                        and scope_idx < self._lambda_frames[-1]["boundary"]):
                    raise ForgeError(f"cannot assign to captured variable '{stmt.name}' "
                                     f"(closures capture by value; captured variables "
                                     f"are read-only in v1)",
                                     stmt.line, stmt.col)
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
                # Assigning a whole intermediate struct revives
                # its fields too (Top-500 #40): replacing o.inner
                # replaces o.inner.vals, so a moved field under
                # the target is live again, not just the target.
                self.moved_fields = {p for p in self.moved_fields
                                     if p != target_path
                                     and not p.startswith(target_path + ".")}
            return
        if isinstance(stmt, A.IndexAssign):
            base = stmt.base.base
            if isinstance(base, A.Var):
                # Writing through a moved array's stale pointer
                # is a use-after-move (Top-500 #40): the buffer
                # now belongs to the moved-to binding.
                if base.name in self.moved:
                    raise ForgeError(f"use of moved value '{base.name}'",
                                     stmt.line, stmt.col)
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
                for idx, (pat, body) in enumerate(stmt.arms):
                    if pat.kind == "wildcard":
                        has_wildcard = True
                        if idx != len(stmt.arms) - 1:
                            raise ForgeError("match wildcard '_' must be the last arm",
                                             stmt.line, stmt.col)
                        self.moved, self.moved_fields, self.pinned = set(match_before_moved), set(match_before_fields), set(match_before_pinned)
                        self.branch_depth += 1
                        try:
                            self.check_block(body)
                        finally:
                            self.branch_depth -= 1
                        match_results.append((set(self.moved), set(self.moved_fields), set(self.pinned)))
                        continue
                    if pat.kind != "variant" or pat.value not in member_set:
                        raise ForgeError(f"'{A.pattern_text(pat)}' is not a member of union '{et}'",
                                         stmt.line, stmt.col)
                    if pat.value in seen:
                        raise ForgeError(f"duplicate match arm '{pat.value}'",
                                         stmt.line, stmt.col)
                    seen.add(pat.value)
                    if pat.binding is None:
                        raise ForgeError(f"member '{pat.value}' has a value; "
                                         f"write {pat.value}(name) => ...",
                                         stmt.line, stmt.col)
                    self.moved, self.moved_fields, self.pinned = set(match_before_moved), set(match_before_fields), set(match_before_pinned)
                    self.scopes.append({pat.binding: (pat.value, False)})
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
            if et in ("int", "bool", "str") or self.struct_fields_for(et) is not None:
                # Top-500 #69: value patterns — int/bool/str literals
                # and struct patterns. First-match-wins; `_` is
                # required for int/str/struct (no finite missing
                # list to name), and for bool unless both literals
                # appear. Value matches skip the #50 ES verdict
                # entirely (no _pending_matches entry).
                fields = self.struct_fields_for(et) or {}
                seen = set()
                has_wildcard = False
                for idx, (pat, body) in enumerate(stmt.arms):
                    if pat.kind == "wildcard":
                        has_wildcard = True
                        if idx != len(stmt.arms) - 1:
                            raise ForgeError("match wildcard '_' must be the last arm",
                                             stmt.line, stmt.col)
                        self.moved, self.moved_fields, self.pinned = set(match_before_moved), set(match_before_fields), set(match_before_pinned)
                        self.branch_depth += 1
                        try:
                            self.check_block(body)
                        finally:
                            self.branch_depth -= 1
                        match_results.append((set(self.moved), set(self.moved_fields), set(self.pinned)))
                        continue
                    key = self._value_pattern_key(pat, et, fields)
                    if key in seen:
                        raise ForgeError(f"duplicate match arm '{A.pattern_text(pat)}'",
                                         pat.line, pat.col)
                    seen.add(key)
                    if pat.kind == "struct":
                        scope = {fp.value: (fields[fname], False)
                                 for fname, fp in (pat.fields or [])
                                 if fp.kind == "binding"}
                        self.moved, self.moved_fields, self.pinned = set(match_before_moved), set(match_before_fields), set(match_before_pinned)
                        self.scopes.append(scope)
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
                if not has_wildcard:
                    if not (et == "bool"
                            and seen == {("lit_bool", True), ("lit_bool", False)}):
                        raise ForgeError(
                            f"match on {et} is not exhaustive; a '_' arm is required",
                            stmt.line, stmt.col)
                self.moved, self.moved_fields, self.pinned = self._join_moved(
                    match_before_moved, match_before_fields, match_before_pinned, match_results)
                return
            info = self.enum_info_for(et)
            if info is None:
                raise ForgeError(f"match needs an enum, union, int, bool, str, "
                                 f"or struct value, got {et}",
                                 stmt.line, stmt.col)
            _base, variant_info = info
            variants = set(variant_info.keys())
            seen = set()
            has_wildcard = False
            for idx, (pat, body) in enumerate(stmt.arms):
                if pat.kind == "wildcard":
                    has_wildcard = True
                    if idx != len(stmt.arms) - 1:
                        raise ForgeError("match wildcard '_' must be the last arm",
                                         stmt.line, stmt.col)
                    self.moved, self.moved_fields, self.pinned = set(match_before_moved), set(match_before_fields), set(match_before_pinned)
                    self.branch_depth += 1
                    try:
                        self.check_block(body)
                    finally:
                        self.branch_depth -= 1
                    match_results.append((set(self.moved), set(self.moved_fields), set(self.pinned)))
                    continue
                if pat.kind != "variant" or pat.value not in variants:
                    raise ForgeError(f"'{A.pattern_text(pat)}' is not a variant of enum '{et}'"
                                     f"{suggest(A.pattern_text(pat), variants)}",
                                     stmt.line, stmt.col)
                if pat.value in seen:
                    raise ForgeError(f"duplicate match arm '{pat.value}'", stmt.line, stmt.col)
                seen.add(pat.value)
                _tag, payload_type = variant_info[pat.value]
                if payload_type is None and pat.binding is not None:
                    raise ForgeError(f"variant '{pat.value}' has no payload to bind",
                                     stmt.line, stmt.col)
                if payload_type is not None and pat.binding is None:
                    raise ForgeError(f"variant '{pat.value}' has a payload; write {pat.value}(name) => ...",
                                     stmt.line, stmt.col)
                if pat.binding is not None:
                    # Check the arm body with the binding in scope.
                    self.moved, self.moved_fields, self.pinned = set(match_before_moved), set(match_before_fields), set(match_before_pinned)
                    self.scopes.append({pat.binding: (payload_type, False)})
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
            # Top-500 #50: the exhaustiveness verdict moves to the
            # post-fixpoint pass (ES-C5) — the scrutinee's inferred
            # set is only known after the fixpoint. Record the
            # pending match; _es_verdict_matches issues the verdict
            # after _infer_error_sets. (The union branch above keeps
            # its verdict in phase 1: no union-set machinery in v1.)
            self._pending_matches[id(stmt)] = (
                self.current_fn.name if self.current_fn is not None else "",
                _base, frozenset(seen), has_wildcard)
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
            # Top-500 #62: labels shadow (choice 3) — an inner loop
            # may reuse an outer label name; innermost wins while
            # in scope (the stack holds only enclosing labels —
            # popped at loop end). No duplicate-label error.
            pushed_label = False
            if getattr(stmt, "label", None) is not None:
                self.label_stack.append(stmt.label)
                pushed_label = True
            self.loop_depth += 1
            try:
                self.check_block(stmt.body)
                body_moved, body_fields = set(self.moved), set(self.moved_fields)
                body_pinned = set(self.pinned)
            finally:
                self.loop_depth -= 1
                if pushed_label:
                    self.label_stack.pop()
            # Loop-back edge (Top-500 #40): the condition is
            # evaluated again after the body runs, so a value
            # the body moved is dead on the second evaluation —
            # re-check the condition against the post-body moved
            # set. Reassignment in the body revives the value,
            # so body_moved (post-body state) is exactly the set
            # that is dead at the next evaluation.
            saved_moved, saved_fields = self.moved, self.moved_fields
            self.moved, self.moved_fields = set(body_moved), set(body_fields)
            try:
                self.check_expr(stmt.cond)
            finally:
                self.moved, self.moved_fields = saved_moved, saved_fields
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
            # Top-500 #494: mark this scope entry as a loop variable
            # (by scope-dict id + name), so a `let` with the loop
            # var's name in the body keeps the old duplicate error
            # instead of becoming a rebind (which would miscompile:
            # the C initializer would read the new variable).
            self._loop_var_entries.add((id(self.scopes[-1]), stmt.name))
            # Top-500 #62: label stack alongside loop_depth (see
            # While above — labels shadow, no duplicate error).
            pushed_label = False
            if getattr(stmt, "label", None) is not None:
                self.label_stack.append(stmt.label)
                pushed_label = True
            self.loop_depth += 1
            self.loop_vars.append(stmt.name)
            # The iterable's buffer is read again on every
            # iteration (Top-500 #40): record it so a move of
            # it inside the body is rejected in check_call —
            # the moved-to binding's scope-end free would leave
            # the next iteration reading freed memory, even if
            # the body reassigns the variable afterwards (the
            # loop still holds the old buffer). The scope id
            # keeps a shadowing inner binding of the same name
            # from tripping the rule.
            iter_root = self._access_root(stmt.expr)
            iter_path = self._field_path(stmt.expr)
            iter_scope = self._scope_id_for(iter_root) if iter_root is not None else None
            if iter_root is not None:
                self._for_iterables.append((iter_scope, iter_root, iter_path))
            try:
                # Top-500 #70: splice ComptimeIfs in the body in
                # place (the for-var scope above is already pushed,
                # so a spliced-in `let` lands in it, as in
                # check_block).
                self._check_stmts(stmt.body.stmts)
                body_moved, body_fields = set(self.moved), set(self.moved_fields)
                body_pinned = set(self.pinned)
            finally:
                self.loop_depth -= 1
                if pushed_label:
                    self.label_stack.pop()
                self.loop_vars.pop()
                if iter_root is not None:
                    self._for_iterables.pop()
            self._loop_var_entries.discard((id(self.scopes[-1]), stmt.name))
            self.scopes.pop()
            self.moved, self.moved_fields, self.pinned = self._join_moved(
                before_moved, before_fields, before_pinned,
                [(body_moved, body_fields, body_pinned)])
            return
        if isinstance(stmt, A.Break):
            # Top-500 #62: a labeled break must name an enclosing
            # labeled loop; the label stack is function-scoped (reset
            # on fn/lambda entry), so a label from an outer function
            # is invisible here by construction.
            if getattr(stmt, "label", None) is not None:
                if stmt.label not in self.label_stack:
                    raise ForgeError(f"break label '{stmt.label}' does not "
                                     f"name an enclosing loop", stmt.line, stmt.col)
            elif self.loop_depth == 0:
                raise ForgeError("break outside a loop; move it inside a "
                                 "'while' or 'for' loop", stmt.line, stmt.col)
            return
        if isinstance(stmt, A.Continue):
            if getattr(stmt, "label", None) is not None:
                if stmt.label not in self.label_stack:
                    raise ForgeError(f"continue label '{stmt.label}' does not "
                                     f"name an enclosing loop", stmt.line, stmt.col)
            elif self.loop_depth == 0:
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
            if not isinstance(stmt.expr, (A.Call, A.IndirectCall)):
                raise ForgeError("an expression statement must be a function call",
                                 stmt.line, stmt.col)
            call = stmt.expr
            if isinstance(call, A.IndirectCall):
                # handlers[i](x); — an indirect call is not a named
                # builtin, so it goes straight to expression
                # checking (Top-500 #103).
                self.check_expr(call)
                return
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
            # Top-500 #60 (D1): a string literal as the assert()
            # message is exempt from the freestanding heap
            # rejection — it lowers to a static C string (native)
            # or static data (big32), never a heap value. Any
            # other str expression is still rejected freestanding.
            if isinstance(call.args[1], A.StrLit):
                mt = self._check_expr_inner(call.args[1])
            else:
                mt = self.check_expr(call.args[1])
            if mt != "str":
                raise ForgeError("assert() message must be str", call.line, call.col)
            if self.current_fn is not None and self.current_fn.name == "crash_handler":
                raise ForgeError("assert() inside crash_handler() would recurse "
                                 "(a failing hook re-enters the hook); "
                                 "the hook must not fail",
                                 call.line, call.col)
            return
        if call.name in ("print", "println"):
            if self.freestanding:
                raise ForgeError("print/println need the hosted I/O library "
                                 "(not in freestanding v1); use poke32 for MMIO output",
                                 call.line, call.col)
            for a in call.args:
                t = self.check_expr(a)
                if is_fn_type(t):
                    # A function value has no printed form (FN-C6).
                    raise ForgeError("cannot print a function value "
                                     f"(type {t})", call.line, call.col)
            return
        if call.name == "fail":
            # Top-500 #60 (D1): a string literal as the fail()
            # message is exempt from the freestanding heap
            # rejection — it lowers to a static C string (native)
            # or static data (big32), never a heap value. Any
            # other str expression is still rejected freestanding.
            if len(call.args) != 1:
                raise ForgeError("fail() takes exactly one str argument", call.line, call.col)
            if isinstance(call.args[0], A.StrLit):
                mt = self._check_expr_inner(call.args[0])
            else:
                mt = self.check_expr(call.args[0])
            if mt != "str":
                raise ForgeError("fail() takes exactly one str argument", call.line, call.col)
            if self.current_fn is not None and self.current_fn.name == "crash_handler":
                raise ForgeError("fail() inside crash_handler() would recurse "
                                 "(a failing hook re-enters the hook); "
                                 "the hook must not fail",
                                 call.line, call.col)
            return
        if call.name == "fail_compile":
            # Slice 5 driver builtin: a compile-time error. Prints
            # "qasida: error: <msg>" to stderr and exits 1 (the CLI's
            # error prefix, which fail() cannot produce). The hosted
            # lexer/parser/checker report their errors through it.
            if self.freestanding:
                raise ForgeError("fail_compile() writes to stderr "
                                 "(not in freestanding v1)",
                                 call.line, call.col)
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("fail_compile() takes exactly one str argument", call.line, call.col)
            return
        if call.name == "eprintln":
            if self.freestanding:
                raise ForgeError("eprintln needs the hosted I/O library "
                                 "(not in freestanding v1); use poke32 for MMIO output",
                                 call.line, call.col)
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("eprintln() takes exactly one str argument", call.line, call.col)
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
            if self.freestanding:
                raise ForgeError("push() reallocates the heap buffer "
                                 "(not in freestanding v1; freestanding "
                                 "code has no heap allocator)",
                                 call.line, call.col)
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
                # Pushing reallocates the buffer: through a moved
                # array's stale pointer that frees the moved-to
                # binding's buffer (Top-500 #40).
                if call.args[0].name in self.moved:
                    raise ForgeError(f"use of moved value '{call.args[0].name}'",
                                     call.line, call.col)
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
                raise ForgeError(f"pin needs an owned value (array, str, struct, tuple, function value), "
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

    def _heap_backed(self, t, _seen=None):
        """True when a value of type t needs the heap (Top-500 #39).

        str and every array (dynamic, sized, readonly view) are
        heap-backed — sized literals malloc in codegen — as is any
        struct, enum, tuple, union or newtype that carries one,
        transitively. A bare "?" hole or a type parameter is not
        known to be heap-backed, so it passes here; the concrete
        value is caught when it is built.
        """
        if not t or t in ("?", "void", "range"):
            return False
        if _seen is None:
            _seen = set()
        if t in _seen:
            return False
        _seen = _seen | {t}
        if t == "str":
            return True
        if is_readonly(t):
            return self._heap_backed(readonly_inner(t), _seen)
        if is_sized_array(t):
            return True
        if t.startswith("[") and t.endswith("]"):
            return True
        if is_union_type(t):
            return any(self._heap_backed(m, _seen)
                       for m in union_members(t))
        if is_tuple_type(t):
            return any(self._heap_backed(e, _seen)
                       for e in tuple_elems(t))
        if t in self.newtype_targets:
            return self._heap_backed(self.newtype_targets[t], _seen)
        fields = self.struct_fields_for(t)
        if fields is not None:
            return any(self._heap_backed(ft, _seen)
                       for ft in fields.values())
        g = parse_generic(t)
        if g is not None:
            base, args = g
            if base in self.enums:
                params = self.enum_params.get(base, [])
                if len(args) == len(params):
                    payloads = self.enum_payloads.get(base, {})
                    bindings = dict(zip(params, args))
                    return any(
                        pt is not None
                        and self._heap_backed(
                            substitute_type(pt, bindings), _seen)
                        for pt in payloads.values())
            return False
        if t in self.enums:
            return any(pt is not None
                       and self._heap_backed(pt, _seen)
                       for pt in self.enum_payloads.get(t, {}).values())
        return False

    def _heap_error(self, expr, t):
        """Named freestanding error for a heap-backed expression."""
        hint = ("(not in freestanding v1; freestanding code has no "
                "heap allocator)")
        if isinstance(expr, A.StrLit):
            return f"string literal allocates on the heap {hint}"
        if isinstance(expr, A.ArrayLit):
            return f"array literal allocates on the heap {hint}"
        if isinstance(expr, A.BinOp) and expr.op == "+" and t == "str":
            return f"string concatenation allocates on the heap {hint}"
        if isinstance(expr, A.Call):
            return (f"call to '{expr.name}' returns heap-backed type "
                    f"'{t}' {hint}")
        if isinstance(expr, A.Var):
            return (f"variable '{expr.name}' has heap-backed type "
                    f"'{t}' {hint}")
        if isinstance(expr, A.StructLit):
            return (f"struct value '{expr.name}' carries heap-backed "
                    f"fields (type '{t}') {hint}")
        return (f"expression of heap-backed type '{t}' allocates on "
                f"the heap {hint}")

    def check_expr(self, expr):
        """Check an expression and return its type.

        In freestanding mode (Top-500 #39) any expression whose type
        is heap-backed is rejected here with a named error — the rule
        is enforced at compile time, at the first heap value,
        instead of dying later in codegen or at the C compiler.
        """
        t = self._check_expr_inner(expr)
        if self.freestanding and self._heap_backed(t):
            raise ForgeError(self._heap_error(expr, t),
                             expr.line, expr.col)
        return t

    def _check_expr_inner(self, expr):
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
            if (expr.name not in self.enum_variants
                    and not any(expr.name in scope for scope in self.scopes)
                    and expr.name in self.funcs):
                # A bare function name in value position is a fn
                # value (Top-500 #103, FN-C1).
                expr.is_fn_value = True
                return self._fn_value_type(expr.name, expr.line, expr.col)
            # Capture recording (Top-500 #101, CL-C2): a name
            # resolving to a scope outside an enclosing lambda's
            # boundary is a capture of that lambda — and of every
            # lambda frame between it and the binding (the
            # transitive chain nested lambdas need: the inner
            # lambda reads the value through the outer env).
            self._record_capture(expr.name)
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
            if (path is not None and self._in_field_base == 0
                    and path != self._moved_field_target):
                # A whole-value use of a struct one of whose
                # fields moved away (Top-500 #40): copying the
                # struct would re-own the moved field, so the
                # intermediate path is dead too. Only the
                # outermost access is a whole-value use — a
                # deeper access is a sibling-field read, decided
                # by its own exact check above.
                moved_field = sorted(p for p in self.moved_fields
                                     if p.startswith(path + "."))
                if moved_field:
                    raise ForgeError(f"use of value '{path}' with moved field "
                                     f"'{moved_field[0]}'", expr.line, expr.col)
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
        if isinstance(expr, A.IndirectCall):
            return self.check_indirect_call(expr)
        if isinstance(expr, A.Lambda):
            return self.check_lambda(expr)
        if isinstance(expr, A.Call):
            return self.check_call(expr)
        raise ForgeError(f"unsupported expression {type(expr).__name__}", expr.line, expr.col)

    def check_lambda(self, expr):
        """Check a lambda expression (Top-500 #101, CL-C1).

        Params must be annotated (like fn declarations); the
        return type defaults to void. The body is checked in a
        fresh function context (loop depth reset — a `break`
        inside a lambda must not break the enclosing loop),
        starting from a COPY of the enclosing move/pin state
        (a variable moved before the lambda was created stays
        unusable inside it; a move inside the lambda moves
        only the lambda's own copy). Captures are collected by
        the Var branch (CL-C2) into the frame pushed here.
        """
        seen = set()
        for pn, pt in expr.params:
            if pn in C_KEYWORDS:
                raise ForgeError(f"'{pn}' is a C keyword and cannot be used as a "
                                 f"parameter name; rename it", expr.line, expr.col)
            if pn in seen:
                raise ForgeError(f"duplicate parameter '{pn}' in lambda",
                                 expr.line, expr.col)
            seen.add(pn)
            if not self.valid_type(pt) or pt == "void":
                raise ForgeError(f"lambda parameter type '{pt}' is not a value type",
                                 expr.line, expr.col)
        if expr.ret != "void" and not self.valid_type(expr.ret):
            raise ForgeError(f"unknown lambda return type '{expr.ret}'"
                             f"{suggest(expr.ret, list(SCALARS) + list(self.structs) + list(self.enums))}",
                             expr.line, expr.col)
        if self.freestanding:
            raise ForgeError("lambda expressions need the heap allocator "
                             "(not in freestanding v1; use a named function instead)",
                             expr.line, expr.col)
        saved = (self.current_ret, self.current_fn, self.loop_depth,
                 self.branch_depth, self.moved, self.moved_fields,
                 self.pinned, self.loop_vars, self._for_iterables,
                 self.unresolved, self.label_stack)
        try:
            self.current_ret = expr.ret
            self.current_fn = None
            self.loop_depth = 0
            self.branch_depth = 0
            self.label_stack = []
            self.moved = set(self.moved)
            self.moved_fields = set(self.moved_fields)
            self.pinned = set(self.pinned)
            self.loop_vars = []
            self._for_iterables = []
            self.unresolved = {}
            frame = {"boundary": len(self.scopes), "captures": {}}
            self._lambda_frames.append(frame)
            try:
                self.scopes.append({n: (t, False) for n, t in expr.params})
                try:
                    self.check_block(expr.body)
                finally:
                    self.scopes.pop()
            finally:
                self._lambda_frames.pop()
            if self.unresolved:
                let = next(iter(self.unresolved.values()))
                raise ForgeError("cannot infer the element type of an empty array "
                                 "literal; add an annotation, e.g. "
                                 "let x: [int] = []",
                                 let.line, let.col)
            if expr.ret == "never":
                if self._has_return(expr.body):
                    raise ForgeError("never lambda cannot return; "
                                     "its body must diverge instead",
                                     expr.line, expr.col)
                if not self._body_diverges(expr.body):
                    raise ForgeError("never lambda must end with a "
                                     "diverging statement (fail or a call to a never "
                                     "function); its body can fall off the end",
                                     expr.line, expr.col)
            elif expr.ret != "void":
                if not expr.body.stmts or not isinstance(expr.body.stmts[-1], A.Return):
                    if not self._body_diverges(expr.body):
                        raise ForgeError(f"lambda returns {expr.ret} but its body "
                                         f"does not end with a return; add a return statement "
                                         f"of type {expr.ret} at the end of the lambda",
                                         expr.line, expr.col)
            expr.captures = list(frame["captures"].items())
            expr.fn_type = fn_type_string(expr.params, expr.ret)
            return expr.fn_type
        finally:
            (self.current_ret, self.current_fn, self.loop_depth,
             self.branch_depth, self.moved, self.moved_fields,
             self.pinned, self.loop_vars, self._for_iterables,
             self.unresolved, self.label_stack) = saved

    def _check_indirect_args(self, call, fn_type, what):
        """Check a call's args against a fn type (FN-C2).

        Mirrors the direct-call argument loop exactly (empty-array
        resolution, placeholder filling, accepts, sized-literal
        rule). Stamps the fn type on the node for codegen's
        ownership loop and returns the fn type's return type.
        """
        params, ret = fn_parts(fn_type)
        if len(call.args) != len(params):
            raise ForgeError(f"{what} takes {len(params)} argument(s), "
                             f"got {len(call.args)}", call.line, call.col)
        for i, (arg, pt) in enumerate(zip(call.args, params)):
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
                                     or f"argument {i} of {what} must be {pt}, got {t}"
                                     f"{cast_hint(t, pt)}",
                                     call.line, call.col)
        call.fn_type = fn_type
        return ret

    def check_indirect_call(self, call):
        """handlers[i](x): the callee must be a fn value (FN-C2)."""
        callee_type = self.check_expr(call.callee)
        if not is_fn_type(callee_type):
            raise ForgeError(f"calling a value of type {callee_type} — "
                             f"only a function value can be called",
                             call.line, call.col)
        return self._check_indirect_args(call, callee_type, "indirect call")

    def check_call(self, call):
        if call.name in STMT_BUILTINS:
            raise ForgeError(f"'{call.name}' can only be used as a statement, not as a value",
                             call.line, call.col)
        if self.freestanding and call.name in (
                "read_file", "write_file", "read_bytes", "write_bytes",
                "file_exists", "read_line", "try_alloc", "try_call",
                "mmap_open", "mmap_get", "mmap_grow", "mmap_get32",
                "http_get", "http_listen", "http_accept", "http_read_request",
                "http_respond", "http_respond_status", "http_close",
                "clock_micros", "panicked_tasks", "last_errno", "try_read_file", "try_read_bytes", "args", "parallel_dot", "parallel_matmul",
                "mkdir", "readdir", "try_readdir", "rename", "symlink", "readlink", "try_readlink", "chmod", "chown", "stat_mode", "stat_uid", "stat_gid", "is_dir", "str_compare",
                "sqrt", "exp", "log", "sin", "cos", "tan", "pow", "abs", "run_command"):
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
                if self._for_iterable_conflict(arg):
                    raise ForgeError(f"cannot move '{path}' (it is the iterable of an "
                                     f"enclosing for loop; moving it frees the buffer "
                                     f"the loop is reading)", call.line, call.col)
                if not self._is_owned_type(t):
                    raise ForgeError(f"move needs an owned value (array, str, struct, tuple, function value), "
                                     f"got {t}", call.line, call.col)
                self.moved_fields.add(path)
                call.in_conditional = False
                return t
            t = self.check_expr(arg)
            if self._for_iterable_conflict(arg):
                raise ForgeError(f"cannot move '{arg.name}' (it is the iterable of an "
                                 f"enclosing for loop; moving it frees the buffer "
                                 f"the loop is reading)", call.line, call.col)
            if not self._is_owned_type(t):
                raise ForgeError(f"move needs an owned value (array, str, struct, tuple, function value), "
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
        if call.name == "panicked_tasks":
            # Top-500 #44: total tasks that have panicked so far.
            if call.args:
                raise ForgeError("panicked_tasks() takes no arguments", call.line, call.col)
            return "int"
        if call.name == "last_errno":
            # Top-500 #46: errno of the most recent failed write
            # (0 if no write has failed).
            if call.args:
                raise ForgeError("last_errno() takes no arguments", call.line, call.col)
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
        if call.name in ("sqrt", "exp", "log", "sin", "cos", "tan"):
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
            # struct comes from forge_lang/stdlib/result.fg, so the program must
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
        if call.name == "try_read_file":
            # Top-500 #46: fallible read, returns Result<str, int>:
            # Ok with the file content, or Err(errno) instead of
            # the fatal forge_fail in read_file. The Result struct
            # comes from forge_lang/stdlib/result.fg, so the program must
            # import it; register the concrete instantiation here so
            # check()'s epilogue appends it to program.structs and
            # codegen emits the C struct body.
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("try_read_file() takes exactly one str argument",
                                 call.line, call.col)
            if "Result" not in self.structs:
                raise ForgeError("try_read_file() needs import \"result.fg\" "
                                 "(it returns Result<str, int>)",
                                 call.line, call.col)
            fields = self.struct_fields_for("Result<str, int>")
            if fields is None:
                raise ForgeError("try_read_file() needs Result<T, E> with ok/value/error "
                                 "fields (import \"result.fg\")",
                                 call.line, call.col)
            self.struct_instantiations["Result<str, int>"] = fields
            call.concrete_type = "Result<str, int>"
            return "Result<str, int>"
        if call.name == "try_read_bytes":
            # Top-500 #46: fallible byte read, returns Result<[int], int>:
            # Ok with the file bytes, or Err(errno) instead of
            # the fatal forge_fail in read_bytes. Same Result
            # registration as try_read_file.
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("try_read_bytes() takes exactly one str argument",
                                 call.line, call.col)
            if "Result" not in self.structs:
                raise ForgeError("try_read_bytes() needs import \"result.fg\" "
                                 "(it returns Result<[int], int>)",
                                 call.line, call.col)
            fields = self.struct_fields_for("Result<[int], int>")
            if fields is None:
                raise ForgeError("try_read_bytes() needs Result<T, E> with ok/value/error "
                                 "fields (import \"result.fg\")",
                                 call.line, call.col)
            self.struct_instantiations["Result<[int], int>"] = fields
            call.concrete_type = "Result<[int], int>"
            return "Result<[int], int>"
        if call.name == "try_call":
            # Top-500 #48: guarded call across a module boundary.
            # try_call(f) / try_call(f, x) calls the foreign function
            # f and returns Result<R, str>: Ok with f's return value,
            # or Err(message) when f fail()s. Only fail() is caught
            # in v1 (runtime faults and assert stay fatal via
            # forge_fail). f must be a bare function name defined in
            # a different .fg file from the caller (the module
            # boundary, fn.file comparison); the Result struct comes
            # from forge_lang/stdlib/result.fg, so the program must
            # import it; register the concrete instantiation here so
            # check()'s epilogue appends it to program.structs and
            # codegen emits the C struct body. The callee's fn type
            # is stamped on call.trycall_fn_type (NOT call.fn_type:
            # is_fresh_str/is_fresh_fn read fn_type and would
            # wrongly treat try_call as returning R instead of
            # Result).
            if len(call.args) not in (1, 2):
                raise ForgeError("try_call() takes a bare function name and 0 or 1 "
                                 "arguments (v1 arity 0-or-1)", call.line, call.col)
            callee = call.args[0]
            if not isinstance(callee, A.Var) \
                    or any(callee.name in scope for scope in self.scopes) \
                    or callee.name not in self.funcs:
                raise ForgeError("try_call() takes a bare function name defined in "
                                 "another file (not a closure, fn-typed variable, or "
                                 "method)", call.line, call.col)
            ft = self.check_expr(callee)
            parts = fn_parts(ft)
            if parts is None:
                raise ForgeError("try_call() takes a bare function name defined in "
                                 "another file (not a closure, fn-typed variable, or "
                                 "method)", call.line, call.col)
            params, ret = parts
            if len(params) != len(call.args) - 1:
                raise ForgeError(f"try_call() callee '{callee.name}' takes "
                                 f"{len(params)} argument(s), got {len(call.args) - 1}",
                                 call.line, call.col)
            if ret in ("void", "never"):
                raise ForgeError(f"try_call() callee '{callee.name}' returns {ret}; "
                                 f"the guarded call needs a value to wrap in Result",
                                 call.line, call.col)
            if is_opaque_type(ret):
                raise ForgeError(f"try_call() callee '{callee.name}' returns opaque "
                                 f"type '{ret}' (no value can be built for the Err arm)",
                                 call.line, call.col)
            if getattr(self.funcs[callee.name], "file", "") == self.current_file:
                raise ForgeError(f"try_call() is for calls across a module boundary; "
                                 f"'{callee.name}' is defined in this file",
                                 call.line, call.col)
            value_call = A.Call(name=callee.name, args=list(call.args[1:]),
                                line=call.line, col=call.col)
            self._check_indirect_args(value_call, ft,
                                      f"try_call() callee '{callee.name}'")
            if "Result" not in self.structs:
                raise ForgeError("try_call() needs import \"result.fg\" "
                                 "(it returns Result<R, str>)",
                                 call.line, call.col)
            result_t = f"Result<{ret}, str>"
            fields = self.struct_fields_for(result_t)
            if fields is None:
                raise ForgeError("try_call() needs Result<T, E> with ok/value/error "
                                 "fields (import \"result.fg\")",
                                 call.line, call.col)
            self.struct_instantiations[result_t] = fields
            call.concrete_type = result_t
            call.trycall_fn_type = ft
            return result_t
        if call.name == "mkdir":
            # Top-500 #181 (filesystem slice): mkdir(path, 0755).
            # False on failure; the errno is readable with
            # last_errno() (write_file shape).
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("mkdir() takes exactly one str argument",
                                 call.line, call.col)
            return "bool"
        if call.name == "readdir":
            # Top-500 #181 (filesystem slice): entry names of a
            # directory, excluding "." and "..", in raw readdir(2)
            # order (unspecified — sort in the library). Fatal
            # forge_fail on opendir failure, like read_file.
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("readdir() takes exactly one str argument",
                                 call.line, call.col)
            return "[str]"
        if call.name == "try_readdir":
            # Top-500 #181 (filesystem slice): fallible readdir,
            # returns Result<[str], int> with Err(errno) instead
            # of the fatal forge_fail in readdir. Same Result
            # registration as try_read_file.
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("try_readdir() takes exactly one str argument",
                                 call.line, call.col)
            if "Result" not in self.structs:
                raise ForgeError("try_readdir() needs import \"result.fg\" "
                                 "(it returns Result<[str], int>)",
                                 call.line, call.col)
            fields = self.struct_fields_for("Result<[str], int>")
            if fields is None:
                raise ForgeError("try_readdir() needs Result<T, E> with ok/value/error "
                                 "fields (import \"result.fg\")",
                                 call.line, call.col)
            self.struct_instantiations["Result<[str], int>"] = fields
            call.concrete_type = "Result<[str], int>"
            return "Result<[str], int>"
        if call.name == "rename":
            # Top-500 #187 (filesystem slice): rename(2). False
            # on failure; the errno is readable with last_errno().
            if len(call.args) != 2:
                raise ForgeError("rename() takes exactly two arguments",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "str":
                    raise ForgeError("rename() takes str arguments", call.line, call.col)
            return "bool"
        if call.name == "symlink":
            # Top-500 #188 (filesystem slice): symlink(2). False
            # on failure; the errno is readable with last_errno().
            if len(call.args) != 2:
                raise ForgeError("symlink() takes exactly two arguments",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "str":
                    raise ForgeError("symlink() takes str arguments", call.line, call.col)
            return "bool"
        if call.name == "readlink":
            # Top-500 #188 (filesystem slice): the target of a
            # symlink. Fatal forge_fail on failure, like read_file.
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("readlink() takes exactly one str argument",
                                 call.line, call.col)
            return "str"
        if call.name == "try_readlink":
            # Top-500 #188 (filesystem slice): fallible readlink,
            # returns Result<str, int> with Err(errno) instead of
            # the fatal forge_fail in readlink. Same Result
            # registration as try_read_file.
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("try_readlink() takes exactly one str argument",
                                 call.line, call.col)
            if "Result" not in self.structs:
                raise ForgeError("try_readlink() needs import \"result.fg\" "
                                 "(it returns Result<str, int>)",
                                 call.line, call.col)
            fields = self.struct_fields_for("Result<str, int>")
            if fields is None:
                raise ForgeError("try_readlink() needs Result<T, E> with ok/value/error "
                                 "fields (import \"result.fg\")",
                                 call.line, call.col)
            self.struct_instantiations["Result<str, int>"] = fields
            call.concrete_type = "Result<str, int>"
            return "Result<str, int>"
        if call.name == "chmod":
            # Top-500 #189 (filesystem slice): chmod(2). False
            # on failure; the errno is readable with last_errno().
            if len(call.args) != 2:
                raise ForgeError("chmod() takes exactly two arguments",
                                 call.line, call.col)
            if self.check_expr(call.args[0]) != "str":
                raise ForgeError("chmod() takes a str path", call.line, call.col)
            if self.check_expr(call.args[1]) != "int":
                raise ForgeError("chmod() takes an int mode", call.line, call.col)
            return "bool"
        if call.name == "chown":
            # Top-500 #189 (filesystem slice): chown(2). False
            # on failure; the errno is readable with last_errno().
            if len(call.args) != 3:
                raise ForgeError("chown() takes exactly three arguments",
                                 call.line, call.col)
            if self.check_expr(call.args[0]) != "str":
                raise ForgeError("chown() takes a str path", call.line, call.col)
            for a in call.args[1:]:
                if self.check_expr(a) != "int":
                    raise ForgeError("chown() takes int uid and gid", call.line, call.col)
            return "bool"
        if call.name in ("stat_mode", "stat_uid", "stat_gid"):
            # Top-500 #189 (filesystem slice): one field of
            # stat(2) — st_mode / st_uid / st_gid. -1 on failure;
            # the errno is readable with last_errno().
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError(f"{call.name}() takes exactly one str argument",
                                 call.line, call.col)
            return "int"
        if call.name == "is_dir":
            # Top-500 #190 (filesystem slice): stat(2) + S_ISDIR.
            # False on any failure, like file_exists.
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("is_dir() takes exactly one str argument",
                                 call.line, call.col)
            return "bool"
        if call.name == "str_compare":
            # Filesystem slice FS-X1: strcmp — the string-ordering
            # primitive directory listings need (string < does not
            # exist, ord/chr are absent). Negative / 0 / positive.
            if len(call.args) != 2:
                raise ForgeError("str_compare() takes exactly two arguments",
                                 call.line, call.col)
            for a in call.args:
                if self.check_expr(a) != "str":
                    raise ForgeError("str_compare() takes str arguments", call.line, call.col)
            return "int"
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
        if call.name == "run_command":
            if len(call.args) != 1 or self.check_expr(call.args[0]) != "str":
                raise ForgeError("run_command() takes exactly one str argument",
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
            # Indirect call through a fn-typed variable (FN-C2):
            # f(x) where f is a local/param of fn type. A same-named
            # function still wins when no fn-typed local shadows it
            # (the funcs.get above); a non-fn local with a function's
            # name also falls through to the function, so existing
            # programs are unaffected.
            var_type = None
            for scope in reversed(self.scopes):
                if call.name in scope:
                    var_type = scope[call.name][0]
                    break
            if var_type is not None:
                if not is_fn_type(var_type):
                    raise ForgeError(f"calling '{call.name}' (type {var_type}) — "
                                     f"'{call.name}' is not a function",
                                     call.line, call.col)
                if call.name in self.moved:
                    # Calling a moved closure is a use of the moved
                    # value, like any other Var use (Top-500 #101:
                    # the callee here is a name, not a Var node, so
                    # the Var branch's moved check never sees it).
                    raise ForgeError(f"use of moved value '{call.name}'",
                                     call.line, call.col)
                # The callee is a name, not a Var node: record the
                # capture here, or a lambda calling an outer fn
                # variable would have no env slot for it (#101).
                self._record_capture(call.name)
                return self._check_indirect_args(call, var_type, f"'{call.name}'")
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
            if lt == rt and is_fn_type(lt):
                # Fn values compare as C pointers (Top-500 #103,
                # FN-C3): same fn type only, no subtyping.
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


def check(program, require_main=True, freestanding=False, dump_error_sets=False,
          target=None):
    Checker(program, freestanding,
            dump_error_sets=dump_error_sets,
            target=target).check(require_main=require_main)
