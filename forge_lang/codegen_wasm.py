"""Forge -> WebAssembly backend (v2: int/float/bool + str + arrays).

Emits a real .wasm binary (not text) for a subset of Forge:
  int (i64), float (f64), bool (i32), str (i32 pointer),
  arrays (i32 handle, see below); functions, let/let mut,
  assign, index assign, if/else, while, return, calls,
  recursion, binary/unary ops, print/println, len, push,
  fail, assert.
NOT supported (clear error, not silent miscompile):
  structs, enums, match, spawn, extern, file I/O, args,
  http, clock, float printing, array printing.
WASM integer arithmetic wraps (like RISC-V, unlike Forge safe
mode) and division by zero traps — the same trade-off as the
big32 backend, stated here, not hidden. Array index out of
bounds traps (unreachable) rather than aborting with a
message, because the module has no host print for errors.
Test it with node: node tools/run_wasm.mjs out.wasm
  (node is available in this VM; no clang/wasm-ld needed,
  because this backend writes the binary directly).
  That runner prints only main()'s return value. String
  output goes to an exported stdout buffer (see below);
  read it with a host that inspects instance memory,
  e.g. the script in docs/WASM_STRINGS.md.

Memory layout (one memory, min 1 page, exported as
"memory"; it grows on demand via the bump allocator):
  0..3      stdout length (u32, bytes written so far)
  8..8199   stdout bytes (capacity 8192; output past
            that is TRUNCATED — a documented v2 limit,
            not a silent success)
  8200..8231 int->decimal scratch (20 digit bytes +
            one sign byte at 8231)
  8320..    static string blobs, 8-aligned, each
            [u32 length][utf-8 bytes]; gaps between
            blobs are zero-filled by module semantics
  heap -->  bump-allocated region after the last blob;
            a mutable i32 global holds the heap pointer
            (8-byte aligned). There is NO free and NO
            GC: allocations in a loop grow memory.
            That is the v2 trade-off, stated here.

Value representations:
  str: an i32 pointer to a length-prefixed blob
    [u32 length][bytes]. String literals live in the
    static area; concatenation allocates a new blob.
  array: an i32 HANDLE (a pointer to a 4-byte cell
    holding the data pointer). The data block is
    [u32 len][u32 cap][elements...]. The handle
    indirection is what makes push-with-growth work:
    push may allocate a bigger block and rewrite the
    handle's cell, so the caller's variable — which
    holds the handle — sees the new block. Element
    sizes: int/float 8 bytes, bool/str 4 bytes.
    One semantic divergence from native, documented
    here: because the handle is shared, push through
    a function parameter DOES reach the caller in
    WASM, while native push to a parameter does not.
    In-place index assignment behaves the same in
    both backends.
  print/println: append to the stdout buffer, with
    one space between arguments (matching native
    output shape). Supported argument types: str,
    int (decimal), bool ("true"/"false"). Float and
    array arguments are a compile error. fail(msg)
    appends msg to the buffer and traps; assert(c,
    msg) does the same when c is false.
"""

from .errors import ForgeError
from . import ast_nodes as A


