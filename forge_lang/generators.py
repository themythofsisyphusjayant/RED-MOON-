"""Top-500 #74: generator functions / yield — checker-side state-machine desugar.

A function containing `yield` and declared `-> Generator<T>` is rewritten,
before checking, into two ordinary functions:

- the CONSTRUCTOR (same name, same params): builds the `Generator<T>`
  value without running the body — laziness is structural;
- the STEP FUNCTION `<name>_next(g: Generator<T>) -> Option<T>`: a
  `while (true)` dispatch loop over `if (g.slots_i[0] == N)` segments.
  Each segment ends with a yield-return, a return-none, or
  `state = X; continue;`.

The generator's params and locals are LIFTED into the slot arrays of
the shared generic struct `Generator<T> { kind, cur, slots_i, slots_s,
slots_b }` (see `forge_lang/stdlib/generators.fg`). Slot 0 of `slots_i`
is the state-machine state; the remaining slots hold the int/str/bool
params and locals. Slot reads/writes are index operations on the
arrays, which persist across calls and struct copies (array headers
are passed by value but index writes go through the shared pointer).
No infer or codegen change is needed in any backend: the desugared
program contains only ordinary `Let`/`Assign`/`If`/`While`/`Return`/
`Call` nodes.

Entry point: `resolve_generators(program, structs, struct_params,
target, freestanding)`, called from `Checker.check()` after aliases
are expanded and structs are known, before any function is checked.
It is idempotent: a second run finds no `Yield` in any body (the
constructor has none, the step fn has none) and returns the program
untouched.
"""

from . import ast_nodes as A
from .errors import ForgeError
from .fntypes import is_fn_type, fn_parts


def _fn_type_params(t):
    parts = fn_parts(t)
    return parts[0] if parts is not None else None


def _fn_type_ret(t):
    parts = fn_parts(t)
    return parts[1] if parts is not None else None
from .generics import parse_generic, substitute_type
from .tuples import is_tuple_type, tuple_elems

GEN_ELEM_TYPES = ("int", "str", "bool")
GEN_SLOT_ARRAYS = {"int": "slots_i", "str": "slots_s", "bool": "slots_b"}
GEN_STRUCT_FIELDS = {
    "kind": "int",
    "cur": "T",
    "slots_i": "[int]",
    "slots_s": "[str]",
    "slots_b": "[bool]",
}
GEN_STRUCT_TPARAMS = ["T"]

# Unambiguous builtin return types, for the desugar's type prover
# (`prove_type`). Anything not listed here is unprovable at desugar
# time and left to the checker (or reported with the annotate error
# where the desugar must know the type).
_BUILTIN_RET = {
    "len": "int",
    "clock_micros": "int",
    "panicked_tasks": "int",
    "last_errno": "int",
    "parse_int": "int",
    "parse_float": "float",
    "read_line": "str",
    "read_file": "str",
    "substr": "str",
    "trim": "str",
    "join": "str",
    "split": "[str]",
    "starts_with": "bool",
    "ends_with": "bool",
    "file_exists": "bool",
    "sqrt": "float",
    "exp": "float",
    "log": "float",
    "sin": "float",
    "cos": "float",
    "tan": "float",
    "pow": "float",
    "range": "range",
}


def _zero(t, line, col):
    """The zero literal of a liftable type (for slot initialisers
    and the `cur` witness field)."""
    if t == "int":
        return A.IntLit(0, line, col)
    if t == "str":
        return A.StrLit("", line, col)
    return A.BoolLit(False, line, col)


def _gen_ret(ret):
    """(True, T) when `ret` is exactly `Generator<T>`, else (False, None)."""
    g = parse_generic(ret)
    if g is not None and g[0] == "Generator" and len(g[1]) == 1:
        return True, g[1][0]
    return False, None


