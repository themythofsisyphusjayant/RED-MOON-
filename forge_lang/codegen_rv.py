"""Qasida -> big32 (RV32IMAC) assembly code generator.

Reuses Forge's parser, checker and type inference; only the backend is
new. Target: big32 v7, single-cycle, 16KB IMEM, 64KB DMEM, UART TX
only (store byte to 0x10000000), ECALL halts (mtvec == 0).

Supported subset (v1, everything else raises a clear ForgeError):
  int (32-bit on big32, NOT Forge's 64-bit x86 int), bool,
  str literals / str variables (pointer to null-terminated static data),
  [int]/[bool]/[str] arrays, let/assign, if/else, while, for over an
  array or over range(n), functions/calls (<= 8 args, recursion works),
  return, print/println (int, bool, str), len (array or str),
  assert/fail (print message, halt with a0 = 1).
Floats (0.7.0, soft-float v1): float literals/variables,
  [float] arrays, + - * (IEEE-754 single precision via
  forge_fadd/forge_fmul helpers, round-to-nearest-even),
  == / != (bitwise: -0.0 != +0.0, unlike IEEE).
  Verified: examples/big32_float_demo.fg 12/12 on the
  Python model AND Icarus Verilog, plus a 60-case
  randomized differential test vs Python float32,
  60/60 on both. fadd works in exact 27-bit integer
  arithmetic (significand << 3 with the shifted
  operand's guard/round/sticky folded into the low
  3 bits), so subtraction borrows correctly; the
  carry shift folds the shifted-out bit into the
  sticky position. fmul extracts guard/round/sticky
  from the full dropped field. NOT yet: float
  division, ordered comparisons (<, >, ...), float
  printing, int<->float casts, subnormal results
  (flushed to signed zero) and subnormal inputs
  (treated as normals — do not rely on them),
  NaN/Inf inputs. Each gap raises a clear ForgeError
  instead of silently miscompiling.
Structs (0.7.0): local struct variables as consecutive
  frame slots (int/bool/str fields), field reads/writes,
  struct copies. Struct function params/returns are
  still rejected (one register cannot carry a struct).
NOT supported: enums, match, spawn, extern/FFI, file
I/O, args(), http, clock, string concatenation/comparison, push,
dynamic allocation. Arithmetic is native RISC-V (wrapping, div by
zero -> -1, rem by zero -> dividend) -- NOT Forge safe-mode aborts.

Calling convention (documented, see README "Forge on big32"):
  args a0-a7, return a0, frame pointer s0, locals in a fixed 2048-byte
  frame addressed via s0 (so sp may move for call spills). Callee
  saves ra + s0 only; caller spills every live temp register across
  a call (so t/a/s temps are effectively caller-saved). Stack starts
  at 65532 and grows down; static data lives at 0x1000 and up.
  Arrays: static slot per source site, first word = length, then
  elements (so an array literal inside a loop re-initialises the same
  slot each iteration -- a documented v1 limitation). Strings:
  null-terminated static data, initialised by _start before main.
"""

import struct

from .errors import ForgeError
from . import ast_nodes as A

UART = 0x10000000
STATIC_BASE = 0x1000
FRAME_BYTES = 2048
SP_START = 65532
# Temp pool: t0-t6, a1-a7 (a0 is return/arg0, never a temp), s2-s11.
# Caller spills live temps across calls, so all of these are safe.
# Expression temps. NOTE: argument registers a0-a7 are deliberately
# NOT in this list. They used to be, and that was unsound: when an
# argument expression was evaluated into, say, a1, the call's
# argument-staging loop then overwrote a1 with another argument
# before copying it to its target register — so fs_write(1, 3, 44)
# stored 3 (the index) instead of 44 (the value), found 27 Oct
# 2026 via the filesystem kernel's readback check. With a-regs
# excluded, argument temps can never collide with staging.
TEMPS = ["t0", "t1", "t2", "t3", "t4", "t5", "t6",
         "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11"]