def uleb(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def sleb(n):
    out = bytearray()
    more = True
    while more:
        b = n & 0x7F
        n >>= 7
        if (n == 0 and not (b & 0x40)) or (n == -1 and (b & 0x40)):
            more = False
        else:
            b |= 0x80
        out.append(b)
    return bytes(out)


def vec(items):
    return uleb(len(items)) + b"".join(items)


def section(sid, payload):
    return bytes([sid]) + uleb(len(payload)) + payload


def name(s):
    b = s.encode()
    return uleb(len(b)) + b


I32 = 0x7F
I64 = 0x7E
F64 = 0x7C

# Memory layout constants (see header).
OUT_LEN_ADDR = 0
OUT_BASE = 8
OUT_CAP = 8192
SCRATCH = 8200
SIGN_ADDR = 8231
STATIC_BASE = 8320


def valtype(t):
    if t == "int":
        return I64
    if t == "float":
        return F64
    if t == "bool":
        return I32
    if t == "str":
        return I32
    if t and t.startswith("[") and t.endswith("]"):
        return I32
    raise ForgeError(f"wasm: type {t} is not supported (v2: int, float, bool, str, arrays only)")


def elem_size(elem):
    if elem in ("int", "float"):
        return 8
    if elem in ("bool", "str"):
        return 4
    raise ForgeError(f"wasm: array element type {elem} is not supported")


def is_wasm_type(t):
    if t in ("int", "float", "bool", "str"):
        return True
    if t and t.startswith("[") and t.endswith("]"):
        return t[1:-1] in ("int", "float", "bool", "str")
    return False


# WASM opcodes used by the helper functions.
I32_CONST = b"\x41"
I64_CONST = b"\x42"
F64_CONST = b"\x44"
LOCAL_GET = b"\x20"
LOCAL_SET = b"\x21"
GLOBAL_GET = b"\x23"
GLOBAL_SET = b"\x24"
CALL = b"\x10"
DROP = b"\x1a"
BLOCK = b"\x02"
LOOP = b"\x03"
IF = b"\x04"
ELSE = b"\x05"
END = b"\x0b"
BR = b"\x0c"
BR_IF = b"\x0d"
RETURN = b"\x0f"
UNREACHABLE = b"\x00"
EMPTY = b"\x40"
I32_T = b"\x7f"
I64_T = b"\x7e"


def i32_const(n):
    return I32_CONST + sleb(n)


def i64_const(n):
    return I64_CONST + sleb(n)


def local_get(i):
    return LOCAL_GET + uleb(i)


def local_set(i):
    return LOCAL_SET + uleb(i)


def call_fn(i):
    return CALL + uleb(i)


def memarg(align, offset):
    return uleb(align) + uleb(offset)


def i32_load(offset=0):
    return b"\x28" + memarg(2, offset)


def i64_load(offset=0):
    return b"\x29" + memarg(3, offset)


def f64_load(offset=0):
    return b"\x2b" + memarg(3, offset)


def i32_load8_u(offset=0):
    return b"\x2d" + memarg(0, offset)


def i32_store(offset=0):
    return b"\x36" + memarg(2, offset)


def i64_store(offset=0):
    return b"\x37" + memarg(3, offset)


def f64_store(offset=0):
    return b"\x39" + memarg(3, offset)


def i32_store8(offset=0):
    return b"\x3a" + memarg(0, offset)


# Helper function definitions, in fixed order. Each is
# (name, param valtypes, result valtypes, local
# valtypes, body builder) where the builder takes the
# helper's own index map (name -> func index) and
# returns the body bytes (without the trailing end;
# code_entry appends it). Helper indices are assigned
# after the user's functions, in this list's order.
HELPER_NAMES = [
    "alloc", "memcpy", "memcmp_eq", "str_eq", "str_concat",
    "out_append", "out_str", "out_nl", "out_space", "out_i64",
    "arr_push_i64", "arr_push_f64", "arr_push_i32",
]


def build_helpers(hidx):
    """Return [(params, results, locals, body)] in HELPER_NAMES order."""
    out = []

    def code(params, results, locals_, body):
        return (params, results, locals_, body)

    # alloc(size: i32) -> i32. Locals: aligned, ptr, new_end, mem_bytes, need.
    b = bytearray()
    b += local_get(0) + i32_const(7) + b"\x6a" + i32_const(-8) + b"\x71" + local_set(1)
    b += GLOBAL_GET + uleb(0) + local_set(2)
    b += local_get(2) + local_get(1) + b"\x6a" + local_set(3)
    b += b"\x3f\x00" + i32_const(16) + b"\x74" + local_set(4)  # memory.size << 16
    b += local_get(3) + local_get(4) + b"\x4b"  # new_end > mem_bytes (unsigned)
    b += IF + EMPTY
    b += local_get(3) + local_get(4) + b"\x6b" + i32_const(65535) + b"\x6a"
    b += i32_const(16) + b"\x76" + local_set(5)  # ceil div by 65536
    b += local_get(5) + b"\x40\x00"  # memory.grow
    b += i32_const(0) + b"\x48"  # result < 0 (signed)
    b += IF + EMPTY + UNREACHABLE + END
    b += END
    b += local_get(3) + GLOBAL_SET + uleb(0)
    b += local_get(2)
    out.append(code([I32], [I32], [I32, I32, I32, I32, I32], bytes(b)))

    # memcpy(dst, src, n). Local: i.
    b = bytearray()
    b += i32_const(0) + local_set(3)
    b += BLOCK + EMPTY + LOOP + EMPTY
    b += local_get(3) + local_get(2) + b"\x4f" + BR_IF + uleb(1)
    b += local_get(0) + local_get(3) + b"\x6a"
    b += local_get(1) + local_get(3) + b"\x6a" + i32_load8_u()
    b += i32_store8()
    b += local_get(3) + i32_const(1) + b"\x6a" + local_set(3)
    b += BR + uleb(0) + END + END
    out.append(code([I32, I32, I32], [], [I32], bytes(b)))

    # memcmp_eq(a, b, n) -> i32. Locals: i, res.
    b = bytearray()
    b += i32_const(1) + local_set(4)
    b += i32_const(0) + local_set(3)
    b += BLOCK + EMPTY + LOOP + EMPTY
    b += local_get(3) + local_get(2) + b"\x4f" + BR_IF + uleb(1)
    b += local_get(0) + local_get(3) + b"\x6a" + i32_load8_u()
    b += local_get(1) + local_get(3) + b"\x6a" + i32_load8_u()
    b += b"\x46"  # i32.eq
    b += local_get(4) + b"\x71" + local_set(4)  # res &= eq
    b += local_get(3) + i32_const(1) + b"\x6a" + local_set(3)
    b += BR + uleb(0) + END + END
    b += local_get(4)
    out.append(code([I32, I32, I32], [I32], [I32, I32], bytes(b)))

    # str_eq(a, b) -> i32. Locals: la, lb.
    b = bytearray()
    b += local_get(0) + i32_load() + local_set(2)
    b += local_get(1) + i32_load() + local_set(3)
    b += local_get(2) + local_get(3) + b"\x47"  # i32.ne
    b += IF + I32_T + i32_const(0) + ELSE
    b += local_get(0) + i32_const(4) + b"\x6a"
    b += local_get(1) + i32_const(4) + b"\x6a"
    b += local_get(2) + call_fn(hidx["memcmp_eq"]) + END
    out.append(code([I32, I32], [I32], [I32, I32], bytes(b)))

    # str_concat(a, b) -> i32. Locals: la, lb, p.
    b = bytearray()
    b += local_get(0) + i32_load() + local_set(2)
    b += local_get(1) + i32_load() + local_set(3)
    b += i32_const(4) + local_get(2) + b"\x6a" + local_get(3) + b"\x6a"
    b += call_fn(hidx["alloc"]) + local_set(4)
    b += local_get(4) + local_get(2) + local_get(3) + b"\x6a" + i32_store()
    b += local_get(4) + i32_const(4) + b"\x6a"
    b += local_get(0) + i32_const(4) + b"\x6a"
    b += local_get(2) + call_fn(hidx["memcpy"])
    b += local_get(4) + i32_const(4) + b"\x6a" + local_get(2) + b"\x6a"
    b += local_get(1) + i32_const(4) + b"\x6a"
    b += local_get(3) + call_fn(hidx["memcpy"])
    b += local_get(4)
    out.append(code([I32, I32], [I32], [I32, I32, I32], bytes(b)))

    # out_append(p, n). Locals: avail, copy, curlen.
    b = bytearray()
    b += i32_const(OUT_LEN_ADDR) + i32_load() + local_set(4)
    b += i32_const(OUT_CAP) + local_get(4) + b"\x6b" + local_set(2)
    b += local_get(1) + local_get(2) + b"\x49"  # n < avail (unsigned)
    b += IF + I32_T + local_get(1) + ELSE + local_get(2) + END + local_set(3)
    b += i32_const(OUT_BASE) + local_get(4) + b"\x6a"
    b += local_get(0) + local_get(3) + call_fn(hidx["memcpy"])
    b += i32_const(OUT_LEN_ADDR) + local_get(4) + local_get(3) + b"\x6a"
    b += i32_store(OUT_LEN_ADDR)
    out.append(code([I32, I32], [], [I32, I32, I32], bytes(b)))

    # out_str(p).
    b = bytearray()
    b += local_get(0) + i32_const(4) + b"\x6a"
    b += local_get(0) + i32_load() + call_fn(hidx["out_append"])
    out.append(code([I32], [], [], bytes(b)))

    # out_nl().
    b = bytearray()
    b += i32_const(SCRATCH) + i32_const(10) + i32_store8()
    b += i32_const(SCRATCH) + i32_const(1) + call_fn(hidx["out_append"])
    out.append(code([], [], [], bytes(b)))

    # out_space().
    b = bytearray()
    b += i32_const(SCRATCH) + i32_const(32) + i32_store8()
    b += i32_const(SCRATCH) + i32_const(1) + call_fn(hidx["out_append"])
    out.append(code([], [], [], bytes(b)))

    # out_i64(v: i64). Locals: u, neg, pos, k.
    b = bytearray()
    b += local_get(0) + i64_const(0) + b"\x53" + local_set(2)  # neg = v < 0
    b += local_get(2) + IF + I64_T
    b += i64_const(0) + local_get(0) + b"\x7d"  # 0 - v
    b += ELSE + local_get(0) + END + local_set(1)
    b += i32_const(0) + local_set(3)
    b += local_get(1) + b"\x50"  # i64.eqz
    b += IF + EMPTY
    b += i32_const(SCRATCH) + i32_const(48) + i32_store8()
    b += i32_const(1) + local_set(3) + END
    b += BLOCK + EMPTY + LOOP + EMPTY
    b += local_get(1) + b"\x50" + BR_IF + uleb(1)
    b += i32_const(SCRATCH) + local_get(3) + b"\x6a"
    b += local_get(1) + i64_const(10) + b"\x82"  # rem_u
    b += b"\xa7" + i32_const(48) + b"\x6a"  # wrap + '0'
    b += i32_store8()
    b += local_get(3) + i32_const(1) + b"\x6a" + local_set(3)
    b += local_get(1) + i64_const(10) + b"\x80" + local_set(1)  # div_u
    b += BR + uleb(0) + END + END
    b += local_get(2) + IF + EMPTY
    b += i32_const(SIGN_ADDR) + i32_const(45) + i32_store8()
    b += i32_const(SIGN_ADDR) + i32_const(1) + call_fn(hidx["out_append"])
    b += END
    b += local_get(3) + i32_const(1) + b"\x6b" + local_set(4)
    b += BLOCK + EMPTY + LOOP + EMPTY
    b += local_get(4) + i32_const(0) + b"\x48" + BR_IF + uleb(1)  # k < 0 (signed)
    b += i32_const(SCRATCH) + local_get(4) + b"\x6a" + i32_const(1)
    b += call_fn(hidx["out_append"])
    b += local_get(4) + i32_const(1) + b"\x6b" + local_set(4)
    b += BR + uleb(0) + END + END
    out.append(code([I64], [], [I64, I32, I32, I32], bytes(b)))

    # arr_push variants: (handle, value). Locals: data, len, cap, newcap, newdata.
    def arr_push(value_type, esize, store_op):
        bb = bytearray()
        bb += local_get(0) + i32_load() + local_set(2)
        bb += local_get(2) + i32_load() + local_set(3)
        bb += local_get(2) + i32_const(4) + b"\x6a" + i32_load() + local_set(4)
        bb += local_get(3) + local_get(4) + b"\x49"  # len < cap (unsigned)
        bb += IF + EMPTY
        # In place: data + 8 + len*esize = value; len += 1.
        bb += local_get(2) + i32_const(8) + b"\x6a"
        bb += local_get(3) + i32_const(esize) + b"\x6c" + b"\x6a"
        bb += local_get(1) + store_op
        bb += local_get(2) + local_get(3) + i32_const(1) + b"\x6a" + i32_store()
        bb += ELSE
        # Grow: newcap = cap == 0 ? 4 : cap * 2.
        bb += local_get(4) + b"\x45"  # i32.eqz
        bb += IF + I32_T + i32_const(4) + ELSE
        bb += local_get(4) + i32_const(2) + b"\x6a" + END + local_set(5)
        bb += i32_const(8) + local_get(5) + i32_const(esize) + b"\x6c" + b"\x6a"
        bb += call_fn(hidx["alloc"]) + local_set(6)
        bb += local_get(6) + local_get(3) + i32_const(1) + b"\x6a" + i32_store()
        bb += local_get(6) + i32_const(4) + b"\x6a" + local_get(5) + i32_store()
        bb += local_get(6) + i32_const(8) + b"\x6a"
        bb += local_get(2) + i32_const(8) + b"\x6a"
        bb += local_get(3) + i32_const(esize) + b"\x6c" + call_fn(hidx["memcpy"])
        bb += local_get(6) + i32_const(8) + b"\x6a"
        bb += local_get(3) + i32_const(esize) + b"\x6c" + b"\x6a"
        bb += local_get(1) + store_op
        bb += local_get(0) + local_get(6) + i32_store()
        bb += END
        return bb

    out.append(code([I32, I64], [], [I32, I32, I32, I32, I32],
                    bytes(arr_push(I64, 8, i64_store()))))
    out.append(code([I32, F64], [], [I32, I32, I32, I32, I32],
                    bytes(arr_push(F64, 8, f64_store()))))
    out.append(code([I32, I32], [], [I32, I32, I32, I32, I32],
                    bytes(arr_push(I32, 4, i32_store()))))
    return out


def code_entry(locals_list, body):
    """Wrap a function body (without trailing end) into a code section entry."""
    runs = []
    for t in locals_list:
        if runs and runs[-1][1] == t:
            runs[-1][0] += 1
        else:
            runs.append([1, t])
    locals_vec = vec([uleb(c) + bytes([t]) for c, t in runs])
    full = locals_vec + body + b"\x0b"
    return uleb(len(full)) + full


def collect_literals(node, ordered):
    """Collect StrLit values in first-encounter order (generic walk)."""
    if isinstance(node, A.StrLit):
        if node.value not in ordered:
            ordered.append(node.value)
        return
    if isinstance(node, list):
        for x in node:
            collect_literals(x, ordered)
        return
    if hasattr(node, "__dict__"):
        for v in vars(node).values():
            if isinstance(v, (str, int, float, bool)) or v is None:
                continue
            collect_literals(v, ordered)


class WasmGen:
    def __init__(self, program, types):
        self.program = program
        self.types = types
        self.funcs = [f for f in program.funcs if not getattr(f, "type_params", None)]
        self.func_index = {f.name: i for i, f in enumerate(self.funcs)}
        self.func_ret = {f.name: f.ret for f in self.funcs}
        self.helper_index = {n: len(self.funcs) + i for i, n in enumerate(HELPER_NAMES)}
        self.scopes = []
        self.tscopes = []
        self.locals = []  # [(valtype)] for locals after params
        self.local_count = 0
        # Static string table, filled by the pre-pass in gen().
        self.lit_addr = {}
        self.heap_base = STATIC_BASE
        # Structured-label depth tracking for `break`: every if/block/
        # loop opcode is a label, so a break must branch to the loop's
        # enclosing block at its absolute depth.
        self.wasm_label_depth = 0
        self.wasm_loop_exits = []

    def expr_type(self, expr):
        return self.types.get(id(expr), "int")

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise ForgeError(f"wasm: undefined variable '{name}'")

    def lookup_type(self, name):
        for scope in reversed(self.tscopes):
            if name in scope:
                return scope[name]
        raise ForgeError(f"wasm: undefined variable '{name}'")

    def new_local(self, t):
        idx = self.local_count
        self.local_count += 1
        self.locals.append(t)
        return idx

    def gen(self):
        # Unions need the tagged tag+payload representation, which
        # the WASM backend does not have in v1.
        from .unions import find_unions
        unions = find_unions(self.program)
        if unions:
            raise ForgeError(f"wasm: union types are not supported in v1 "
                             f"(found {unions[0]})")
        from .opaques import find_opaques
        opaques = find_opaques(self.program)
        if opaques:
            raise ForgeError(f"wasm: opaque types are not supported in v1 "
                             f"(found {opaques[0]})")
        from .fixedints import find_fixed
        fixed = find_fixed(self.program)
        if fixed:
            raise ForgeError(f"wasm: fixed-width integer types are "
                             f"not supported in v1 (found {fixed[0]})")
        from .sizedarrays import find_sized
        sized = find_sized(self.program)
        if sized:
            raise ForgeError(f"wasm: sized arrays are not supported in v1 "
                             f"(found {sized[0]})")
        from .readonly import find_readonly
        readonly = find_readonly(self.program)
        if readonly:
            raise ForgeError(f"wasm: readonly views are not supported in v1 "
                             f"(found {readonly[0]})")
        from .never import find_never
        never = find_never(self.program)
        if never:
            raise ForgeError(f"wasm: never types are not supported in v1 "
                             f"(found {never[0]})")
        from .tuples import find_tuples
        tuples = find_tuples(self.program)
        if tuples:
            raise ForgeError(f"wasm: tuples are not supported in v1 "
                             f"(found {tuples[0]})")
        from .ranges import find_ranges
        ranges = find_ranges(self.program)
        if ranges:
            raise ForgeError("wasm: ranges are not supported in v1 "
                             "(found range)")
        from .defers import find_defers
        if find_defers(self.program):
            raise ForgeError("wasm: defer is not supported in v1")
        # Validate signatures first, so errors are Forge errors, not bad binaries.
        for fn in self.funcs:
            if not is_wasm_type(fn.ret) and fn.ret != "void":
                raise ForgeError(f"wasm: function '{fn.name}' returns {fn.ret}, not supported in v2")
            for _pn, pt in fn.params:
                if not is_wasm_type(pt):
                    raise ForgeError(f"wasm: parameter of type {pt} in '{fn.name}' is not supported in v2")
        # Pre-pass: static string literals (reserved words first so
        # bool printing never depends on user code).
        ordered = ["true", "false", " "]
        for fn in self.funcs:
            collect_literals(fn.body, ordered)
        addr = STATIC_BASE
        for s in ordered:
            self.lit_addr[s] = addr
            addr += 4 + len(s.encode())
            addr = (addr + 7) & ~7
        self.heap_base = addr
        # User code first (it may reference helper indices, which are fixed).
        code_bodies = []
        for fn in self.funcs:
            code_bodies.append(self.gen_func(fn))
        helpers = build_helpers(self.helper_index)
        for params, results, locals_, body in helpers:
            code_bodies.append(code_entry(locals_, body))
        # Type section: user function types + helper types, deduped.
        type_entries = []
        type_index = {}

        def type_key(params, results):
            return (tuple(params), tuple(results))

        def add_type(params, results):
            key = type_key(params, results)
            if key not in type_index:
                type_index[key] = len(type_entries)
                type_entries.append(b"\x60" + vec([bytes([t]) for t in params])
                                    + vec([bytes([t]) for t in results]))
            return type_index[key]

        user_type_idx = []
        for fn in self.funcs:
            user_type_idx.append(add_type(
                [valtype(pt) for _pn, pt in fn.params],
                [valtype(fn.ret)] if fn.ret != "void" else []))
        helper_type_idx = []
        for params, results, _locals, _body in helpers:
            helper_type_idx.append(add_type(params, results))
        type_sec = section(1, vec(type_entries))
        func_sec = section(3, vec([uleb(i) for i in user_type_idx + helper_type_idx]))
        mem_sec = section(5, vec([b"\x00" + uleb(1)]))
        global_sec = section(6, vec([bytes([I32, 0x01]) + i32_const(self.heap_base) + b"\x0b"]))
        export_entries = []
        for i, fn in enumerate(self.funcs):
            export_entries.append(name(fn.name) + b"\x00" + uleb(i))
        export_entries.append(name("memory") + b"\x02" + uleb(0))
        export_sec = section(7, vec(export_entries))
        code_sec = section(10, vec(code_bodies))
        data_entries = []
        for s in ordered:
            blob = len(s.encode()).to_bytes(4, "little") + s.encode()
            data_entries.append(b"\x00" + i32_const(self.lit_addr[s]) + b"\x0b"
                                + uleb(len(blob)) + blob)
        data_sec = section(11, vec(data_entries))
        return (b"\x00asm\x01\x00\x00\x00" + type_sec + func_sec + mem_sec
                + global_sec + export_sec + code_sec + data_sec)

    def gen_func(self, fn):
        self.scopes = [{pn: i for i, (pn, _pt) in enumerate(fn.params)}]
        self.tscopes = [{pn: pt for pn, pt in fn.params}]
        self.locals = []
        self.local_count = len(fn.params)
        body = bytearray()
        for stmt in fn.body.stmts:
            body += self.gen_stmt(stmt)
        body += b"\x0b"  # end
        runs = []
        for t in self.locals:
            if runs and runs[-1][1] == t:
                runs[-1][0] += 1
            else:
                runs.append([1, t])
        locals_vec = vec([uleb(c) + bytes([t]) for c, t in runs])
        full = locals_vec + bytes(body)
        return uleb(len(full)) + full

    def gen_block(self, block):
        self.scopes.append({})
        self.tscopes.append({})
        out = bytearray()
        for stmt in block.stmts:
            out += self.gen_stmt(stmt)
        self.scopes.pop()
        self.tscopes.pop()
        return bytes(out)

    def gen_print(self, expr, newline):
        """Code for print/println: one space between args, newline iff asked."""
        out = bytearray()
        for i, arg in enumerate(expr.args):
            if i > 0:
                out += call_fn(self.helper_index["out_space"])
            t = self.expr_type(arg)
            if t == "str":
                out += self.gen_expr(arg) + call_fn(self.helper_index["out_str"])
            elif t == "int":
                out += self.gen_expr(arg) + call_fn(self.helper_index["out_i64"])
            elif t == "bool":
                # bool prints as the static "true"/"false" literal.
                out += self.gen_expr(arg) + IF + I32_T
                out += i32_const(self.lit_addr["true"]) + ELSE
                out += i32_const(self.lit_addr["false"]) + END
                out += call_fn(self.helper_index["out_str"])
            else:
                raise ForgeError(f"wasm: print of {t} is not supported (str, int, bool only)")
        if newline:
            out += call_fn(self.helper_index["out_nl"])
        return bytes(out)

    def gen_stmt(self, stmt):
        if isinstance(stmt, A.Let):
            code = self.gen_expr(stmt.expr)
            t = stmt.ann or self.expr_type(stmt.expr)
            if not is_wasm_type(t):
                raise ForgeError(f"wasm: let of type {t} is not supported in v2")
            idx = self.local_count
            self.local_count += 1
            self.locals.append(valtype(t))
            self.scopes[-1][stmt.name] = idx
            self.tscopes[-1][stmt.name] = t
            return code + b"\x21" + uleb(idx)  # local.set
        if isinstance(stmt, A.Assign):
            idx = self.lookup(stmt.name)
            return self.gen_expr(stmt.expr) + b"\x21" + uleb(idx)
        if isinstance(stmt, A.IndexAssign):
            # base is an Index node whose base is a Var.
            base_node = stmt.base.base
            if not isinstance(base_node, A.Var):
                raise ForgeError("wasm: index assignment to a non-variable is not supported")
            handle = self.lookup(base_node.name)
            btype = self.lookup_type(base_node.name)
            if not (btype.startswith("[") and btype.endswith("]")):
                raise ForgeError(f"wasm: index assignment to non-array {btype}")
            esize = elem_size(btype[1:-1])
            etype = btype[1:-1]
            h = self.new_local(I32)
            d = self.new_local(I32)
            ix = self.new_local(I32)
            out = bytearray()
            out += local_get(handle) + local_set(h)
            out += local_get(h) + i32_load() + local_set(d)
            out += self.gen_expr(stmt.base.index) + b"\xa7" + local_set(ix)  # i32.wrap_i64
            # Bounds check: ix >= len (unsigned) traps.
            out += local_get(ix) + local_get(d) + i32_load() + b"\x4f"  # i32.ge_u
            out += IF + EMPTY + UNREACHABLE + END
            out += local_get(d) + i32_const(8) + b"\x6a"
            out += local_get(ix) + i32_const(esize) + b"\x6c" + b"\x6a"
            out += self.gen_expr(stmt.expr)
            if etype == "int":
                out += i64_store()
            elif etype == "float":
                out += f64_store()
            else:
                out += i32_store()
            return bytes(out)
        if isinstance(stmt, A.Return):
            if stmt.expr is None:
                return b"\x0f"
            return self.gen_expr(stmt.expr) + b"\x0f"
        if isinstance(stmt, A.If):
            cond = self.gen_expr(stmt.cond)
            out = cond + b"\x04\x40"  # if, empty blocktype
            self.wasm_label_depth += 1
            out += self.gen_block(stmt.then)
            if stmt.els is not None:
                out += b"\x05" + self.gen_block(stmt.els)
            out += b"\x0b"
            self.wasm_label_depth -= 1
            return out
        if isinstance(stmt, A.Break):
            if not self.wasm_loop_exits:
                raise ForgeError("wasm: break outside a loop", stmt.line, stmt.col)
            rel = self.wasm_label_depth - self.wasm_loop_exits[-1]
            return b"\x0c" + uleb(rel)  # br to the loop's enclosing block
        if isinstance(stmt, A.Continue):
            if not self.wasm_loop_exits:
                raise ForgeError("wasm: continue outside a loop", stmt.line, stmt.col)
            # The loop itself sits one label inside its enclosing
            # block, so branching to it re-runs the condition check
            # at the loop head (the check lives inside the loop).
            rel = self.wasm_label_depth - (self.wasm_loop_exits[-1] + 1)
            return b"\x0c" + uleb(rel)  # br to the loop head
        if isinstance(stmt, A.While):
            # block { loop { if !cond br 1; body; br 0 } }
            out = b"\x02\x40\x03\x40"
            self.wasm_loop_exits.append(self.wasm_label_depth + 1)  # the block
            self.wasm_label_depth += 2
            out += self.gen_expr(stmt.cond)
            out += b"\x45\x0d\x01"  # i32.eqz, br_if 1 (exit block)
            out += self.gen_block(stmt.body)
            out += b"\x0c\x00\x0b\x0b"  # br 0, end loop, end block
            self.wasm_label_depth -= 2
            self.wasm_loop_exits.pop()
            return out
        if isinstance(stmt, A.Block):
            return self.gen_block(stmt)
        if isinstance(stmt, A.Scope):
            # No threads on WASM: a scope without spawn runs as its
            # block, and a spawn inside still fails as before.
            return self.gen_block(stmt.body)
        if isinstance(stmt, A.ExprStmt):
            e = stmt.expr
            if isinstance(e, A.Call):
                if e.name in ("print", "println"):
                    return self.gen_print(e, e.name == "println")
                if e.name == "push":
                    arg0 = e.args[0]
                    if not isinstance(arg0, A.Var):
                        raise ForgeError("wasm: push to a non-variable is not supported")
                    handle = self.lookup(arg0.name)
                    btype = self.lookup_type(arg0.name)
                    if not (btype.startswith("[") and btype.endswith("]")):
                        raise ForgeError(f"wasm: push to non-array {btype}")
                    etype = btype[1:-1]
                    helper = {"int": "arr_push_i64", "float": "arr_push_f64",
                              "bool": "arr_push_i32", "str": "arr_push_i32"}[etype]
                    return (local_get(handle) + self.gen_expr(e.args[1])
                            + call_fn(self.helper_index[helper]))
                if e.name == "fail":
                    return (self.gen_expr(e.args[0])
                            + call_fn(self.helper_index["out_str"]) + UNREACHABLE)
                if e.name == "assert":
                    out = bytearray()
                    out += self.gen_expr(e.args[0]) + b"\x45"  # i32.eqz
                    out += IF + EMPTY
                    out += self.gen_expr(e.args[1])
                    out += call_fn(self.helper_index["out_str"]) + UNREACHABLE
                    out += END
                    return bytes(out)
            code = self.gen_expr(e)
            # Drop a non-void call result.
            if isinstance(e, A.Call) and self.func_ret.get(e.name, "void") != "void":
                code += b"\x1a"
            if isinstance(e, A.Call) and e.name == "len":
                code += b"\x1a"
            return code
        raise ForgeError(f"wasm: statement {type(stmt).__name__} is not supported in v1")

    def gen_expr(self, expr):
        if isinstance(expr, A.MethodCall):
            raise ForgeError("wasm: trait method calls are not supported "
                             "in v1", expr.line, expr.col)
        if isinstance(expr, A.IntLit):
            return b"\x42" + sleb(int(expr.value))
        if isinstance(expr, A.FloatLit):
            import struct as _struct
            return b"\x44" + _struct.pack("<d", float(expr.value))
        if isinstance(expr, A.StrLit):
            return i32_const(self.lit_addr[expr.value])
        if isinstance(expr, A.BoolLit):
            return b"\x41" + sleb(1 if expr.value else 0)
        if isinstance(expr, A.Var):
            return b"\x20" + uleb(self.lookup(expr.name))
        if isinstance(expr, A.ArrayLit):
            t = self.expr_type(expr)
            if not (t.startswith("[") and t.endswith("]")):
                raise ForgeError(f"wasm: array literal of type {t} is not supported")
            etype = t[1:-1]
            if etype not in ("int", "float", "bool", "str"):
                raise ForgeError(f"wasm: array element type {etype} is not supported")
            esize = elem_size(etype)
            n = len(expr.elems)
            h = self.new_local(I32)
            d = self.new_local(I32)
            out = bytearray()
            out += i32_const(4) + call_fn(self.helper_index["alloc"]) + local_set(h)
            out += i32_const(8 + n * esize) + call_fn(self.helper_index["alloc"]) + local_set(d)
            out += local_get(h) + local_get(d) + i32_store()
            out += local_get(d) + i32_const(n) + i32_store()
            out += local_get(d) + i32_const(4) + b"\x6a" + i32_const(n) + i32_store()
            for i, e in enumerate(expr.elems):
                out += local_get(d) + i32_const(8 + i * esize) + b"\x6a"
                out += self.gen_expr(e)
                if etype == "int":
                    out += i64_store()
                elif etype == "float":
                    out += f64_store()
                else:
                    out += i32_store()
            out += local_get(h)
            return bytes(out)
        if isinstance(expr, A.Index):
            btype = self.expr_type(expr.base)
            if btype == "str":
                # str value = pointer to [len:i32][bytes...]. Indexing
                # returns a fresh 1-char string: alloc 5 bytes, store
                # len 1, copy the byte. Bounds check traps like arrays.
                p = self.new_local(I32)
                ix = self.new_local(I32)
                outp = self.new_local(I32)
                out = bytearray()
                out += self.gen_expr(expr.base) + local_set(p)
                out += self.gen_expr(expr.index) + b"\xa7" + local_set(ix)  # i32.wrap_i64
                out += local_get(ix) + local_get(p) + i32_load() + b"\x4f"  # i32.ge_u
                out += IF + EMPTY + UNREACHABLE + END
                out += i32_const(5) + call_fn(self.helper_index["alloc"]) + local_set(outp)
                out += local_get(outp) + i32_const(1) + i32_store()
                out += local_get(outp) + i32_const(4) + b"\x6a"
                out += local_get(p) + i32_const(4) + b"\x6a" + local_get(ix) + b"\x6a"
                out += i32_load8_u() + i32_store8()
                out += local_get(outp)
                return bytes(out)
            if not (btype.startswith("[") and btype.endswith("]")):
                raise ForgeError(f"wasm: indexing non-array {btype}")
            etype = btype[1:-1]
            if etype not in ("int", "float", "bool", "str"):
                raise ForgeError(f"wasm: array element type {etype} is not supported")
            esize = elem_size(etype)
            h = self.new_local(I32)
            d = self.new_local(I32)
            ix = self.new_local(I32)
            out = bytearray()
            out += self.gen_expr(expr.base) + local_set(h)
            out += local_get(h) + i32_load() + local_set(d)
            out += self.gen_expr(expr.index) + b"\xa7" + local_set(ix)  # i32.wrap_i64
            out += local_get(ix) + local_get(d) + i32_load() + b"\x4f"  # i32.ge_u
            out += IF + EMPTY + UNREACHABLE + END
            out += local_get(d) + i32_const(8) + b"\x6a"
            out += local_get(ix) + i32_const(esize) + b"\x6c" + b"\x6a"
            if etype == "int":
                out += i64_load()
            elif etype == "float":
                out += f64_load()
            else:
                out += i32_load()
            return bytes(out)
        if isinstance(expr, A.UnaryOp):
            inner = self.gen_expr(expr.expr)
            if expr.op == "-":
                if self.expr_type(expr.expr) == "float":
                    return inner + b"\x9a"  # f64.neg
                # WASM has no integer neg: 0 - x.
                return b"\x42\x00" + inner + b"\x7d"  # i64.const 0, x, i64.sub
            if expr.op == "!":
                return inner + b"\x45"  # i32.eqz
            if expr.op == "~":
                # WASM has no bitwise not: x xor -1.
                return inner + b"\x42\x7f" + b"\x85"  # i64.const -1, i64.xor
            raise ForgeError(f"wasm: unary {expr.op} is not supported in v1")
        if isinstance(expr, A.BinOp):
            lt = self.expr_type(expr.left)
            if lt == "str":
                left = self.gen_expr(expr.left)
                right = self.gen_expr(expr.right)
                if expr.op == "+":
                    return left + right + call_fn(self.helper_index["str_concat"])
                if expr.op == "==":
                    return left + right + call_fn(self.helper_index["str_eq"])
                if expr.op == "!=":
                    return (left + right + call_fn(self.helper_index["str_eq"])
                            + b"\x45")  # i32.eqz
                raise ForgeError(f"wasm: operator {expr.op} on str is not supported")
            if lt.startswith("["):
                raise ForgeError(f"wasm: binary op on arrays is not supported")
            left = self.gen_expr(expr.left)
            right = self.gen_expr(expr.right)
            if lt == "int":
                ops = {"+": 0x7C, "-": 0x7D, "*": 0x7E, "/": 0x7F, "%": 0x81,
                       "==": 0x51, "!=": 0x52, "<": 0x53, ">": 0x55, "<=": 0x57, ">=": 0x59,
                       "&": 0x83, "|": 0x84, "^": 0x85, "<<": 0x86, ">>": 0x87}
            elif lt == "float":
                ops = {"+": 0xA0, "-": 0xA1, "*": 0xA2, "/": 0xA3,
                       "==": 0x61, "!=": 0x62, "<": 0x63, ">": 0x64, "<=": 0x65, ">=": 0x66}
            elif lt == "bool":
                ops = {"&&": 0x71, "||": 0x72, "==": 0x46, "!=": 0x47}
            else:
                raise ForgeError(f"wasm: binary op on {lt} is not supported in v1")
            if expr.op not in ops:
                raise ForgeError(f"wasm: operator {expr.op} on {lt} is not supported in v2")
            return left + right + bytes([ops[expr.op]])
        if isinstance(expr, A.Cast):
            inner = self.gen_expr(expr.expr)
            src = self.expr_type(expr.expr)
            if src == "int" and expr.target == "float":
                return inner + b"\xb9"  # f64.convert_i64_s
            if src == "float" and expr.target == "int":
                return inner + b"\xb0"  # i64.trunc_f64_s
            raise ForgeError(f"wasm: cast {src} -> {expr.target} is not supported in v2")
        if isinstance(expr, A.Call):
            if expr.name == "len":
                t = self.expr_type(expr.args[0])
                if t == "str":
                    return self.gen_expr(expr.args[0]) + i32_load() + b"\xad"  # extend_u
                if t.startswith("[") and t.endswith("]"):
                    return (self.gen_expr(expr.args[0]) + i32_load() + i32_load()
                            + b"\xad")
                raise ForgeError(f"wasm: len() of {t} is not supported")
            if expr.name in ("print", "println", "push", "fail", "assert"):
                raise ForgeError(f"wasm: {expr.name}() is statement-only")
            if expr.name in ("peek32", "poke32"):
                raise ForgeError(f"wasm: {expr.name}() needs raw memory addresses, "
                                 f"which WASM does not expose")
            if expr.name in ("csr_read", "csr_write", "csr_set", "csr_clear", "ecall", "ecall3"):
                raise ForgeError(f"wasm: {expr.name}() needs RISC-V CSRs/ecall "
                                 f"(big32 target only)")
            if expr.name in ("wrapping_add", "wrapping_sub", "wrapping_mul"):
                # i64 arithmetic wraps by spec in WASM.
                op = {"wrapping_add": b"\x7c", "wrapping_sub": b"\x7d",
                      "wrapping_mul": b"\x7e"}[expr.name]
                return (self.gen_expr(expr.args[0]) +
                        self.gen_expr(expr.args[1]) + op)
            if expr.name == "wrapping_neg":
                # No i64.neg opcode: 0 - x.
                return (b"\x42\x00" + self.gen_expr(expr.args[0]) + b"\x7d")
            if expr.name not in self.func_index:
                raise ForgeError(f"wasm: call to '{expr.name}' is not supported in v1 "
                                 f"(builtins, structs, and enums are out)")
            out = bytearray()
            for a in expr.args:
                out += self.gen_expr(a)
            out += b"\x10" + uleb(self.func_index[expr.name])
            return bytes(out)
        raise ForgeError(f"wasm: expression {type(expr).__name__} is not supported in v1")


def generate_wasm(program, types):
    return WasmGen(program, types).gen()