class _GenTransform:
    """The per-program generator transform (one instance per check)."""

    def __init__(self, program, structs, struct_params, target, freestanding):
        self.program = program
        self.structs = structs  # name -> {field: type}
        self.struct_params = struct_params  # name -> [type params]
        self.target = target  # Target record (has .target/.freestanding)
        self.freestanding = freestanding
        self.fn_table = {}
        for fn in program.funcs:
            self.fn_table[fn.name] = fn
        self.kind_counter = 0
        self.step_fns = []
        # Per-generator state (reset for each generator fn).
        self.fn = None
        self.elem = None
        self.kind = 0
        self.scope = []  # [frame]; frame: name -> ("slot", arr, idx, typ) | ("opaque", typ|None)
        self.int_count = 1  # slots_i[0] is the state
        self.str_count = 0
        self.bool_count = 0
        self.states = {}  # id -> [stmts]
        self.cur_state = 0
        self.next_state = 1
        self.end_state = None
        self.loop_stack = []  # (label|None, is_split, break_state, cont_state)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def run(self):
        out_funcs = []
        changed = False
        for fn in self.program.funcs:
            if getattr(fn, "is_extern", False) or fn.body is None:
                out_funcs.append(fn)
                continue
            has_yield, violation = self._scan_body(fn.body)
            is_gen, elem = _gen_ret(fn.ret)
            if violation is not None and (has_yield or is_gen):
                kind, node = violation
                if kind == "defer":
                    raise ForgeError(
                        "defer is not supported inside a generator function "
                        "in v1 (it would run when the step function returns, "
                        "not when the generator closes)", node.line, node.col)
                raise ForgeError(
                    "walrus ':=' is not supported inside a generator "
                    "function in v1 (write the assignment before the "
                    "if/while instead)", node.line, node.col)
            if has_yield:
                if not is_gen:
                    raise ForgeError(
                        "yield is only allowed in a function returning "
                        "Generator<T> in v1", fn.line, fn.col)
                if elem not in GEN_ELEM_TYPES:
                    raise ForgeError(
                        "generator element type must be int, str, or bool "
                        f"in v1, got {elem}", fn.line, fn.col)
                if getattr(fn, "type_params", None):
                    raise ForgeError(
                        "generic generator functions are not supported in v1",
                        fn.line, fn.col)
                self._check_gen_struct(fn)
                self._check_target(fn)
                ctor, step = self._transform(fn, elem)
                out_funcs.append(ctor)
                self.step_fns.append(step)
                changed = True
            elif is_gen:
                # No yield: a degenerate empty generator (the body
                # still runs once, lazily, on the first next()).
                # Only transform when the struct exists — otherwise
                # leave the fn alone so check_func reports the
                # ordinary unknown-type error.
                if elem not in GEN_ELEM_TYPES:
                    raise ForgeError(
                        "generator element type must be int, str, or bool "
                        f"in v1, got {elem}", fn.line, fn.col)
                if getattr(fn, "type_params", None):
                    raise ForgeError(
                        "generic generator functions are not supported in v1",
                        fn.line, fn.col)
                if "Generator" not in self.structs:
                    out_funcs.append(fn)
                    continue
                # Idempotency: the hosted compiler runs this pass
                # twice (check_program, then compile_to_c on the
                # merged program). A constructor from the first pass
                # still returns Generator<T> with no yield, so
                # without this skip the second pass would re-transform
                # it and trip its own step fn as a name collision.
                # A fn whose <name>_next already exists is already
                # a constructor — leave it alone. (A yield-ful fn
                # whose step fn exists is a REAL collision and still
                # errors in _transform; a no-yield fn whose step fn
                # is user-defined is the same shape and is likewise
                # left alone — the <name>_next name is reserved.)
                if fn.name + "_next" in self.fn_table:
                    out_funcs.append(fn)
                    continue
                self._check_gen_struct(fn)
                self._check_target(fn)
                ctor, step = self._transform(fn, elem)
                out_funcs.append(ctor)
                self.step_fns.append(step)
                changed = True
            else:
                out_funcs.append(fn)
        if changed:
            self.program.funcs = out_funcs + self.step_fns
        return self.program

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    def _check_gen_struct(self, fn):
        """The Generator struct must be the stdlib one (import
        "generators.fg"); anything else is a named error."""
        if "Generator" not in self.structs:
            raise ForgeError(
                "generator functions need import \"generators.fg\" "
                f"(type '{fn.ret}' is not defined)", fn.line, fn.col)
        fields = self.structs["Generator"]
        params = self.struct_params.get("Generator", [])
        if params != GEN_STRUCT_TPARAMS or fields != GEN_STRUCT_FIELDS:
            raise ForgeError(
                "Generator<T> must come from import \"generators.fg\" "
                "(expected fields kind, cur, slots_i, slots_s, slots_b)",
                fn.line, fn.col)

    def _check_target(self, fn):
        """Native only in v1 — big32 / wasm / freestanding are
        check-time named errors, never backend-internal ones."""
        if self.freestanding or (self.target is not None
                                 and getattr(self.target, "freestanding", False)):
            raise ForgeError(
                "generators are not supported in freestanding mode in v1 "
                "(generators need arrays)", fn.line, fn.col)
        tgt = getattr(self.target, "target", "native") if self.target else "native"
        if tgt == "big32":
            raise ForgeError(
                "generators are not supported on big32 in v1 (the Generator "
                "struct needs array fields, which big32 structs do not "
                "support in v1)", fn.line, fn.col)
        if tgt == "wasm":
            raise ForgeError(
                "generators are not supported on wasm in v1 (wasm v2 does "
                "not support struct returns)", fn.line, fn.col)

    # ------------------------------------------------------------------
    # Pre-scan: Yield / walrus / defer / match / comptime errors.
    # Walks the body WITHOUT crossing lambda boundaries for the
    # body-level rules; a Yield inside a lambda is its own error.
    # ------------------------------------------------------------------
    def _scan_body(self, body):
        found = [False]
        # First defer/walrus in the body proper, in source order
        # ("defer"|"walrus", node) — recorded, NOT raised here.
        # The pre-scan runs on EVERY fn (to find yields), but a
        # defer/walrus is only an error inside a GENERATOR fn; a
        # non-generator fn with a defer/walrus is fine (the corpus
        # defer files v23/v24/v27/v89 tripped this: the scan raised
        # the defer error for ordinary fns). run() raises the
        # recorded violation only when the fn is a generator
        # (has_yield or returns Generator<T>). A defer/walrus
        # inside a lambda is the lambda's own business and is
        # never recorded.
        violation = [None]
        self._scan_violation = violation

        def scan_stmts(stmts, in_lambda):
            for s in stmts:
                scan_stmt(s, in_lambda)

        def scan_stmt(s, in_lambda):
            if isinstance(s, A.Yield):
                if in_lambda:
                    raise ForgeError(
                        "yield cannot appear inside a nested function or "
                        "closure in v1", s.line, s.col)
                found[0] = True
                self._scan_expr(s.expr, in_lambda)
            elif isinstance(s, A.Defer):
                if not in_lambda and violation[0] is None:
                    violation[0] = ("defer", s)
                self._scan_expr(s.call, in_lambda)
            elif isinstance(s, A.Match):
                for _pat, arm in s.arms:
                    if self._has_yield_stmts(arm.stmts):
                        raise ForgeError(
                            "yield cannot appear inside a match arm in v1 "
                            "(use if/else)", s.line, s.col)
                    scan_stmts(arm.stmts, in_lambda)
                self._scan_expr(s.expr, in_lambda)
            elif isinstance(s, A.ComptimeIf):
                for branch in (s.then, s.els):
                    if branch is not None and self._has_yield_stmts(branch.stmts):
                        raise ForgeError(
                            "yield cannot appear inside a comptime if branch "
                            "in v1", s.line, s.col)
                    if branch is not None:
                        scan_stmts(branch.stmts, in_lambda)
            elif isinstance(s, A.Scope):
                if self._has_yield_stmts(s.body.stmts):
                    raise ForgeError(
                        "yield cannot appear inside a scope block in v1",
                        s.line, s.col)
                scan_stmts(s.body.stmts, in_lambda)
            elif isinstance(s, A.Block):
                scan_stmts(s.stmts, in_lambda)
            elif isinstance(s, A.If):
                self._scan_expr(s.cond, in_lambda)
                scan_stmts(s.then.stmts, in_lambda)
                if s.els is not None:
                    scan_stmts(s.els.stmts, in_lambda)
            elif isinstance(s, A.While):
                self._scan_expr(s.cond, in_lambda)
                scan_stmts(s.body.stmts, in_lambda)
            elif isinstance(s, A.For):
                self._scan_expr(s.expr, in_lambda)
                scan_stmts(s.body.stmts, in_lambda)
            elif isinstance(s, A.Let):
                self._scan_expr(s.expr, in_lambda)
            elif isinstance(s, A.Assign):
                self._scan_expr(s.expr, in_lambda)
            elif isinstance(s, A.IndexAssign):
                self._scan_expr(s.base, in_lambda)
                self._scan_expr(s.expr, in_lambda)
            elif isinstance(s, A.FieldAssign):
                self._scan_expr(s.target, in_lambda)
                self._scan_expr(s.expr, in_lambda)
            elif isinstance(s, A.Return):
                if s.expr is not None:
                    self._scan_expr(s.expr, in_lambda)
            elif isinstance(s, A.ExprStmt):
                self._scan_expr(s.expr, in_lambda)
            elif isinstance(s, (A.Break, A.Continue)):
                pass
            else:
                # Unknown statement shape: walk its fields generically.
                self._scan_generic(s, in_lambda)

        scan_stmts(body.stmts, False)
        return found[0], violation[0]

    def _scan_generic(self, node, in_lambda):
        import dataclasses
        if not dataclasses.is_dataclass(node):
            return
        for f in dataclasses.fields(node):
            v = getattr(node, f.name)
            if isinstance(v, A.Yield):
                raise ForgeError(
                    "yield cannot appear inside a nested function or closure "
                    "in v1" if in_lambda else
                    "yield is only allowed in a function returning "
                    "Generator<T> in v1", node.line, node.col)
            if isinstance(v, list):
                for item in v:
                    if dataclasses.is_dataclass(item):
                        self._scan_generic(item, in_lambda)
            elif dataclasses.is_dataclass(v):
                self._scan_generic(v, in_lambda)

    def _scan_expr(self, e, in_lambda):
        """Scan one expression: NamedExpr (walrus) in the body proper
        is an error; a Yield cannot occur in an expression except
        inside a lambda (its own error)."""
        if e is None:
            return
        if isinstance(e, A.NamedExpr):
            # Recorded, not raised (see _scan_body): a walrus is
            # only an error inside a generator fn, and this scan
            # runs on every fn. A walrus inside a lambda is the
            # lambda's own business.
            if not in_lambda:
                v = getattr(self, "_scan_violation", None)
                if v is not None and v[0] is None:
                    v[0] = ("walrus", e)
            self._scan_expr(e.expr, in_lambda)
            return
        if isinstance(e, A.Lambda):
            self._scan_lambda_body(e, in_lambda)
            return
        import dataclasses
        if not dataclasses.is_dataclass(e):
            return
        for f in dataclasses.fields(e):
            v = getattr(e, f.name)
            if isinstance(v, list):
                for item in v:
                    if dataclasses.is_dataclass(item):
                        self._scan_expr(item, in_lambda)
            elif dataclasses.is_dataclass(v):
                self._scan_expr(v, in_lambda)

    def _scan_lambda_body(self, lam, in_lambda):
        # A yield anywhere in the lambda body is the closure error;
        # defer/walrus inside are the lambda's own business.
        if self._has_yield_stmts(lam.body.stmts):
            bad = self._find_yield(lam.body.stmts)
            raise ForgeError(
                "yield cannot appear inside a nested function or closure "
                "in v1", bad.line, bad.col)

    def _find_yield(self, stmts):
        for s in stmts:
            if isinstance(s, A.Yield):
                return s
            import dataclasses
            if dataclasses.is_dataclass(s):
                for f in dataclasses.fields(s):
                    v = getattr(s, f.name)
                    if isinstance(v, list):
                        for item in v:
                            if dataclasses.is_dataclass(item):
                                r = self._find_yield_in(item)
                                if r is not None:
                                    return r
                    elif dataclasses.is_dataclass(v):
                        r = self._find_yield_in(v)
                        if r is not None:
                            return r
        return None

    def _find_yield_in(self, node):
        if isinstance(node, A.Yield):
            return node
        if isinstance(node, A.Lambda):
            return None  # a nested lambda is a new boundary
        import dataclasses
        if not dataclasses.is_dataclass(node):
            return None
        for f in dataclasses.fields(node):
            v = getattr(node, f.name)
            if isinstance(v, list):
                for item in v:
                    if dataclasses.is_dataclass(item):
                        r = self._find_yield_in(item)
                        if r is not None:
                            return r
            elif dataclasses.is_dataclass(v):
                r = self._find_yield_in(v)
                if r is not None:
                    return r
        return None

    def _has_yield_stmts(self, stmts):
        return self._find_yield(stmts) is not None

    def _has_yield(self, node):
        """True when a Yield occurs anywhere under `node` without
        crossing a lambda boundary."""
        return self._find_yield_in(node) is not None


    # ------------------------------------------------------------------
    # Type prover (best-effort; the checker is the backstop).
    # Returns a type string or None when it cannot be proved.
    # ------------------------------------------------------------------
    def prove_type(self, e):
        if e is None:
            return None
        if isinstance(e, A.IntLit):
            return "int"
        if isinstance(e, A.FloatLit):
            return "float"
        if isinstance(e, A.StrLit):
            return "str"
        if isinstance(e, A.BoolLit):
            return "bool"
        if isinstance(e, A.Var):
            b = self._lookup(e.name)
            if b is None:
                return None
            return b[3] if b[0] == "slot" else b[1]
        if isinstance(e, A.BinOp):
            if e.op in ("==", "!=", "<", "<=", ">", ">=", "&&", "||"):
                return "bool"
            if e.op in ("+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^"):
                lt = self.prove_type(e.left)
                rt = self.prove_type(e.right)
                if e.op == "+" and (lt == "str" or rt == "str"):
                    return "str"
                if lt == "float" or rt == "float":
                    return "float"
                if lt == "int" and rt == "int":
                    return "int"
                return None
            return None
        if isinstance(e, A.UnaryOp):
            if e.op == "!":
                return "bool"
            return self.prove_type(e.expr)
        if isinstance(e, A.Call):
            if e.name in _BUILTIN_RET:
                return _BUILTIN_RET[e.name]
            fn = self.fn_table.get(e.name)
            if fn is None:
                return None
            if getattr(fn, "type_params", None):
                return self._prove_generic_call(fn, e)
            return fn.ret
        if isinstance(e, A.IndirectCall):
            ct = self.prove_type(e.callee)
            if ct is not None and is_fn_type(ct):
                return _fn_type_ret(ct)
            return None
        if isinstance(e, A.Index):
            bt = self.prove_type(e.base)
            if bt == "str":
                return "str"
            if bt is not None and bt.startswith("[") and bt.endswith("]"):
                return bt[1:-1]
            return None
        if isinstance(e, A.TupleIndex):
            bt = self.prove_type(e.base)
            if bt is not None and is_tuple_type(bt):
                elems = tuple_elems(bt)
                if 0 <= e.index < len(elems):
                    return elems[e.index]
            return None
        if isinstance(e, A.FieldAccess):
            bt = self.prove_type(e.base)
            if bt is None:
                return None
            fields = self._struct_fields_of(bt)
            if fields is None:
                return None
            return fields.get(e.field)
        if isinstance(e, A.MethodCall):
            bt = self.prove_type(e.base)
            if bt == "range":
                if e.method == "len":
                    return "int"
                if e.method == "contains":
                    return "bool"
            return None
        if isinstance(e, A.StructLit):
            return e.name
        if isinstance(e, A.ArrayLit):
            if not e.elems:
                return None
            et = self.prove_type(e.elems[0])
            return f"[{et}]" if et is not None else None
        if isinstance(e, A.TupleLit):
            parts = [self.prove_type(x) for x in e.elems]
            if any(p is None for p in parts):
                return None
            return "(" + ", ".join(parts) + ")"
        if isinstance(e, A.RangeLit):
            return "range"
        if isinstance(e, A.Cast):
            return e.target
        if isinstance(e, A.Try):
            t = self.prove_type(e.expr)
            if t is None:
                return None
            g = parse_generic(t)
            if g is not None and g[0] in ("Option", "Result") and g[1]:
                return g[1][0]
            return None
        if isinstance(e, A.Lambda):
            params = ", ".join(pt for _n, pt in e.params)
            return f"fn({params}) -> {e.ret}"
        return None

    def _prove_generic_call(self, fn, call):
        """Bind a generic fn's type params from the call args
        (positional, first-use order) and substitute into its
        return type. Best-effort: None when it cannot be bound."""
        bindings = {}
        params = getattr(fn, "type_params", None) or []
        for (_n, pt), arg in zip(fn.params, call.args):
            if pt in params and pt not in bindings:
                at = self.prove_type(arg)
                if at is not None:
                    bindings[pt] = at
        if len(bindings) != len(params):
            return None
        return substitute_type(fn.ret, bindings)

    def _struct_fields_of(self, t):
        """{field: type} for a (possibly generic-instantiated)
        struct type, or None when unknown."""
        g = parse_generic(t)
        if g is not None:
            base, args = g
            if base not in self.structs:
                return None
            params = self.struct_params.get(base, [])
            if len(params) != len(args):
                return None
            bindings = dict(zip(params, args))
            return {f: substitute_type(ft, bindings)
                    for f, ft in self.structs[base].items()}
        if t in self.structs:
            return dict(self.structs[t])
        return None

    # ------------------------------------------------------------------
    # Scope stack. A frame maps a name to ("slot", arr, idx, typ) for
    # a lifted generator binding, or ("opaque", typ|None) for a name
    # that stays an ordinary variable (lambda param, match binding,
    # inline for-loop var).
    # ------------------------------------------------------------------
    def _push(self):
        self.scope.append({})

    def _pop(self):
        self.scope.pop()

    def _lookup(self, name):
        for frame in reversed(self.scope):
            if name in frame:
                return frame[name]
        return None

    def _alloc_slot(self, typ):
        if typ == "int":
            idx = self.int_count
            self.int_count += 1
            return "slots_i", idx
        if typ == "str":
            idx = self.str_count
            self.str_count += 1
            return "slots_s", idx
        idx = self.bool_count
        self.bool_count += 1
        return "slots_b", idx

    def _declare_slot(self, name, typ, line, col):
        arr, idx = self._alloc_slot(typ)
        binding = ("slot", arr, idx, typ)
        self.scope[-1][name] = binding
        return binding

    # ------------------------------------------------------------------
    # Generated-node helpers (all carry the source position).
    # ------------------------------------------------------------------
    def _gvar(self, line, col):
        return A.Var("g", line, col)

    def _slot_read(self, binding, line, col):
        _kind, arr, idx, _typ = binding
        return A.Index(A.FieldAccess(self._gvar(line, col), arr, line, col),
                       A.IntLit(idx, line, col), line, col)

    def _slot_write(self, binding, rhs, line, col):
        _kind, arr, idx, _typ = binding
        return A.IndexAssign(
            A.Index(A.FieldAccess(self._gvar(line, col), arr, line, col),
                    A.IntLit(idx, line, col), line, col),
            rhs, line, col)

    def _state_write(self, target, line, col):
        return A.IndexAssign(
            A.Index(A.FieldAccess(self._gvar(line, col), "slots_i", line, col),
                    A.IntLit(0, line, col), line, col),
            A.IntLit(target, line, col), line, col)

    def _state_read(self, line, col):
        return A.Index(A.FieldAccess(self._gvar(line, col), "slots_i", line, col),
                       A.IntLit(0, line, col), line, col)

    def _has_inline_loop(self, loops):
        """True when the loop stack holds an inline (real C) loop."""
        for _label, is_split, _brk, _cont in loops:
            if not is_split:
                return True
        return False

    def _unwind_jump(self, s, tgt, loops):
        """A break/continue jumping to a SPLIT loop's state `tgt`,
        emitted inside inline (real C) code. It must unwind out of
        every enclosing inline loop before the dispatch loop can see
        the new state: an unlabeled `break` exits the innermost
        inline loop, and the guard after each inline loop cascades
        the unwind outward. A `continue` here would target the
        innermost inline loop and spin forever (the s06b
        labeled-break hang: `break outer` inside an inline while
        became `state = 2; continue;` inside that while). With no
        enclosing inline loop the statement is already at segment
        level, so a plain `continue` targets the dispatch loop."""
        if self._has_inline_loop(loops):
            return [self._state_write(tgt, s.line, s.col),
                    A.Break(s.line, s.col, None)]
        return [self._state_write(tgt, s.line, s.col),
                A.Continue(s.line, s.col, None)]

    def _inline_guard(self, line, col, cur_state, enclosing):
        """The unwind guard placed after an inline (real C) loop:
        `if (state != cur_state) { break|continue; }`. A jump
        inside the loop sets the state and breaks out; the guard
        sees the changed state and unwinds one more level (`break`
        when the loop is nested inside another inline loop,
        `continue` when it sits directly in a segment, where
        `continue` targets the dispatch loop). With no jump the
        state is unchanged and the guard is a no-op. Emitted
        unconditionally: the scan that would prove a loop jump-free
        is more bug surface than the one-line guard."""
        if self._has_inline_loop(enclosing):
            unwind = A.Break(line, col, None)
        else:
            unwind = A.Continue(line, col, None)
        return A.If(A.BinOp("!=", self._state_read(line, col),
                            A.IntLit(cur_state, line, col), line, col),
                    A.Block([unwind]), None, line, col)

    def _none_lit(self, line, col):
        return A.StructLit("Option", [
            ("present", A.BoolLit(False, line, col)),
            ("value", _zero(self.elem, line, col)),
        ], line, col)

    def _opt_some(self, expr, line, col):
        return A.Call("opt_some", [expr], line, col)

    # ------------------------------------------------------------------
    # Segment machinery. `self.cur_state` is always an open state;
    # every state is sealed with exactly one terminator.
    # ------------------------------------------------------------------
    def _new_state(self):
        i = self.next_state
        self.next_state += 1
        self.states[i] = []
        return i

    def _emit(self, stmt):
        self.states[self.cur_state].append(stmt)

    def _jump(self, target):
        """Seal the current state with `state = target; continue;`."""
        line, col = self.fn.line, self.fn.col
        self._emit(self._state_write(target, line, col))
        self._emit(A.Continue(line, col, None))
        self.cur_state = target

    def _continue_to(self, target):
        """Seal the current state with a bare `continue;` (the
        state was already set inside the enclosing if)."""
        line, col = self.fn.line, self.fn.col
        self._emit(A.Continue(line, col, None))
        self.cur_state = target

    def _seal_return(self, extra):
        """Seal the current state with end-of-iteration: any
        side-effect statements, then `state = -1; return none;`."""
        line, col = self.fn.line, self.fn.col
        for s in extra:
            self._emit(s)
        self._emit(self._state_write(-1, line, col))
        self._emit(A.Return(self._none_lit(line, col), line, col))
        self.cur_state = self._new_state()

    def _split_block(self, stmts, cont):
        """Compile a statement list to states, starting in the
        current state; `cont` is the state to jump to when the
        block finishes normally. Returns the block's first state."""
        first = self.cur_state
        self._push()
        self._process_stmts(stmts)
        self._pop()
        self._jump(cont)
        return first

    def _split_block_fresh(self, stmts, cont):
        """Like _split_block, but the block starts in a fresh state
        (for branches, which must not share the enclosing segment)."""
        self.cur_state = self._new_state()
        return self._split_block(stmts, cont)

    def _process_stmts(self, stmts):
        for s in stmts:
            self._split_stmt(s)

    # ------------------------------------------------------------------
    # Split-mode statement processing (appends to cur_state).
    # ------------------------------------------------------------------
    def _split_stmt(self, s):
        if isinstance(s, A.Yield):
            t = self.prove_type(s.expr)
            if t is not None and t != self.elem:
                raise ForgeError(
                    "yield value of type "
                    f"{t} does not match generator element type {self.elem}",
                    s.line, s.col)
            nxt = self._new_state()
            self._emit(self._state_write(nxt, s.line, s.col))
            self._emit(A.Return(
                self._opt_some(self._rewrite_expr(s.expr), s.line, s.col),
                s.line, s.col))
            self.cur_state = nxt
            return
        if isinstance(s, A.Return):
            extra = []
            if s.expr is not None:
                extra.append(A.ExprStmt(self._rewrite_expr(s.expr),
                                        s.line, s.col))
            self._seal_return(extra)
            return
        if isinstance(s, (A.Break, A.Continue)):
            tgt = self._loop_target(s)
            if tgt is None:
                # Outside any loop, or targeting an inline loop:
                # emit as-is; the checker validates it.
                self._emit(s)
            else:
                self._jump(tgt)
            return
        if isinstance(s, A.Let):
            self._split_let(s)
            return
        if isinstance(s, A.Assign):
            rhs = self._rewrite_expr(s.expr)
            b = self._lookup(s.name)
            if b is not None and b[0] == "slot":
                self._emit(self._slot_write(b, rhs, s.line, s.col))
            else:
                self._emit(A.Assign(s.name, rhs, s.line, s.col))
            return
        if isinstance(s, A.IndexAssign):
            self._emit(A.IndexAssign(self._rewrite_expr(s.base),
                                     self._rewrite_expr(s.expr),
                                     s.line, s.col))
            return
        if isinstance(s, A.FieldAssign):
            self._emit(A.FieldAssign(self._rewrite_expr(s.target),
                                     self._rewrite_expr(s.expr),
                                     s.line, s.col))
            return
        if isinstance(s, A.ExprStmt):
            self._emit(A.ExprStmt(self._rewrite_expr(s.expr), s.line, s.col))
            return
        if isinstance(s, A.Block):
            self._push()
            self._process_stmts(s.stmts)
            self._pop()
            return
        if isinstance(s, A.If):
            cond = self._rewrite_expr(s.cond)
            if self._has_yield(s.then) or (s.els is not None
                                           and self._has_yield(s.els)):
                join = self._new_state()
                here = self.cur_state
                then_first = self._split_block_fresh(s.then.stmts, join)
                if s.els is not None:
                    else_first = self._split_block_fresh(s.els.stmts, join)
                else:
                    else_first = join
                self.cur_state = here
                self._emit(A.If(
                    cond,
                    A.Block([self._state_write(then_first, s.line, s.col)]),
                    A.Block([self._state_write(else_first, s.line, s.col)]),
                    s.line, s.col))
                self._continue_to(join)
            else:
                self._push()
                then_stmts = self._inline_stmts(s.then.stmts)
                self._pop()
                els_stmts = None
                if s.els is not None:
                    self._push()
                    els_stmts = self._inline_stmts(s.els.stmts)
                    self._pop()
                self._emit(A.If(cond, A.Block(then_stmts),
                                A.Block(els_stmts) if els_stmts is not None
                                else None, s.line, s.col))
            return
        if isinstance(s, A.While):
            cond = self._rewrite_expr(s.cond)
            if self._has_yield(s.body):
                exit_state = self._new_state()
                head = self._new_state()
                here = self.cur_state
                self.loop_stack.append((s.label, True, exit_state, head))
                body_first = self._split_block_fresh(s.body.stmts, head)
                self.loop_stack.pop()
                self.cur_state = head
                self._emit(A.If(
                    cond,
                    A.Block([self._state_write(body_first, s.line, s.col)]),
                    A.Block([self._state_write(exit_state, s.line, s.col)]),
                    s.line, s.col))
                self._continue_to(exit_state)
                self.cur_state = here
                self._jump(head)
                self.cur_state = exit_state
            else:
                enclosing = list(self.loop_stack)
                here = self.cur_state
                self.loop_stack.append((s.label, False, None, None))
                self._push()
                body_stmts = self._inline_stmts(s.body.stmts)
                self._pop()
                self.loop_stack.pop()
                self._emit(A.While(cond, A.Block(body_stmts), s.line, s.col,
                                   s.label))
                self._emit(self._inline_guard(s.line, s.col, here, enclosing))
            return
        if isinstance(s, A.For):
            self._split_for(s)
            return
        if isinstance(s, A.Match):
            if self._has_yield(s):
                raise ForgeError(
                    "yield cannot appear inside a match arm in v1 "
                    "(use if/else)", s.line, s.col)
            self._emit(self._opaque_match(s))
            return
        if isinstance(s, A.ComptimeIf):
            if self._has_yield(s):
                raise ForgeError(
                    "yield cannot appear inside a comptime if branch in v1",
                    s.line, s.col)
            self._emit(self._opaque_comptime(s))
            return
        if isinstance(s, A.Scope):
            if self._has_yield(s.body):
                raise ForgeError(
                    "yield cannot appear inside a scope block in v1",
                    s.line, s.col)
            self._push()
            body_stmts = self._inline_stmts(s.body.stmts)
            self._pop()
            self._emit(A.Scope(A.Block(body_stmts), s.line, s.col))
            return
        if isinstance(s, A.Spawn):
            self._emit(A.Spawn(self._rewrite_expr(s.call), s.line, s.col))
            return
        # Unknown statement shape: rewrite its expressions
        # generically and emit as-is (the checker decides).
        self._emit(self._rewrite_stmt_generic(s))

    def _split_let(self, s):
        typ = s.ann
        if typ is None:
            typ = self.prove_type(s.expr)
        if typ is None:
            raise ForgeError(
                f"generator local '{s.name}' needs a type annotation in v1 "
                "(the desugar cannot infer its type from the right-hand "
                "side)", s.line, s.col)
        if typ not in GEN_ELEM_TYPES:
            raise ForgeError(
                f"generator local '{s.name}' has type {typ}; only int, str, "
                "and bool locals are supported in v1", s.line, s.col)
        rhs = self._rewrite_expr(s.expr)
        binding = self._declare_slot(s.name, typ, s.line, s.col)
        self._emit(self._slot_write(binding, rhs, s.line, s.col))

    def _loop_target(self, s):
        """The state a break/continue jumps to, or None when it
        targets an inline loop (emit as-is) or no loop at all."""
        if s.label is not None:
            for label, is_split, brk, cont in reversed(self.loop_stack):
                if label == s.label:
                    if not is_split:
                        return None
                    return brk if isinstance(s, A.Break) else cont
            return None
        for _label, is_split, brk, cont in reversed(self.loop_stack):
            if not is_split:
                return None
            return brk if isinstance(s, A.Break) else cont
        return None

    def _split_for(self, s):
        """`for v in lo..hi` containing a yield: evaluate the bounds
        once into slots at loop entry, then header/body/increment
        states. Any other source with a yield inside is an error."""
        kind = self._for_source_kind(s.expr)
        if kind != "range":
            if self._has_yield(s.body):
                if kind == "range_expr":
                    raise ForgeError(
                        "for over a range expression is not supported in v1 "
                        "(use a literal lo..hi range or a while loop)",
                        s.line, s.col)
                raise ForgeError(
                    "for over an array cannot contain yield in v1 (use "
                    "while, or a for loop over a range)", s.line, s.col)
            # No yield: an ordinary for, inlined.
            enclosing = list(self.loop_stack)
            here = self.cur_state
            self.loop_stack.append((s.label, False, None, None))
            self._push()
            vtype = self.prove_type(s.expr)
            if vtype == "range":
                self.scope[-1][s.name] = ("opaque", "int")
            elif vtype is not None and vtype.startswith("["):
                self.scope[-1][s.name] = ("opaque", vtype[1:-1])
            else:
                self.scope[-1][s.name] = ("opaque", None)
            body_stmts = self._inline_stmts(s.body.stmts)
            self._pop()
            self.loop_stack.pop()
            self._emit(A.For(s.name, self._rewrite_expr(s.expr),
                             A.Block(body_stmts), s.line, s.col, s.label))
            self._emit(self._inline_guard(s.line, s.col, here, enclosing))
            return
        # Range form: the source must be a literal RangeLit.
        lo_rw = self._rewrite_expr(s.expr.start)
        hi_rw = self._rewrite_expr(s.expr.end)
        # Allocate the loop-var slot directly (no frame entry here):
        # the binding lives only in the body frame, so the name does
        # not leak past the loop.
        _lv_arr, lv_idx = self._alloc_slot("int")
        lv_binding = ("slot", "slots_i", lv_idx, "int")
        _harr, hi_idx = self._alloc_slot("int")
        exit_state = self._new_state()
        head = self._new_state()
        inc = self._new_state()
        here = self.cur_state
        self.loop_stack.append((s.label, True, exit_state, inc))
        self._push()
        self.scope[-1][s.name] = lv_binding
        body_first = self._split_block_fresh(s.body.stmts, inc)
        self._pop()
        self.loop_stack.pop()
        # Increment state: lv += 1; jump to the header.
        self.cur_state = inc
        self._emit(A.IndexAssign(
            A.Index(A.FieldAccess(self._gvar(s.line, s.col), "slots_i",
                                  s.line, s.col),
                    A.IntLit(lv_binding[2], s.line, s.col), s.line, s.col),
            A.BinOp("+", self._slot_read(lv_binding, s.line, s.col),
                    A.IntLit(1, s.line, s.col), s.line, s.col),
            s.line, s.col))
        self._jump(head)
        # Header state: if (lv < hi) body else exit; continue.
        self.cur_state = head
        hi_read = A.Index(
            A.FieldAccess(self._gvar(s.line, s.col), "slots_i", s.line, s.col),
            A.IntLit(hi_idx, s.line, s.col), s.line, s.col)
        self._emit(A.If(
            A.BinOp("<", self._slot_read(lv_binding, s.line, s.col),
                    hi_read, s.line, s.col),
            A.Block([self._state_write(body_first, s.line, s.col)]),
            A.Block([self._state_write(exit_state, s.line, s.col)]),
            s.line, s.col))
        self._continue_to(exit_state)
        # Entry, in the enclosing segment: lv = lo; hi = hi_expr;
        # jump to the header.
        self.cur_state = here
        self._emit(self._slot_write(lv_binding, lo_rw, s.line, s.col))
        self._emit(A.IndexAssign(
            A.Index(A.FieldAccess(self._gvar(s.line, s.col), "slots_i",
                                  s.line, s.col),
                    A.IntLit(hi_idx, s.line, s.col), s.line, s.col),
            hi_rw, s.line, s.col))
        self._jump(head)
        self.cur_state = exit_state

    def _for_source_kind(self, expr):
        """'range' for a literal RangeLit, 'range_expr' for a
        provably range-typed expression, 'array' otherwise."""
        if isinstance(expr, A.RangeLit):
            return "range"
        t = self.prove_type(expr)
        if t == "range":
            return "range_expr"
        return "array"

    # ------------------------------------------------------------------
    # Inline-mode processing (constructs without yields): returns a
    # new statement list. Lets become slot writes; break/continue
    # targeting a split loop become [state-write, continue];
    # returns become end-of-iteration sequences.
    # ------------------------------------------------------------------
    def _inline_stmts(self, stmts):
        out = []
        for s in stmts:
            out.extend(self._inline_stmt(s))
        return out

    def _inline_stmt(self, s):
        if isinstance(s, A.Yield):
            raise ForgeError("internal error: unresolved yield",
                             s.line, s.col)
        if isinstance(s, A.Return):
            extra = []
            if s.expr is not None:
                extra.append(A.ExprStmt(self._rewrite_expr(s.expr),
                                        s.line, s.col))
            line, col = s.line, s.col
            return extra + [self._state_write(-1, line, col),
                            A.Return(self._none_lit(line, col), line, col)]
        if isinstance(s, (A.Break, A.Continue)):
            tgt = self._loop_target(s)
            if tgt is None:
                return [s]
            return self._unwind_jump(s, tgt, self.loop_stack)
        if isinstance(s, A.Let):
            typ = s.ann
            if typ is None:
                typ = self.prove_type(s.expr)
            if typ is None:
                raise ForgeError(
                    f"generator local '{s.name}' needs a type annotation "
                    "in v1 (the desugar cannot infer its type from the "
                    "right-hand side)", s.line, s.col)
            if typ not in GEN_ELEM_TYPES:
                raise ForgeError(
                    f"generator local '{s.name}' has type {typ}; only int, "
                    "str, and bool locals are supported in v1",
                    s.line, s.col)
            rhs = self._rewrite_expr(s.expr)
            binding = self._declare_slot(s.name, typ, s.line, s.col)
            return [self._slot_write(binding, rhs, s.line, s.col)]
        if isinstance(s, A.Assign):
            rhs = self._rewrite_expr(s.expr)
            b = self._lookup(s.name)
            if b is not None and b[0] == "slot":
                return [self._slot_write(b, rhs, s.line, s.col)]
            return [A.Assign(s.name, rhs, s.line, s.col)]
        if isinstance(s, A.IndexAssign):
            return [A.IndexAssign(self._rewrite_expr(s.base),
                                  self._rewrite_expr(s.expr),
                                  s.line, s.col)]
        if isinstance(s, A.FieldAssign):
            return [A.FieldAssign(self._rewrite_expr(s.target),
                                  self._rewrite_expr(s.expr),
                                  s.line, s.col)]
        if isinstance(s, A.ExprStmt):
            return [A.ExprStmt(self._rewrite_expr(s.expr), s.line, s.col)]
        if isinstance(s, A.Block):
            self._push()
            out = self._inline_stmts(s.stmts)
            self._pop()
            return [A.Block(out)]
        if isinstance(s, A.If):
            cond = self._rewrite_expr(s.cond)
            self._push()
            then_stmts = self._inline_stmts(s.then.stmts)
            self._pop()
            els_stmts = None
            if s.els is not None:
                self._push()
                els_stmts = self._inline_stmts(s.els.stmts)
                self._pop()
            return [A.If(cond, A.Block(then_stmts),
                         A.Block(els_stmts) if els_stmts is not None else None,
                         s.line, s.col)]
        if isinstance(s, A.While):
            cond = self._rewrite_expr(s.cond)
            enclosing = list(self.loop_stack)
            here = self.cur_state
            self.loop_stack.append((s.label, False, None, None))
            self._push()
            body_stmts = self._inline_stmts(s.body.stmts)
            self._pop()
            self.loop_stack.pop()
            return [A.While(cond, A.Block(body_stmts), s.line, s.col, s.label),
                    self._inline_guard(s.line, s.col, here, enclosing)]
        if isinstance(s, A.For):
            if self._has_yield(s.body):
                # Unreachable: an inline body never contains a yield
                # (has_yield is transitive), but fail loudly if the
                # invariant ever breaks.
                raise ForgeError("internal error: unresolved yield",
                                 s.line, s.col)
            enclosing = list(self.loop_stack)
            here = self.cur_state
            self.loop_stack.append((s.label, False, None, None))
            self._push()
            vtype = self.prove_type(s.expr)
            if vtype == "range":
                self.scope[-1][s.name] = ("opaque", "int")
            elif vtype is not None and vtype.startswith("["):
                self.scope[-1][s.name] = ("opaque", vtype[1:-1])
            else:
                self.scope[-1][s.name] = ("opaque", None)
            body_stmts = self._inline_stmts(s.body.stmts)
            self._pop()
            self.loop_stack.pop()
            return [A.For(s.name, self._rewrite_expr(s.expr),
                          A.Block(body_stmts), s.line, s.col, s.label),
                    self._inline_guard(s.line, s.col, here, enclosing)]
        if isinstance(s, A.Match):
            if self._has_yield(s):
                raise ForgeError(
                    "yield cannot appear inside a match arm in v1 "
                    "(use if/else)", s.line, s.col)
            return [self._opaque_match(s)]
        if isinstance(s, A.ComptimeIf):
            if self._has_yield(s):
                raise ForgeError(
                    "yield cannot appear inside a comptime if branch in v1",
                    s.line, s.col)
            return [self._opaque_comptime(s)]
        if isinstance(s, A.Scope):
            if self._has_yield(s.body):
                raise ForgeError(
                    "yield cannot appear inside a scope block in v1",
                    s.line, s.col)
            self._push()
            body_stmts = self._inline_stmts(s.body.stmts)
            self._pop()
            return [A.Scope(A.Block(body_stmts), s.line, s.col)]
        if isinstance(s, A.Spawn):
            return [A.Spawn(self._rewrite_expr(s.call), s.line, s.col)]
        return [self._rewrite_stmt_generic(s)]

    # ------------------------------------------------------------------
    # Opaque-mode processing (lambda bodies, match arms, comptime
    # branches): lets stay lets; only expressions are rewritten.
    # `in_lambda` selects the lambda rules (its own return, its own
    # loop stack); otherwise returns end the iteration and breaks
    # use the generator's loop stack.
    # ------------------------------------------------------------------
    def _opaque_stmts(self, stmts, extra_opaque, in_lambda, loops):
        out = []
        self._push()
        for name, typ in extra_opaque:
            self.scope[-1][name] = ("opaque", typ)
        for s in stmts:
            out.extend(self._opaque_stmt(s, in_lambda, loops))
        self._pop()
        return out

    def _opaque_stmt(self, s, in_lambda, loops):
        if isinstance(s, A.Yield):
            raise ForgeError(
                "yield cannot appear inside a nested function or closure "
                "in v1" if in_lambda else
                "internal error: unresolved yield", s.line, s.col)
        if isinstance(s, A.Return):
            if in_lambda:
                expr = (self._rewrite_expr(s.expr)
                        if s.expr is not None else None)
                return [A.Return(expr, s.line, s.col)]
            extra = []
            if s.expr is not None:
                extra.append(A.ExprStmt(self._rewrite_expr(s.expr),
                                        s.line, s.col))
            line, col = s.line, s.col
            return extra + [self._state_write(-1, line, col),
                            A.Return(self._none_lit(line, col), line, col)]
        if isinstance(s, (A.Break, A.Continue)):
            tgt = self._loop_target_in(loops, s)
            if tgt is None:
                return [s]
            return self._unwind_jump(s, tgt, loops)
        if isinstance(s, A.Let):
            rhs = self._rewrite_expr(s.expr)
            self.scope[-1][s.name] = ("opaque", s.ann)
            return [A.Let(s.name, s.mutable, s.ann, rhs, s.line, s.col)]
        if isinstance(s, A.Assign):
            rhs = self._rewrite_expr(s.expr)
            b = self._lookup(s.name)
            if b is not None and b[0] == "slot":
                return [self._slot_write(b, rhs, s.line, s.col)]
            return [A.Assign(s.name, rhs, s.line, s.col)]
        if isinstance(s, A.IndexAssign):
            return [A.IndexAssign(self._rewrite_expr(s.base),
                                  self._rewrite_expr(s.expr),
                                  s.line, s.col)]
        if isinstance(s, A.FieldAssign):
            return [A.FieldAssign(self._rewrite_expr(s.target),
                                  self._rewrite_expr(s.expr),
                                  s.line, s.col)]
        if isinstance(s, A.ExprStmt):
            return [A.ExprStmt(self._rewrite_expr(s.expr), s.line, s.col)]
        if isinstance(s, A.Block):
            return [A.Block(self._opaque_stmts(
                s.stmts, [], in_lambda, list(loops)))]
        if isinstance(s, A.If):
            cond = self._rewrite_expr(s.cond)
            then_stmts = self._opaque_stmts(
                s.then.stmts, [], in_lambda, list(loops))
            els_stmts = None
            if s.els is not None:
                els_stmts = self._opaque_stmts(
                    s.els.stmts, [], in_lambda, list(loops))
            return [A.If(cond, A.Block(then_stmts),
                         A.Block(els_stmts) if els_stmts is not None else None,
                         s.line, s.col)]
        if isinstance(s, A.While):
            cond = self._rewrite_expr(s.cond)
            loops2 = list(loops)
            loops2.append((s.label, False, None, None))
            body_stmts = self._opaque_stmts(
                s.body.stmts, [], in_lambda, loops2)
            out = [A.While(cond, A.Block(body_stmts), s.line, s.col, s.label)]
            # No guard inside a lambda: `g` is out of scope there
            # (and a lambda's jumps can never target a split loop,
            # its loop stack is fresh). In a match/comptime arm the
            # guard unwinds exactly like the inline-mode one.
            if not in_lambda:
                out.append(self._inline_guard(
                    s.line, s.col, self.cur_state, loops))
            return out
        if isinstance(s, A.For):
            loops2 = list(loops)
            loops2.append((s.label, False, None, None))
            vtype = self.prove_type(s.expr)
            if vtype == "range":
                extra = [(s.name, "int")]
            elif vtype is not None and vtype.startswith("["):
                extra = [(s.name, vtype[1:-1])]
            else:
                extra = [(s.name, None)]
            body_stmts = self._opaque_stmts(
                s.body.stmts, extra, in_lambda, loops2)
            out = [A.For(s.name, self._rewrite_expr(s.expr),
                         A.Block(body_stmts), s.line, s.col, s.label)]
            if not in_lambda:
                out.append(self._inline_guard(
                    s.line, s.col, self.cur_state, loops))
            return out
        if isinstance(s, A.Match):
            if self._has_yield(s):
                raise ForgeError(
                    "yield cannot appear inside a match arm in v1 "
                    "(use if/else)", s.line, s.col)
            return [self._opaque_match_in(s, in_lambda, loops)]
        if isinstance(s, A.ComptimeIf):
            if self._has_yield(s):
                raise ForgeError(
                    "yield cannot appear inside a comptime if branch in v1",
                    s.line, s.col)
            return [self._opaque_comptime_in(s, in_lambda, loops)]
        if isinstance(s, A.Scope):
            if self._has_yield(s.body):
                raise ForgeError(
                    "yield cannot appear inside a scope block in v1",
                    s.line, s.col)
            body_stmts = self._opaque_stmts(
                s.body.stmts, [], in_lambda, list(loops))
            return [A.Scope(A.Block(body_stmts), s.line, s.col)]
        if isinstance(s, A.Spawn):
            return [A.Spawn(self._rewrite_expr(s.call), s.line, s.col)]
        return [self._rewrite_stmt_generic(s)]

    def _loop_target_in(self, loops, s):
        if s.label is not None:
            for label, is_split, brk, cont in reversed(loops):
                if label == s.label:
                    if not is_split:
                        return None
                    return brk if isinstance(s, A.Break) else cont
            return None
        for _label, is_split, brk, cont in reversed(loops):
            if not is_split:
                return None
            return brk if isinstance(s, A.Break) else cont
        return None

    def _match_bindings(self, pat):
        out = []
        if getattr(pat, "binding", None):
            out.append((pat.binding, None))
        if getattr(pat, "kind", None) == "struct":
            for _fname, fpat in (pat.fields or []):
                if getattr(fpat, "kind", None) == "binding":
                    out.append((fpat.value, None))
        return out

    def _opaque_match(self, s):
        return self._opaque_match_in(s, False, list(self.loop_stack))

    def _opaque_match_in(self, s, in_lambda, loops):
        scr = self._rewrite_expr(s.expr)
        arms = []
        for pat, arm in s.arms:
            bindings = self._match_bindings(pat)
            body = self._opaque_stmts(arm.stmts, bindings, in_lambda,
                                      list(loops))
            arms.append((pat, A.Block(body)))
        return A.Match(scr, arms, s.line, s.col)

    def _opaque_comptime(self, s):
        return self._opaque_comptime_in(s, False, list(self.loop_stack))

    def _opaque_comptime_in(self, s, in_lambda, loops):
        then = A.Block(self._opaque_stmts(s.then.stmts, [], in_lambda,
                                          list(loops)))
        els = None
        if s.els is not None:
            els = A.Block(self._opaque_stmts(s.els.stmts, [], in_lambda,
                                             list(loops)))
        return A.ComptimeIf(s.pred, then, els, s.line, s.col)

    # ------------------------------------------------------------------
    # Expression rewriter: lifted names become slot reads.
    # ------------------------------------------------------------------
    def _rewrite_expr(self, e):
        if e is None:
            return None
        if isinstance(e, A.Var):
            b = self._lookup(e.name)
            if b is not None and b[0] == "slot":
                return self._slot_read(b, e.line, e.col)
            return e
        if isinstance(e, A.Lambda):
            self._push()
            for pname, ptype in e.params:
                self.scope[-1][pname] = ("opaque", ptype)
            body = self._opaque_stmts(e.body.stmts, [], True, [])
            self._pop()
            return A.Lambda(e.params, e.ret, A.Block(body),
                            e.line, e.col, e.captures, e.fn_type)
        if isinstance(e, A.BinOp):
            return A.BinOp(e.op, self._rewrite_expr(e.left),
                           self._rewrite_expr(e.right), e.line, e.col)
        if isinstance(e, A.UnaryOp):
            return A.UnaryOp(e.op, self._rewrite_expr(e.expr),
                             e.line, e.col)
        if isinstance(e, A.Call):
            return A.Call(e.name, [self._rewrite_expr(a) for a in e.args],
                          e.line, e.col, e.concrete_type, e.fn_type,
                          e.trycall_fn_type)
        if isinstance(e, A.IndirectCall):
            return A.IndirectCall(self._rewrite_expr(e.callee),
                                  [self._rewrite_expr(a) for a in e.args],
                                  e.line, e.col, e.fn_type)
        if isinstance(e, A.Index):
            return A.Index(self._rewrite_expr(e.base),
                           self._rewrite_expr(e.index), e.line, e.col)
        if isinstance(e, A.TupleIndex):
            return A.TupleIndex(self._rewrite_expr(e.base), e.index,
                                e.line, e.col)
        if isinstance(e, A.FieldAccess):
            return A.FieldAccess(self._rewrite_expr(e.base), e.field,
                                 e.line, e.col)
        if isinstance(e, A.MethodCall):
            return A.MethodCall(self._rewrite_expr(e.base), e.method,
                                [self._rewrite_expr(a) for a in e.args],
                                e.line, e.col)
        if isinstance(e, A.StructLit):
            return A.StructLit(e.name,
                               [(fn, self._rewrite_expr(fe))
                                for fn, fe in e.fields],
                               e.line, e.col, e.concrete_type)
        if isinstance(e, A.ArrayLit):
            return A.ArrayLit([self._rewrite_expr(x) for x in e.elems],
                              e.line, e.col)
        if isinstance(e, A.TupleLit):
            return A.TupleLit([self._rewrite_expr(x) for x in e.elems],
                              e.line, e.col)
        if isinstance(e, A.RangeLit):
            return A.RangeLit(self._rewrite_expr(e.start),
                              self._rewrite_expr(e.end), e.line, e.col)
        if isinstance(e, A.Cast):
            return A.Cast(self._rewrite_expr(e.expr), e.target,
                          e.line, e.col)
        if isinstance(e, A.Try):
            return A.Try(self._rewrite_expr(e.expr), e.line, e.col,
                         e.kind, e.value_type, e.ret_type, e.error_type)
        if isinstance(e, A.NamedExpr):
            raise ForgeError(
                "walrus ':=' is not supported inside a generator function "
                "in v1 (write the assignment before the if/while instead)",
                e.line, e.col)
        return e

    def _rewrite_stmt_generic(self, s):
        """Best-effort expression rewrite for statement shapes the
        splitter does not know: recurse into dataclass fields."""
        import dataclasses
        import copy
        if not dataclasses.is_dataclass(s):
            return s
        out = copy.copy(s)
        for f in dataclasses.fields(s):
            v = getattr(s, f.name)
            if isinstance(v, list):
                setattr(out, f.name, [self._rewrite_expr(x)
                                      if dataclasses.is_dataclass(x) else x
                                      for x in v])
            elif dataclasses.is_dataclass(v):
                setattr(out, f.name, self._rewrite_expr(v))
        return out

    # ------------------------------------------------------------------
    # The transform itself.
    # ------------------------------------------------------------------
    def _transform(self, fn, elem):
        self.kind_counter += 1
        self.fn = fn
        self.elem = elem
        self.kind = self.kind_counter
        self.scope = [{}]
        self.int_count = 1
        self.str_count = 0
        self.bool_count = 0
        self.states = {0: []}
        self.cur_state = 0
        self.next_state = 1
        self.end_state = None
        self.loop_stack = []
        step_name = fn.name + "_next"
        if step_name in self.fn_table:
            raise ForgeError(
                f"generator '{fn.name}' needs a step function named "
                f"'{step_name}' but one already exists; rename it",
                fn.line, fn.col)
        # Seed the scope with the params (slots 1.. for ints).
        param_slots = {}
        for pname, ptype in fn.params:
            if ptype not in GEN_ELEM_TYPES:
                raise ForgeError(
                    f"generator parameter '{pname}' has type {ptype}; only "
                    "int, str, and bool parameters are supported in v1",
                    fn.line, fn.col)
            param_slots[pname] = self._declare_slot(
                pname, ptype, fn.line, fn.col)
        # Split the body: state 0 is the first segment; the end
        # state returns none.
        self.end_state = self._new_state()
        self._split_block(fn.body.stmts, self.end_state)
        self.states[self.end_state] = [
            A.Return(self._none_lit(fn.line, fn.col), fn.line, fn.col)]
        # The constructor: slot arrays in annotated lets, then the
        # struct literal. Param slots hold the params; local slots
        # hold zero.
        si_elems = [A.IntLit(0, fn.line, fn.col)]
        for _ in range(1, self.int_count):
            si_elems.append(A.IntLit(0, fn.line, fn.col))
        ss_elems = [A.StrLit("", fn.line, fn.col)
                    for _ in range(self.str_count)]
        sb_elems = [A.BoolLit(False, fn.line, fn.col)
                    for _ in range(self.bool_count)]
        for pname, b in param_slots.items():
            _k, arr, idx, _t = b
            v = A.Var(pname, fn.line, fn.col)
            if arr == "slots_i":
                si_elems[idx] = v
            elif arr == "slots_s":
                ss_elems[idx] = v
            else:
                sb_elems[idx] = v
        ctor_body = [
            A.Let("si", False, "[int]", A.ArrayLit(si_elems, fn.line, fn.col),
                  fn.line, fn.col),
            A.Let("ss", False, "[str]", A.ArrayLit(ss_elems, fn.line, fn.col),
                  fn.line, fn.col),
            A.Let("sb", False, "[bool]",
                  A.ArrayLit(sb_elems, fn.line, fn.col),
                  fn.line, fn.col),
            A.Return(A.StructLit("Generator", [
                ("kind", A.IntLit(self.kind, fn.line, fn.col)),
                ("cur", _zero(elem, fn.line, fn.col)),
                ("slots_i", A.Var("si", fn.line, fn.col)),
                ("slots_s", A.Var("ss", fn.line, fn.col)),
                ("slots_b", A.Var("sb", fn.line, fn.col)),
            ], fn.line, fn.col), fn.line, fn.col),
        ]
        ctor = A.FuncDef(fn.name, fn.params, fn.ret, A.Block(ctor_body),
                         fn.line, fn.col, fn.is_extern, fn.type_params,
                         fn.file)
        # The step function: while (true) dispatch over the states,
        # then a trailing return (definite-return analysis, p13).
        dispatch = []
        for sid in sorted(self.states):
            cond = A.BinOp(
                "==",
                A.Index(A.FieldAccess(self._gvar(fn.line, fn.col), "slots_i",
                                      fn.line, fn.col),
                        A.IntLit(0, fn.line, fn.col), fn.line, fn.col),
                A.IntLit(sid, fn.line, fn.col), fn.line, fn.col)
            dispatch.append(A.If(cond, A.Block(self.states[sid]), None,
                                 fn.line, fn.col))
        dispatch.append(A.Return(self._none_lit(fn.line, fn.col),
                                 fn.line, fn.col))
        step_body = A.Block([
            A.While(A.BoolLit(True, fn.line, fn.col), A.Block(dispatch),
                    fn.line, fn.col, None),
            A.Return(self._none_lit(fn.line, fn.col), fn.line, fn.col),
        ])
        step = A.FuncDef(step_name, [("g", fn.ret)], f"Option<{elem}>",
                         step_body, fn.line, fn.col, False, None, fn.file)
        self.fn_table[step_name] = step
        return ctor, step


def resolve_generators(program, structs, struct_params, target, freestanding):
    """Program-level generator transform (see the module docstring).
    Returns the (possibly rewritten) program; raises ForgeError on
    any v1 violation. A no-op when the program defines no generator."""
    return _GenTransform(program, structs, struct_params, target,
                         freestanding).run()