class RVGen:
    def __init__(self, program, types, stack_top=SP_START):
        self.program = program
        self.types = types
        self.stack_top = stack_top
        self.lines = []
        self.init_lines = []          # _start static-string initialisation
        self.label_n = 0
        self.loop_ends = []
        self.loop_conts = []
        self.free = list(TEMPS)
        self.live = []                # temps currently holding values
        self.funcs = {fn.name: fn for fn in program.funcs}
        self.env = []                 # stack of {name: (slot, type)}
        self.slot_n = 0               # locals allocated in current fn
        self.epilogue = None
        self.cur_fn = None
        self.str_slots = {}           # string value -> DMEM address
        self.arr_slots = []           # (slot id, address) in allocation order
        self.next_static = STATIC_BASE
        self.true_addr = None
        self.false_addr = None

    # ---------- utilities ----------
    def label(self, prefix):
        self.label_n += 1
        return f"{prefix}_{self.label_n}"

    def emit(self, text=""):
        self.lines.append(text)

    def alloc(self):
        if not self.free:
            raise ForgeError("expression too deep for big32 backend "
                             "(temp registers exhausted)")
        r = self.free.pop(0)
        self.live.append(r)
        return r

    def free_reg(self, r):
        if r in self.live:
            self.live.remove(r)
        if r not in self.free:
            self.free.append(r)

    def alloc_slot(self):
        self.slot_n += 1
        if self.slot_n * 4 > FRAME_BYTES:
            raise ForgeError("too many locals for big32 backend frame")
        return self.slot_n

    def slot_off(self, slot):
        return -4 * slot

    def lookup(self, name):
        for scope in reversed(self.env):
            if name in scope:
                return scope[name]
        raise ForgeError(f"unknown variable {name}")

    def expr_type(self, expr):
        return self.types.get(id(expr), "int")

    def static_addr(self, size):
        addr = self.next_static
        # Align to 4, reserve size bytes.
        self.next_static = (addr + size + 3) & ~3
        if self.next_static > 0x8000:
            raise ForgeError("static data exhausted on big32")
        return addr

    def str_addr(self, value):
        if value in self.str_slots:
            return self.str_slots[value]
        addr = self.static_addr(len(value.encode("utf-8")) + 1)
        self.str_slots[value] = addr
        # Initialisation emitted into _start (uses t0/t1, no live temps).
        self.init_lines.append(f"    li t0, {addr}")
        for b in value.encode("utf-8"):
            self.init_lines.append(f"    li t1, {b}")
            self.init_lines.append("    sb t1, 0(t0)")
            self.init_lines.append("    addi t0, t0, 1")
        self.init_lines.append("    sb zero, 0(t0)")
        return addr

    # ---------- top level ----------
    def generate(self):
        # Unions need the tagged tag+payload representation, which
        # the big32 backend does not have in v1: reject loudly
        # rather than miscompiling a multi-word value into one slot.
        from .unions import find_unions
        unions = find_unions(self.program)
        if unions:
            raise ForgeError(f"big32: union types are not supported in v1 "
                             f"(found {unions[0]})")
        from .opaques import find_opaques
        opaques = find_opaques(self.program)
        if opaques:
            raise ForgeError(f"big32: opaque types are not supported in v1 "
                             f"(found {opaques[0]})")
        from .fixedints import find_fixed
        fixed = find_fixed(self.program)
        if fixed:
            raise ForgeError(f"big32: fixed-width integer types are "
                             f"not supported in v1 (found {fixed[0]})")
        from .sizedarrays import find_sized
        sized = find_sized(self.program)
        if sized:
            raise ForgeError(f"big32: sized arrays are not supported in v1 "
                             f"(found {sized[0]})")
        from .readonly import find_readonly
        readonly = find_readonly(self.program)
        if readonly:
            raise ForgeError(f"big32: readonly views are not supported in v1 "
                             f"(found {readonly[0]})")
        from .never import find_never
        never = find_never(self.program)
        if never:
            raise ForgeError(f"big32: never types are not supported in v1 "
                             f"(found {never[0]})")
        from .tuples import find_tuples
        tuples = find_tuples(self.program)
        if tuples:
            raise ForgeError(f"big32: tuples are not supported in v1 "
                             f"(found {tuples[0]})")
        from .ranges import find_ranges
        ranges = find_ranges(self.program)
        if ranges:
            raise ForgeError("big32: ranges are not supported in v1 "
                             "(found range)")
        from .defers import find_defers
        if find_defers(self.program):
            raise ForgeError("big32: defer is not supported in v1")
        from .moves import uses_move
        if uses_move(self.program):
            raise ForgeError("big32: move is not supported")
        from .pins import uses_pin
        if uses_pin(self.program):
            raise ForgeError("big32: pin is not supported")
        from .allocfail import uses_try_alloc
        if uses_try_alloc(self.program):
            raise ForgeError("big32: try_alloc is not supported")
        from .mmaps import uses_mmap
        if uses_mmap(self.program):
            raise ForgeError("big32: mmap is not supported in v1")
        from .drops import uses_drop
        if uses_drop(self.program):
            raise ForgeError("big32: drop is not supported in v1")
        # Structs (0.7.0): a struct variable is consecutive
        # frame slots, one per field, in declaration
        # order. Fields must be scalar (int/bool/str);
        # struct-typed function params/returns are still
        # rejected (one register cannot carry a struct).
        self.struct_layout = {}
        for sd in (getattr(self.program, "structs", None) or []):
            if getattr(sd, "type_params", None):
                continue
            fields = []
            for fname, ftype in sd.fields:
                if ftype not in ("int", "bool", "str"):
                    raise ForgeError(
                        f"big32 structs support int/bool/str fields only, "
                        f"not {ftype} in struct {sd.name} (v1)")
                fields.append((fname, ftype))
            self.struct_layout[sd.name] = fields
        if self.program.enums:
            raise ForgeError("enums are not supported on big32 (v1)")
        if "main" not in self.funcs:
            raise ForgeError("big32 target needs a main function")
        # Trap-handler hook: a function named trap_handler, if present,
        # is wired to mtvec by _start and called by the trap entry
        # stub on every trap. It takes no arguments, or one int: the
        # trap-frame pointer (sp just after the stub saved the 30
        # registers). A no-arg handler ignores the register; the stub
        # always passes it, so old handlers keep working. The handler
        # reads mcause/mepc itself via csr_read, and returns nothing.
        self.has_trap_handler = "trap_handler" in self.funcs
        if self.has_trap_handler:
            th = self.funcs["trap_handler"]
            one_int = (len(th.params) == 1 and th.params[0][1] == "int")
            if (th.params and not one_int) or th.ret != "void":
                raise ForgeError("trap_handler() must take no arguments "
                                 "or one int (trap frame pointer) "
                                 "and return nothing",
                                 th.line, th.col)
        for fn in self.program.funcs:
            if getattr(fn, "is_extern", False):
                raise ForgeError("extern functions are not supported on big32")
            for _n, t in fn.params:
                if t in self.struct_layout:
                    raise ForgeError(
                        "struct function parameters are not supported on big32 (v1)")
            if fn.ret in self.struct_layout:
                raise ForgeError(
                    "struct function returns are not supported on big32 (v1)")
        # Emit functions first so string/array slots are discovered;
        # _start (with string init) is prepended at the end.
        body = []
        for fn in self.program.funcs:
            self.gen_func(fn)
        body = self.lines
        self.lines = []
        # _start: stack, static strings, trap vector, call main, halt.
        self.emit("_start:")
        self.emit(f"    li sp, {self.stack_top}")
        self.lines.extend(self.init_lines)
        if self.has_trap_handler:
            self.emit("    la t0, forge_trap_entry")
            self.emit("    csrw 773, t0")
        self.emit("    jal ra, main")
        self.emit_halt()
        self.lines.extend(body)
        self.lines.extend(self.helpers())
        return "\n".join(self.lines) + "\n"

    def emit_halt(self):
        # Halt: with a trap handler wired, a bare ecall would trap
        # instead of halting (and the handler would return past it
        # into whatever follows). So clear mtvec first, then ecall.
        if self.has_trap_handler:
            self.emit("    csrw 773, zero")
        self.emit("    ecall")

    def helpers(self):
        # Note: true/false strings are allocated during gen_func (bool
        # printing), i.e. before _start is emitted, so their init code
        # is already in _start. Helpers must not allocate new strings
        # here (their init would never be emitted).
        h = []
        h.append("forge_print_str:")
        h.append("    addi sp, sp, -4")
        h.append("    sw ra, 0(sp)")
        h.append("forge_print_str_loop:")
        h.append("    lb t0, 0(a0)")
        h.append("    beq t0, zero, forge_print_str_done")
        h.append(f"    li t1, {UART}")
        h.append("    sb t0, 0(t1)")
        h.append("    addi a0, a0, 1")
        h.append("    j forge_print_str_loop")
        h.append("forge_print_str_done:")
        h.append("    lw ra, 0(sp)")
        h.append("    addi sp, sp, 4")
        h.append("    ret")
        h.append("forge_print_int:")
        h.append("    addi sp, sp, -4")
        h.append("    sw ra, 0(sp)")
        # INT_MIN: signed negation wraps, so print '-' then extract
        # digits unsigned (divu/remu) from the bit pattern 0x80000000.
        h.append("    li t0, -2147483648")
        h.append("    bne a0, t0, forge_print_int_sign")
        h.append(f"    li t0, {UART}")
        h.append("    li t1, 45")
        h.append("    sb t1, 0(t0)")
        h.append("    li a0, -2147483648")
        h.append("    j forge_print_int_push_u")
        h.append("forge_print_int_sign:")
        h.append("    blt a0, zero, forge_print_int_neg")
        h.append("    j forge_print_int_digits")
        h.append("forge_print_int_neg:")
        h.append(f"    li t0, {UART}")
        h.append("    li t1, 45")
        h.append("    sb t1, 0(t0)")
        h.append("    sub a0, zero, a0")
        h.append("forge_print_int_digits:")
        h.append("    beq a0, zero, forge_print_int_zero")
        h.append("    mv t3, sp")
        h.append("    li t2, 10")
        h.append("forge_print_int_push:")
        h.append("    beq a0, zero, forge_print_int_pop")
        h.append("    rem t0, a0, t2")
        h.append("    addi t0, t0, 48")
        h.append("    addi sp, sp, -4")
        h.append("    sw t0, 0(sp)")
        h.append("    div a0, a0, t2")
        h.append("    j forge_print_int_push")
        h.append("forge_print_int_push_u:")
        h.append("    mv t3, sp")
        h.append("    li t2, 10")
        h.append("forge_print_int_push_u_loop:")
        h.append("    beq a0, zero, forge_print_int_pop")
        h.append("    remu t0, a0, t2")
        h.append("    addi t0, t0, 48")
        h.append("    addi sp, sp, -4")
        h.append("    sw t0, 0(sp)")
        h.append("    divu a0, a0, t2")
        h.append("    j forge_print_int_push_u_loop")
        h.append("forge_print_int_pop:")
        h.append("    beq sp, t3, forge_print_int_done")
        h.append("    lw t0, 0(sp)")
        h.append("    addi sp, sp, 4")
        h.append(f"    li t1, {UART}")
        h.append("    sb t0, 0(t1)")
        h.append("    j forge_print_int_pop")
        h.append("forge_print_int_zero:")
        h.append(f"    li t0, {UART}")
        h.append("    li t1, 48")
        h.append("    sb t1, 0(t0)")
        h.append("forge_print_int_done:")
        h.append("    lw ra, 0(sp)")
        h.append("    addi sp, sp, 4")
        h.append("    ret")
        h.append("forge_strlen:")
        h.append("    li t0, 0")
        h.append("forge_strlen_loop:")
        h.append("    lb t1, 0(a0)")
        h.append("    beq t1, zero, forge_strlen_done")
        h.append("    addi a0, a0, 1")
        h.append("    addi t0, t0, 1")
        h.append("    j forge_strlen_loop")
        h.append("forge_strlen_done:")
        h.append("    mv a0, t0")
        h.append("    ret")
        # ---- soft-float v1 (0.7.0) ----
        # IEEE-754 single precision in integer registers.
        # Callers spill live temps first (see gen_binop),
        # so helpers may use any t/s register except s0
        # (frame pointer), sp and ra. Subnormal inputs
        # are treated as normals (wrong, documented);
        # NaN/Inf inputs are not handled.
        h.append("forge_fsub:")
        h.append("    li t0, -2147483648")
        h.append("    xor a1, a1, t0")
        h.append("    j forge_fadd")
        h.append("forge_fadd:")
        h.append("    srli t0, a0, 31")
        h.append("    slli t0, t0, 31")
        h.append("    srli t1, a1, 31")
        h.append("    slli t1, t1, 31")
        h.append("    srli t2, a0, 23")
        h.append("    andi t2, t2, 255")
        h.append("    srli t3, a1, 23")
        h.append("    andi t3, t3, 255")
        h.append("    li t6, 8388607")
        h.append("    and t4, a0, t6")
        h.append("    and t5, a1, t6")
        h.append("    or t6, t2, t4")
        h.append("    bne t6, zero, fa_anotzero")
        h.append("    or t6, t3, t5")
        h.append("    beq t6, zero, fa_bothzero")
        h.append("    mv a0, a1")
        h.append("    ret")
        h.append("fa_bothzero:")
        h.append("    bne t0, t1, fa_bz_pos")
        h.append("    mv a0, t0")
        h.append("    ret")
        h.append("fa_bz_pos:")
        h.append("    li a0, 0")
        h.append("    ret")
        h.append("fa_anotzero:")
        h.append("    or t6, t3, t5")
        h.append("    bne t6, zero, fa_bnotzero")
        h.append("    ret")
        h.append("fa_bnotzero:")
        h.append("    li t6, 8388608")
        h.append("    or t4, t4, t6")
        h.append("    or t5, t5, t6")
        h.append("    li s5, 0")
        h.append("    li s6, 0")
        h.append("    li s7, 0")
        h.append("    li s11, 0")
        h.append("    bge t2, t3, fa_align_b")
        h.append("    sub s8, t3, t2")
        h.append("    mv s3, t3")
        h.append("    li s11, 1")
        h.append("    j fa_shift_a")
        h.append("fa_align_b:")
        h.append("    sub s8, t2, t3")
        h.append("    mv s3, t2")
        h.append("    li s11, 2")
        h.append("    j fa_shift_b")
        # Shift t4 right by s8, extracting guard (s5),
        # round (s6) and sticky (s7) from dropped bits.
        h.append("fa_shift_a:")
        h.append("    beq s8, zero, fa_addsub")
        h.append("    li t6, 25")
        h.append("    blt s8, t6, fa_shift_a_small")
        h.append("    sltu s7, zero, t4")
        h.append("    li t4, 0")
        h.append("    j fa_addsub")
        h.append("fa_shift_a_small:")
        h.append("    li t6, 1")
        h.append("    sll t6, t6, s8")
        h.append("    addi t6, t6, -1")
        h.append("    and s10, t4, t6")
        h.append("    addi s9, s8, -1")
        h.append("    srl s5, s10, s9")
        h.append("    andi s5, s5, 1")
        h.append("    li s6, 0")
        h.append("    li s9, 2")
        h.append("    blt s8, s9, fa_shift_a_rdone")
        h.append("    addi s9, s8, -2")
        h.append("    srl s6, s10, s9")
        h.append("    andi s6, s6, 1")
        h.append("fa_shift_a_rdone:")
        h.append("    li s7, 0")
        h.append("    li s9, 3")
        h.append("    blt s8, s9, fa_shift_a_sdone")
        h.append("    addi s9, s8, -2")
        h.append("    li t6, 1")
        h.append("    sll t6, t6, s9")
        h.append("    addi t6, t6, -1")
        h.append("    and t6, s10, t6")
        h.append("    sltu s7, zero, t6")
        h.append("fa_shift_a_sdone:")
        h.append("    srl t4, t4, s8")
        h.append("    j fa_addsub")
        h.append("fa_shift_b:")
        h.append("    beq s8, zero, fa_addsub")
        h.append("    li t6, 25")
        h.append("    blt s8, t6, fa_shift_b_small")
        h.append("    sltu s7, zero, t5")
        h.append("    li t5, 0")
        h.append("    j fa_addsub")
        h.append("fa_shift_b_small:")
        h.append("    li t6, 1")
        h.append("    sll t6, t6, s8")
        h.append("    addi t6, t6, -1")
        h.append("    and s10, t5, t6")
        h.append("    addi s9, s8, -1")
        h.append("    srl s5, s10, s9")
        h.append("    andi s5, s5, 1")
        h.append("    li s6, 0")
        h.append("    li s9, 2")
        h.append("    blt s8, s9, fa_shift_b_rdone")
        h.append("    addi s9, s8, -2")
        h.append("    srl s6, s10, s9")
        h.append("    andi s6, s6, 1")
        h.append("fa_shift_b_rdone:")
        h.append("    li s7, 0")
        h.append("    li s9, 3")
        h.append("    blt s8, s9, fa_shift_b_sdone")
        h.append("    addi s9, s8, -2")
        h.append("    li t6, 1")
        h.append("    sll t6, t6, s9")
        h.append("    addi t6, t6, -1")
        h.append("    and t6, s10, t6")
        h.append("    sltu s7, zero, t6")
        h.append("fa_shift_b_sdone:")
        h.append("    srl t5, t5, s8")
        h.append("    j fa_addsub")
        # 27-bit exact arithmetic (fix for the first
        # version's borrow bug): fold the shifted
        # operand's guard/round/sticky into the low 3
        # bits of a 27-bit significand, so add/sub are
        # exact integer ops and rounding reads the
        # low bits directly. The first version kept
        # the fraction separate and forgot that a
        # subtraction BORROWS from it (true value =
        # diff - fraction, not diff + fraction),
        # which made every cancellation case land
        # up to 2 ulps high.
        h.append("fa_addsub:")
        h.append("    slli t4, t4, 3")
        h.append("    slli t5, t5, 3")
        h.append("    beq s11, zero, fa_27_ready")
        h.append("    li t6, 1")
        h.append("    beq s11, t6, fa_27_shift_a")
        h.append("    slli s5, s5, 2")
        h.append("    slli s6, s6, 1")
        h.append("    or t5, t5, s5")
        h.append("    or t5, t5, s6")
        h.append("    or t5, t5, s7")
        h.append("    j fa_27_ready")
        h.append("fa_27_shift_a:")
        h.append("    slli s5, s5, 2")
        h.append("    slli s6, s6, 1")
        h.append("    or t4, t4, s5")
        h.append("    or t4, t4, s6")
        h.append("    or t4, t4, s7")
        h.append("fa_27_ready:")
        h.append("    bne t0, t1, fa_sub")
        h.append("    add s4, t4, t5")
        h.append("    mv s2, t0")
        h.append("    j fa_norm")
        h.append("fa_sub:")
        h.append("    beq t4, t5, fa_sub_zero")
        h.append("    bltu t5, t4, fa_sub_a_bigger")
        h.append("    sub s4, t5, t4")
        h.append("    mv s2, t1")
        h.append("    j fa_norm")
        h.append("fa_sub_a_bigger:")
        h.append("    sub s4, t4, t5")
        h.append("    mv s2, t0")
        h.append("    j fa_norm")
        h.append("fa_sub_zero:")
        h.append("    li a0, 0")
        h.append("    ret")
        h.append("fa_norm:")
        h.append("    li t6, 134217728")
        h.append("    and t6, s4, t6")
        h.append("    beq t6, zero, fa_norm_left")
        # Carry shift: fold the shifted-out bit into
        # the sticky position first, or a carry with
        # fraction bits 1001 would round 1 ulp low.
        h.append("    andi t6, s4, 1")
        h.append("    slli t6, t6, 1")
        h.append("    or s4, s4, t6")
        h.append("    srli s4, s4, 1")
        h.append("    addi s3, s3, 1")
        h.append("    j fa_round")
        h.append("fa_norm_left:")
        h.append("    li t6, 67108864")
        h.append("    and t6, s4, t6")
        h.append("    bne t6, zero, fa_round")
        h.append("    beq s3, zero, fa_flush")
        h.append("    slli s4, s4, 1")
        h.append("    addi s3, s3, -1")
        h.append("    j fa_norm_left")
        h.append("fa_flush:")
        h.append("    mv a0, s2")
        h.append("    ret")
        h.append("fa_round:")
        h.append("    srli s5, s4, 2")
        h.append("    andi s5, s5, 1")
        h.append("    beq s5, zero, fa_assemble")
        h.append("    srli t6, s4, 1")
        h.append("    andi t6, t6, 1")
        h.append("    andi s9, s4, 1")
        h.append("    or t6, t6, s9")
        h.append("    srli s9, s4, 3")
        h.append("    andi s9, s9, 1")
        h.append("    or t6, t6, s9")
        h.append("    beq t6, zero, fa_assemble")
        h.append("    srli s4, s4, 3")
        h.append("    addi s4, s4, 1")
        h.append("    li t6, 16777216")
        h.append("    and t6, s4, t6")
        h.append("    beq t6, zero, fa_assemble2")
        h.append("    srli s4, s4, 1")
        h.append("    addi s3, s3, 1")
        h.append("    j fa_assemble2")
        h.append("fa_assemble:")
        h.append("    srli s4, s4, 3")
        h.append("fa_assemble2:")
        h.append("    li t6, 255")
        h.append("    bge s3, t6, fa_inf")
        h.append("    bge zero, s3, fa_flush")
        h.append("    slli t6, s3, 23")
        h.append("    or a0, s2, t6")
        h.append("    li t6, 8388607")
        h.append("    and t6, s4, t6")
        h.append("    or a0, a0, t6")
        h.append("    ret")
        h.append("fa_inf:")
        h.append("    li t6, 2139095040")
        h.append("    or a0, s2, t6")
        h.append("    ret")
        h.append("forge_fmul:")
        h.append("    srli t2, a0, 23")
        h.append("    andi t2, t2, 255")
        h.append("    srli t3, a1, 23")
        h.append("    andi t3, t3, 255")
        h.append("    li t6, 8388607")
        h.append("    and t4, a0, t6")
        h.append("    and t5, a1, t6")
        h.append("    or t6, t2, t4")
        h.append("    beq t6, zero, fm_zero")
        h.append("    or t6, t3, t5")
        h.append("    beq t6, zero, fm_zero")
        h.append("    xor s2, a0, a1")
        h.append("    li t6, -2147483648")
        h.append("    and s2, s2, t6")
        h.append("    add s3, t2, t3")
        h.append("    addi s3, s3, -127")
        h.append("    li t6, 8388608")
        h.append("    or t4, t4, t6")
        h.append("    or t5, t5, t6")
        h.append("    mulhu s4, t4, t5")
        h.append("    mul s5, t4, t5")
        h.append("    li t6, 32768")
        h.append("    bltu s4, t6, fm_shift23")
        h.append("    slli s6, s4, 8")
        h.append("    srli t6, s5, 24")
        h.append("    or s6, s6, t6")
        h.append("    li t6, 16777215")
        h.append("    and t6, s5, t6")
        h.append("    srli s7, t6, 23")
        h.append("    andi s7, s7, 1")
        h.append("    srli s8, t6, 22")
        h.append("    andi s8, s8, 1")
        h.append("    li s9, 4194303")
        h.append("    and s9, t6, s9")
        h.append("    sltu s9, zero, s9")
        h.append("    addi s3, s3, 1")
        h.append("    j fm_round")
        h.append("fm_shift23:")
        h.append("    slli s6, s4, 9")
        h.append("    srli t6, s5, 23")
        h.append("    or s6, s6, t6")
        h.append("    li t6, 8388607")
        h.append("    and t6, s5, t6")
        h.append("    srli s7, t6, 22")
        h.append("    andi s7, s7, 1")
        h.append("    srli s8, t6, 21")
        h.append("    andi s8, s8, 1")
        h.append("    li s9, 2097151")
        h.append("    and s9, t6, s9")
        h.append("    sltu s9, zero, s9")
        h.append("fm_round:")
        h.append("    beq s7, zero, fm_assemble")
        h.append("    or t6, s8, s9")
        h.append("    andi s10, s6, 1")
        h.append("    or t6, t6, s10")
        h.append("    beq t6, zero, fm_assemble")
        h.append("    addi s6, s6, 1")
        h.append("    li t6, 16777216")
        h.append("    and t6, s6, t6")
        h.append("    beq t6, zero, fm_assemble")
        h.append("    srli s6, s6, 1")
        h.append("    addi s3, s3, 1")
        h.append("fm_assemble:")
        h.append("    li t6, 255")
        h.append("    bge s3, t6, fm_inf")
        h.append("    bge zero, s3, fm_zero_signed")
        h.append("    slli t6, s3, 23")
        h.append("    or a0, s2, t6")
        h.append("    li t6, 8388607")
        h.append("    and t6, s6, t6")
        h.append("    or a0, a0, t6")
        h.append("    ret")
        h.append("fm_inf:")
        h.append("    li t6, 2139095040")
        h.append("    or a0, s2, t6")
        h.append("    ret")
        h.append("fm_zero:")
        h.append("    xor a0, a0, a1")
        h.append("    li t6, -2147483648")
        h.append("    and a0, a0, t6")
        h.append("    ret")
        h.append("fm_zero_signed:")
        h.append("    mv a0, s2")
        h.append("    ret")
        if self.has_trap_handler:
            # Trap entry: save every register the handler could
            # touch on the stack (sp is always valid at a trap in
            # well-formed programs), pass the trap-frame pointer in
            # a0 (no-arg handlers ignore it), call the Qasida
            # handler, then check mscratch: if the handler wrote a
            # non-zero frame pointer there, switch stacks to it
            # (this is how the scheduler context-switches) and clear
            # it, restore, and return from the trap. The stub does
            # NOT touch mepc: advancing past an ecall (or not) is
            # the handler's job — it reads mcause/mepc via csr_read
            # and writes mepc via csr_write.
            regs = ["ra", "gp", "tp", "t0", "t1", "t2", "s0", "s1",
                    "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7",
                    "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9",
                    "s10", "s11", "t3", "t4", "t5", "t6"]
            h.append("forge_trap_entry:")
            h.append(f"    addi sp, sp, -{4 * len(regs)}")
            for i, r in enumerate(regs):
                h.append(f"    sw {r}, {4 * i}(sp)")
            h.append("    mv a0, sp")
            h.append("    jal ra, trap_handler")
            h.append("    csrr t0, 832")
            h.append("    beq t0, zero, forge_trap_noswitch")
            h.append("    mv sp, t0")
            h.append("    csrw 832, zero")
            h.append("forge_trap_noswitch:")
            for i, r in enumerate(regs):
                h.append(f"    lw {r}, {4 * i}(sp)")
            h.append(f"    addi sp, sp, {4 * len(regs)}")
            h.append("    mret")
        return h

    # ---------- functions ----------
    def gen_func(self, fn):
        self.cur_fn = fn.name
        self.slot_n = 0
        self.free = list(TEMPS)
        self.live = []
        self.env = [{}]
        self.epilogue = f"{fn.name}_epilogue"
        self.emit(f"{fn.name}:")
        self.emit("    addi sp, sp, -8")
        self.emit("    sw ra, 4(sp)")
        self.emit("    sw s0, 0(sp)")
        self.emit("    mv s0, sp")
        self.emit(f"    addi sp, sp, -{FRAME_BYTES}")
        for pname, ptype in fn.params:
            slot = self.alloc_slot()
            self.env[0][pname] = (slot, ptype)
        # Store incoming args into their slots (a0-a7).
        for i, (pname, _pt) in enumerate(fn.params):
            slot, _t = self.env[0][pname]
            self.emit(f"    sw a{i}, {self.slot_off(slot)}(s0)")
        self.gen_block(fn.body)
        if fn.name == "main":
            self.emit_halt()
        else:
            self.emit(f"{self.epilogue}:")
            self.emit("    mv sp, s0")
            self.emit("    lw s0, 0(sp)")
            self.emit("    lw ra, 4(sp)")
            self.emit("    addi sp, sp, 8")
            self.emit("    ret")
        self.env = []
        self.cur_fn = None

    def gen_block(self, block):
        self.env.append({})
        for stmt in block.stmts:
            self.gen_stmt(stmt)
        self.env.pop()

    # ---------- statements ----------
    def gen_stmt(self, stmt):
        if isinstance(stmt, A.Block):
            self.gen_block(stmt)
            return
        if isinstance(stmt, A.Scope):
            # No threads on big32: a scope without spawn runs as its
            # block, and a spawn inside still fails as before.
            self.gen_block(stmt.body)
            return
        if isinstance(stmt, A.Let):
            t = stmt.ann if stmt.ann else self.expr_type(stmt.expr)
            if t in self.struct_layout:
                fields = self.struct_layout[t]
                if isinstance(stmt.expr, A.StructLit):
                    if stmt.expr.name != t:
                        raise ForgeError(
                            f"struct literal type {stmt.expr.name} does not match {t}")
                    base = self.alloc_slot()
                    for _ in range(len(fields) - 1):
                        self.alloc_slot()
                    self.env[-1][stmt.name] = (base, t)
                    vals = {}
                    for fname, fexpr in stmt.expr.fields:
                        vals[fname] = fexpr
                    for k, (fname, _ft) in enumerate(fields):
                        if fname not in vals:
                            raise ForgeError(f"struct literal missing field {fname}")
                        r = self.gen_expr(vals[fname])
                        self.emit(f"    sw {r}, {self.slot_off(base + k)}(s0)")
                        self.free_reg(r)
                    return
                if isinstance(stmt.expr, A.Var):
                    sbase, st = self.lookup(stmt.expr.name)
                    if st != t:
                        raise ForgeError("struct copy type mismatch on big32")
                    base = self.alloc_slot()
                    for _ in range(len(fields) - 1):
                        self.alloc_slot()
                    self.env[-1][stmt.name] = (base, t)
                    for k in range(len(fields)):
                        r = self.alloc()
                        self.emit(f"    lw {r}, {self.slot_off(sbase + k)}(s0)")
                        self.emit(f"    sw {r}, {self.slot_off(base + k)}(s0)")
                        self.free_reg(r)
                    return
                raise ForgeError(
                    "struct variables on big32 come from literals or copies (v1)")
            r = self.gen_expr(stmt.expr)
            slot = self.alloc_slot()
            self.env[-1][stmt.name] = (slot, t)
            self.emit(f"    sw {r}, {self.slot_off(slot)}(s0)")
            self.free_reg(r)
            return
        if isinstance(stmt, A.Assign):
            slot, t = self.lookup(stmt.name)
            if t in self.struct_layout:
                if not isinstance(stmt.expr, A.Var):
                    raise ForgeError(
                        "struct assignment on big32 copies a struct variable (v1)")
                sbase, st = self.lookup(stmt.expr.name)
                if st != t:
                    raise ForgeError("struct copy type mismatch on big32")
                for k in range(len(self.struct_layout[t])):
                    r = self.alloc()
                    self.emit(f"    lw {r}, {self.slot_off(sbase + k)}(s0)")
                    self.emit(f"    sw {r}, {self.slot_off(slot + k)}(s0)")
                    self.free_reg(r)
                return
            r = self.gen_expr(stmt.expr)
            self.emit(f"    sw {r}, {self.slot_off(slot)}(s0)")
            self.free_reg(r)
            return
        if isinstance(stmt, A.IndexAssign):
            base = stmt.base.base
            if not isinstance(base, A.Var):
                raise ForgeError("index assignment target must be a variable on big32")
            slot, _t = self.lookup(base.name)
            if _t == "str":
                raise ForgeError("cannot assign to a string index on big32")
            if _t.startswith("[") and _t.endswith("]") and _t[1:-1] in self.struct_layout:
                raise ForgeError("arrays of structs are not supported on big32 (v1)")
            ptr = self.alloc()
            self.emit(f"    lw {ptr}, {self.slot_off(slot)}(s0)")
            idx = self.gen_expr(stmt.base.index)
            val = self.gen_expr(stmt.expr)
            addr = self.alloc()
            self.emit(f"    addi {addr}, {ptr}, 4")
            self.emit(f"    slli {idx}, {idx}, 2")
            self.emit(f"    add {addr}, {addr}, {idx}")
            self.emit(f"    sw {val}, 0({addr})")
            for r in (addr, val, idx, ptr):
                self.free_reg(r)
            return
        if isinstance(stmt, A.FieldAssign):
            fa = stmt.target
            if not isinstance(fa.base, A.Var):
                raise ForgeError("field assignment base must be a variable on big32")
            base, t = self.lookup(fa.base.name)
            if t not in self.struct_layout:
                raise ForgeError("field assignment on a non-struct variable on big32")
            fields = self.struct_layout[t]
            idx = None
            for k, (fname, _ft) in enumerate(fields):
                if fname == fa.field:
                    idx = k
            if idx is None:
                raise ForgeError(f"struct {t} has no field {fa.field}")
            r = self.gen_expr(stmt.expr)
            self.emit(f"    sw {r}, {self.slot_off(base + idx)}(s0)")
            self.free_reg(r)
            return
        if isinstance(stmt, A.Match):
            raise ForgeError("match/enums are not supported on big32 (v1)")
        if isinstance(stmt, A.Spawn):
            raise ForgeError("spawn/threads are not supported on big32 (v1)")
        if isinstance(stmt, A.If):
            els = self.label("else")
            end = self.label("endif")
            cond = self.gen_expr(stmt.cond)
            self.emit(f"    beq {cond}, zero, {els}")
            self.free_reg(cond)
            self.gen_block(stmt.then)
            self.emit(f"    j {end}")
            self.emit(f"{els}:")
            if stmt.els is not None:
                self.gen_block(stmt.els)
            self.emit(f"{end}:")
            return
        if isinstance(stmt, A.Break):
            if not self.loop_ends:
                raise ForgeError("big32: break outside a loop", stmt.line, stmt.col)
            self.emit(f"    j {self.loop_ends[-1]}")
            return
        if isinstance(stmt, A.Continue):
            if not self.loop_conts:
                raise ForgeError("big32: continue outside a loop", stmt.line, stmt.col)
            self.emit(f"    j {self.loop_conts[-1]}")
            return
        if isinstance(stmt, A.While):
            cond_l = self.label("while")
            end = self.label("wend")
            self.emit(f"{cond_l}:")
            cond = self.gen_expr(stmt.cond)
            self.emit(f"    beq {cond}, zero, {end}")
            self.free_reg(cond)
            self.loop_ends.append(end)
            self.loop_conts.append(cond_l)
            self.gen_block(stmt.body)
            self.loop_conts.pop()
            self.loop_ends.pop()
            self.emit(f"    j {cond_l}")
            self.emit(f"{end}:")
            return
        if isinstance(stmt, A.For):
            self.gen_for(stmt)
            return
        if isinstance(stmt, A.Return):
            if stmt.expr is not None:
                r = self.gen_expr(stmt.expr)
                self.emit(f"    mv a0, {r}")
                self.free_reg(r)
            if self.cur_fn == "main":
                self.emit_halt()
            else:
                self.emit(f"    j {self.epilogue}")
            return
        if isinstance(stmt, A.ExprStmt):
            call = stmt.expr
            if isinstance(call, A.Call) and call.name in ("print", "println"):
                self.gen_print(call)
                return
            if isinstance(call, A.Call) and call.name == "assert":
                cond = self.gen_expr(call.args[0])
                ok = self.label("assert_ok")
                self.emit(f"    bne {cond}, zero, {ok}")
                self.free_reg(cond)
                msg = self.gen_expr(call.args[1])
                self.emit(f"    mv a0, {msg}")
                self.free_reg(msg)
                self.emit("    jal ra, forge_print_str")
                self.emit("    li a0, 1")
                self.emit_halt()
                self.emit(f"{ok}:")
                return
            if isinstance(call, A.Call) and call.name == "fail":
                msg = self.gen_expr(call.args[0])
                self.emit(f"    mv a0, {msg}")
                self.free_reg(msg)
                self.emit("    jal ra, forge_print_str")
                self.emit("    li a0, 1")
                self.emit_halt()
                return
            if isinstance(call, A.Call) and call.name in ("fail_compile", "eprintln"):
                # Slice 5 driver builtins write to stderr; big32 has
                # no OS/stderr in v1.
                raise ForgeError(f"builtin {call.name}() is not supported on big32 (v1)")
            if isinstance(call, A.Call) and call.name == "push":
                raise ForgeError("push (dynamic growth) is not supported on big32 (v1)")
            r = self.gen_expr(stmt.expr)
            self.free_reg(r)
            return
        raise ForgeError(f"unsupported statement {type(stmt).__name__} on big32")

    def gen_for(self, stmt):
        # for v in range(n) { ... }
        if isinstance(stmt.expr, A.Call) and stmt.expr.name == "range":
            n = self.gen_expr(stmt.expr.args[0])
            cnt_slot = self.alloc_slot()
            var_slot = self.alloc_slot()
            self.emit(f"    sw zero, {self.slot_off(cnt_slot)}(s0)")
            top = self.label("for")
            end = self.label("forend")
            self.emit(f"{top}:")
            cnt = self.alloc()
            self.emit(f"    lw {cnt}, {self.slot_off(cnt_slot)}(s0)")
            self.emit(f"    slt {cnt}, {cnt}, {n}")
            self.emit(f"    beq {cnt}, zero, {end}")
            self.free_reg(cnt)
            # loop var = counter value
            val = self.alloc()
            self.emit(f"    lw {val}, {self.slot_off(cnt_slot)}(s0)")
            self.emit(f"    sw {val}, {self.slot_off(var_slot)}(s0)")
            self.free_reg(val)
            self.env.append({stmt.name: (var_slot, "int")})
            self.loop_ends.append(end)
            cont = self.label("forcont")
            self.loop_conts.append(cont)
            self.gen_block(stmt.body)
            self.loop_conts.pop()
            self.loop_ends.pop()
            self.env.pop()
            self.emit(f"{cont}:")
            inc = self.alloc()
            self.emit(f"    lw {inc}, {self.slot_off(cnt_slot)}(s0)")
            self.emit(f"    addi {inc}, {inc}, 1")
            self.emit(f"    sw {inc}, {self.slot_off(cnt_slot)}(s0)")
            self.free_reg(inc)
            self.free_reg(n)
            self.emit(f"    j {top}")
            self.emit(f"{end}:")
            return
        # for v in array { ... }
        arr_t = self.expr_type(stmt.expr)
        if not arr_t.startswith("["):
            raise ForgeError("for loop over a non-array is not supported on big32")
        et = arr_t[1:-1]
        if et in self.struct_layout:
            raise ForgeError("arrays of structs are not supported on big32 (v1)")
        ptr = self.gen_expr(stmt.expr)
        len_slot = self.alloc_slot()
        idx_slot = self.alloc_slot()
        var_slot = self.alloc_slot()
        tmp = self.alloc()
        self.emit(f"    lw {tmp}, 0({ptr})")
        self.emit(f"    sw {tmp}, {self.slot_off(len_slot)}(s0)")
        self.free_reg(tmp)
        self.emit(f"    sw zero, {self.slot_off(idx_slot)}(s0)")
        top = self.label("for")
        end = self.label("forend")
        self.emit(f"{top}:")
        idx = self.alloc()
        ln = self.alloc()
        self.emit(f"    lw {idx}, {self.slot_off(idx_slot)}(s0)")
        self.emit(f"    lw {ln}, {self.slot_off(len_slot)}(s0)")
        self.emit(f"    slt {idx}, {idx}, {ln}")
        self.emit(f"    beq {idx}, zero, {end}")
        self.free_reg(idx)
        self.free_reg(ln)
        # element = *(ptr + 4 + idx*4)
        idx2 = self.alloc()
        addr = self.alloc()
        self.emit(f"    lw {idx2}, {self.slot_off(idx_slot)}(s0)")
        self.emit(f"    slli {idx2}, {idx2}, 2")
        self.emit(f"    add {addr}, {ptr}, {idx2}")
        self.emit(f"    lw {addr}, 4({addr})")
        self.emit(f"    sw {addr}, {self.slot_off(var_slot)}(s0)")
        self.free_reg(idx2)
        self.free_reg(addr)
        self.env.append({stmt.name: (var_slot, et)})
        self.loop_ends.append(end)
        cont = self.label("forcont")
        self.loop_conts.append(cont)
        self.gen_block(stmt.body)
        self.loop_conts.pop()
        self.loop_ends.pop()
        self.env.pop()
        self.emit(f"{cont}:")
        inc = self.alloc()
        self.emit(f"    lw {inc}, {self.slot_off(idx_slot)}(s0)")
        self.emit(f"    addi {inc}, {inc}, 1")
        self.emit(f"    sw {inc}, {self.slot_off(idx_slot)}(s0)")
        self.free_reg(inc)
        self.free_reg(ptr)
        self.emit(f"    j {top}")
        self.emit(f"{end}:")

    def gen_print(self, call):
        newline = call.name == "println"
        for i, arg in enumerate(call.args):
            t = self.expr_type(arg)
            r = self.gen_expr(arg)
            if t == "int":
                self.emit(f"    mv a0, {r}")
                self.emit("    jal ra, forge_print_int")
            elif t == "bool":
                true_l = self.label("istrue")
                done_l = self.label("bool_done")
                self.emit(f"    bne {r}, zero, {true_l}")
                self.emit(f"    li a0, {self.str_addr('false')}")
                self.emit("    jal ra, forge_print_str")
                self.emit(f"    j {done_l}")
                self.emit(f"{true_l}:")
                self.emit(f"    li a0, {self.str_addr('true')}")
                self.emit("    jal ra, forge_print_str")
                self.emit(f"{done_l}:")
            elif t == "str":
                self.emit(f"    mv a0, {r}")
                self.emit("    jal ra, forge_print_str")
            else:
                raise ForgeError(f"cannot print a value of type {t} on big32")
            self.free_reg(r)
            if i < len(call.args) - 1:
                self.emit(f"    li t0, {UART}")
                self.emit("    li t1, 32")
                self.emit("    sb t1, 0(t0)")
        if newline:
            self.emit(f"    li t0, {UART}")
            self.emit("    li t1, 10")
            self.emit("    sb t1, 0(t0)")

    # ---------- expressions: returns a temp register ----------
    def gen_expr(self, expr):
        if isinstance(expr, A.MethodCall):
            raise ForgeError("big32: trait method calls need struct "
                             "parameters, not supported in v1",
                             expr.line, expr.col)
        if isinstance(expr, A.IntLit):
            r = self.alloc()
            v = expr.value & 0xFFFFFFFF
            if v >= 0x80000000:
                v -= 0x100000000
            self.emit(f"    li {r}, {v}")
            return r
        if isinstance(expr, A.FloatLit):
            # Soft-float v1: a float value IS its IEEE-754
            # single-precision bit pattern in a register.
            bits = struct.unpack("<I", struct.pack("<f", expr.value))[0]
            if bits >= 0x80000000:
                bits -= 0x100000000
            r = self.alloc()
            self.emit(f"    li {r}, {bits}")
            return r
        if isinstance(expr, A.StrLit):
            r = self.alloc()
            self.emit(f"    li {r}, {self.str_addr(expr.value)}")
            return r
        if isinstance(expr, A.BoolLit):
            r = self.alloc()
            self.emit(f"    li {r}, {1 if expr.value else 0}")
            return r
        if isinstance(expr, A.Var):
            slot, t = self.lookup(expr.name)
            if t in self.struct_layout:
                raise ForgeError(
                    "struct values cannot be passed or returned on big32 (v1); "
                    "use field access instead")
            r = self.alloc()
            self.emit(f"    lw {r}, {self.slot_off(slot)}(s0)")
            return r
        if isinstance(expr, A.ArrayLit):
            et = self.expr_type(expr)
            if et in ("[?]", "int"):
                raise ForgeError("array literal needs a known element type on big32")
            inner = et[1:-1]
            if inner in self.struct_layout:
                raise ForgeError("arrays of structs are not supported on big32 (v1)")
            n = len(expr.elems)
            addr = self.static_addr(4 * (n + 1))
            ptr = self.alloc()
            self.emit(f"    li {ptr}, {addr}")
            ln = self.alloc()
            self.emit(f"    li {ln}, {n}")
            self.emit(f"    sw {ln}, 0({ptr})")
            self.free_reg(ln)
            self.emit(f"    addi {ptr}, {ptr}, 4")
            for e in expr.elems:
                er = self.gen_expr(e)
                self.emit(f"    sw {er}, 0({ptr})")
                self.free_reg(er)
                self.emit(f"    addi {ptr}, {ptr}, 4")
            # ptr now points past the end; reload the base address.
            self.emit(f"    li {ptr}, {addr}")
            return ptr
        if isinstance(expr, A.StructLit):
            raise ForgeError(
                "struct literals on big32 appear in let statements only (v1)")
        if isinstance(expr, A.FieldAccess):
            if not isinstance(expr.base, A.Var):
                raise ForgeError("field access base must be a variable on big32")
            base, t = self.lookup(expr.base.name)
            if t not in self.struct_layout:
                raise ForgeError("field access on a non-struct variable on big32")
            for k, (fname, _ft) in enumerate(self.struct_layout[t]):
                if fname == expr.field:
                    r = self.alloc()
                    self.emit(f"    lw {r}, {self.slot_off(base + k)}(s0)")
                    return r
            raise ForgeError(f"struct {t} has no field {expr.field}")
        if isinstance(expr, A.Index):
            if self.expr_type(expr.base) == "str":
                raise ForgeError("string indexing is not supported on big32 (v1)")
            bt = self.expr_type(expr.base)
            if bt.startswith("[") and bt.endswith("]") and bt[1:-1] in self.struct_layout:
                raise ForgeError("arrays of structs are not supported on big32 (v1)")
            # Float elements load as bit patterns, same as ints.
            base = self.gen_expr(expr.base)
            idx = self.gen_expr(expr.index)
            addr = self.alloc()
            self.emit(f"    addi {addr}, {base}, 4")
            self.emit(f"    slli {idx}, {idx}, 2")
            self.emit(f"    add {addr}, {addr}, {idx}")
            self.emit(f"    lw {addr}, 0({addr})")
            self.free_reg(base)
            self.free_reg(idx)
            return addr
        if isinstance(expr, A.Cast):
            if expr.target == "float" or self.expr_type(expr.expr) == "float":
                raise ForgeError(
                    "int<->float casts are not supported on big32 (v1)")
            return self.gen_expr(expr.expr)
        if isinstance(expr, A.UnaryOp):
            r = self.gen_expr(expr.expr)
            if expr.op == "-":
                if self.expr_type(expr.expr) == "float":
                    # Flip the sign bit only.
                    s = self.alloc()
                    self.emit(f"    li {s}, -2147483648")
                    self.emit(f"    xor {r}, {r}, {s}")
                    self.free_reg(s)
                else:
                    self.emit(f"    sub {r}, zero, {r}")
            elif expr.op == "!":
                self.emit(f"    xori {r}, {r}, 1")
            elif expr.op == "~":
                # Bitwise not: x xor -1 (-1 fits the 12-bit immediate).
                self.emit(f"    xori {r}, {r}, -1")
            else:
                raise ForgeError(f"unsupported unary operator {expr.op} on big32")
            return r
        if isinstance(expr, A.BinOp):
            return self.gen_binop(expr)
        if isinstance(expr, A.Call):
            return self.gen_call(expr)
        raise ForgeError(f"unsupported expression {type(expr).__name__} on big32")

    def gen_binop(self, expr):
        # Short-circuit && / || with branches.
        if expr.op in ("&&", "||"):
            left = self.gen_expr(expr.left)
            end = self.label("logic")
            if expr.op == "&&":
                self.emit(f"    beq {left}, zero, {end}")
                right = self.gen_expr(expr.right)
                self.emit(f"    mv {left}, {right}")
                self.free_reg(right)
            else:
                self.emit(f"    bne {left}, zero, {end}")
                right = self.gen_expr(expr.right)
                self.emit(f"    mv {left}, {right}")
                self.free_reg(right)
            self.emit(f"{end}:")
            return left
        left = self.gen_expr(expr.left)
        right = self.gen_expr(expr.right)
        lt = self.expr_type(expr.left)
        if lt == "str":
            raise ForgeError("string comparison/concatenation is not supported on big32 (v1)")
        op = expr.op
        if lt == "float":
            if op in ("/", "%", "<", ">", "<=", ">=", "&", "|", "^",
                      "<<", ">>"):
                raise ForgeError(
                    f"float operator {op} is not supported on big32 (v1)")
            if op in ("+", "-", "*"):
                # Soft-float helper call. Spill every live
                # temp except the operands (helpers use
                # t/s registers freely; s0/sp/ra are
                # untouched and the frame is s0-based).
                saved = [r for r in self.live if r not in (left, right)]
                if saved:
                    self.emit(f"    addi sp, sp, -{4 * len(saved)}")
                    for i, r in enumerate(saved):
                        self.emit(f"    sw {r}, {4 * i}(sp)")
                    for r in saved:
                        self.live.remove(r)
                self.emit(f"    mv a0, {left}")
                self.emit(f"    mv a1, {right}")
                helper = {"+": "forge_fadd", "-": "forge_fsub",
                          "*": "forge_fmul"}[op]
                self.emit(f"    jal ra, {helper}")
                self.emit(f"    mv {left}, a0")
                self.free_reg(right)
                if saved:
                    for i, r in enumerate(saved):
                        self.emit(f"    lw {r}, {4 * i}(sp)")
                    self.emit(f"    addi sp, sp, {4 * len(saved)}")
                    for r in saved:
                        self.live.append(r)
                return left
            # == / != fall through to the int compare
            # below: bitwise equality on the patterns.
        if op == "+":
            self.emit(f"    add {left}, {left}, {right}")
        elif op == "-":
            self.emit(f"    sub {left}, {left}, {right}")
        elif op == "*":
            self.emit(f"    mul {left}, {left}, {right}")
        elif op == "/":
            self.emit(f"    div {left}, {left}, {right}")
        elif op == "%":
            self.emit(f"    rem {left}, {left}, {right}")
        elif op == "<":
            self.emit(f"    slt {left}, {left}, {right}")
        elif op == ">":
            self.emit(f"    slt {left}, {right}, {left}")
        elif op == "<=":
            self.emit(f"    slt {left}, {right}, {left}")
            self.emit(f"    xori {left}, {left}, 1")
        elif op == ">=":
            self.emit(f"    slt {left}, {left}, {right}")
            self.emit(f"    xori {left}, {left}, 1")
        elif op == "==":
            self.emit(f"    xor {left}, {left}, {right}")
            self.emit(f"    sltiu {left}, {left}, 1")
        elif op == "!=":
            self.emit(f"    xor {left}, {left}, {right}")
            self.emit(f"    sltu {left}, zero, {left}")
        elif op == "&":
            self.emit(f"    and {left}, {left}, {right}")
        elif op == "|":
            self.emit(f"    or {left}, {left}, {right}")
        elif op == "^":
            self.emit(f"    xor {left}, {left}, {right}")
        elif op == "<<":
            self.emit(f"    sll {left}, {left}, {right}")
        elif op == ">>":
            self.emit(f"    sra {left}, {left}, {right}")
        else:
            raise ForgeError(f"unsupported operator {op} on big32")
        self.free_reg(right)
        return left

    def gen_call(self, expr):
        name = expr.name
        if name == "len":
            arg = expr.args[0]
            at = self.expr_type(arg)
            r = self.gen_expr(arg)
            if at == "str":
                self.emit(f"    mv a0, {r}")
                self.free_reg(r)
                self.emit("    jal ra, forge_strlen")
                out = self.alloc()
                self.emit(f"    mv {out}, a0")
                return out
            if at.startswith("["):
                self.emit(f"    lw {r}, 0({r})")
                return r
            raise ForgeError("len() of a non-array, non-string is not supported on big32")
        if name == "range":
            raise ForgeError("range() is only supported as a for-loop source on big32")
        if name in ("print", "println", "push"):
            raise ForgeError(f"{name}() cannot be used as an expression on big32")
        if name in ("sqrt", "exp", "log", "pow", "clock_micros", "read_file",
                    "read_line",
                    "write_file", "args", "parse_int", "split", "join",
                    "substr", "trim", "starts_with", "ends_with", "http_get",
                    "run_command"):
            raise ForgeError(f"builtin {name}() is not supported on big32 (v1)")
        if name == "peek32":
            r = self.gen_expr(expr.args[0])
            self.emit(f"    lw {r}, 0({r})")
            return r
        if name == "poke32":
            a = self.gen_expr(expr.args[0])
            v = self.gen_expr(expr.args[1])
            self.emit(f"    sw {v}, 0({a})")
            self.free_reg(a)
            return v
        if name in ("wrapping_add", "wrapping_sub", "wrapping_mul"):
            # 32-bit add/sub/mul wrap by nature on big32.
            a = self.gen_expr(expr.args[0])
            b = self.gen_expr(expr.args[1])
            op = {"wrapping_add": "add", "wrapping_sub": "sub",
                  "wrapping_mul": "mul"}[name]
            self.emit(f"    {op} {a}, {a}, {b}")
            self.free_reg(b)
            return a
        if name == "wrapping_neg":
            a = self.gen_expr(expr.args[0])
            self.emit(f"    sub {a}, zero, {a}")
            return a
        if name == "csr_read":
            if not isinstance(expr.args[0], A.IntLit):
                raise ForgeError("csr_read() takes a literal CSR number",
                                 expr.line, expr.col)
            r = self.alloc()
            self.emit(f"    csrr {r}, {expr.args[0].value}")
            return r
        if name in ("csr_write", "csr_set", "csr_clear"):
            if not isinstance(expr.args[0], A.IntLit):
                raise ForgeError(f"{name}() takes a literal CSR number",
                                 expr.line, expr.col)
            v = self.gen_expr(expr.args[1])
            mnem = {"csr_write": "csrw", "csr_set": "csrs",
                    "csr_clear": "csrc"}[name]
            self.emit(f"    {mnem} {expr.args[0].value}, {v}")
            return v
        if name == "ecall":
            # SBI-style call: extension id in a7, argument in a0,
            # result back in a0. The trap stub saves/restores every
            # register, so no spill is needed across the ecall.
            eid = self.gen_expr(expr.args[0])
            arg = self.gen_expr(expr.args[1])
            arg_regs = [eid, arg]
            scratch = None
            for cand in TEMPS:
                if cand not in arg_regs and cand not in self.live:
                    scratch = cand
                    break
            if scratch is None:
                raise ForgeError("no scratch register available for ecall")
            for target, r in ((7, eid), (0, arg)):
                if r == f"a{target}":
                    continue
                self.emit(f"    mv {scratch}, {r}")
                self.emit(f"    mv a{target}, {scratch}")
            self.emit("    ecall")
            out = self.alloc()
            self.emit(f"    mv {out}, a0")
            self.free_reg(eid)
            self.free_reg(arg)
            return out
        if name == "ecall3":
            # Three-argument call: extension id in a7, arguments in
            # a0 and a1, result back in a0. Arg registers come from
            # TEMPS (never a-regs), so the sequential moves below
            # cannot clobber an argument still to be moved.
            eid = self.gen_expr(expr.args[0])
            arg0 = self.gen_expr(expr.args[1])
            arg1 = self.gen_expr(expr.args[2])
            arg_regs = [eid, arg0, arg1]
            scratch = None
            for cand in TEMPS:
                if cand not in arg_regs and cand not in self.live:
                    scratch = cand
                    break
            if scratch is None:
                raise ForgeError("no scratch register available for ecall3")
            for target, r in ((7, eid), (0, arg0), (1, arg1)):
                if r == f"a{target}":
                    continue
                self.emit(f"    mv {scratch}, {r}")
                self.emit(f"    mv a{target}, {scratch}")
            self.emit("    ecall")
            out = self.alloc()
            self.emit(f"    mv {out}, a0")
            self.free_reg(eid)
            self.free_reg(arg0)
            self.free_reg(arg1)
            return out
        if name not in self.funcs:
            raise ForgeError(f"unknown function {name} on big32")
        if len(expr.args) > 8:
            raise ForgeError("more than 8 function arguments are not supported on big32 (v1)")
        arg_regs = [self.gen_expr(a) for a in expr.args]
        # Spill every other live temp across the call.
        saved = [r for r in self.live if r not in arg_regs]
        if saved:
            self.emit(f"    addi sp, sp, -{4 * len(saved)}")
            for i, r in enumerate(saved):
                self.emit(f"    sw {r}, {4 * i}(sp)")
            for r in saved:
                self.live.remove(r)
        # Move args to a0-a7 via a scratch temp that is not an arg reg.
        scratch = None
        for cand in TEMPS:
            if cand not in arg_regs and cand not in self.live:
                scratch = cand
                break
        if scratch is None:
            raise ForgeError("no scratch register available for a big32 call")
        for i, r in enumerate(arg_regs):
            if r == f"a{i}":
                continue
            self.emit(f"    mv {scratch}, {r}")
            self.emit(f"    mv a{i}, {scratch}")
            self.free_reg(r)
        self.emit(f"    jal ra, {name}")
        if saved:
            for i, r in enumerate(saved):
                self.emit(f"    lw {r}, {4 * i}(sp)")
            self.emit(f"    addi sp, sp, {4 * len(saved)}")
            for r in saved:
                self.live.append(r)
        out = self.alloc()
        self.emit(f"    mv {out}, a0")
        return out


def generate_rv(program, types, stack_top=None):
    gen = RVGen(program, types,
                stack_top=stack_top if stack_top is not None else SP_START)
    return gen.generate()
