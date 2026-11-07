# From scratch: making Qasida capable of its own OS

Goal (set 27 Oct 2026): an operating system **bigger than TempleOS,
written completely in Qasida, with no Linux anywhere in it**.
Not a Linux distro with a theme (that is what Black Moon OS is today),
and not a simulation (that is what JalOS is today): a real kernel
that boots on real hardware — starting with our own CPU, big32 —
plus the userspace on top of it, all in our own language.

This document is the capability roadmap. The order matters: the
language must be able to touch hardware **before** kernel code is
written in it. Each phase ends at a verified checkpoint; kernel
building starts after Phase E.

## Why TempleOS is the right yardstick — and what "bigger" means

TempleOS (Terry Davis, ~2005–2013, one person) was: its own
language (HolyC), its own kernel, its own window manager and
filesystem, ring-0-only, no networking, no multi-user, x86-64 only,
roughly 100,000 lines. "Bigger" here means beating it where it was
weak while matching where it was strong:

- Own language AND own CPU (TempleOS had only the language; big32
  is already ours) — the stack is more self-owned from the start.
- Networking (TempleOS had none) and real user programs written in
  the same language as the kernel.
- A windowed desktop, not just a terminal.
- Honest limits, stated up front: big32 is single-core and
  simulated, so "bigger" is measured in capability and completeness,
  not in raw performance or hardware range. A PC (x86-64) port is a
  later phase, not phase one: PC hardware needs ACPI, PCI, USB, GPU
  and NVMe drivers, each a project of its own.

## What the language cannot do today (the blockers)

- ~~No bitwise operators~~ — FIXED in Phase A. Device registers are
  all bitfields; without `& | ^ << >> ~` no driver code is possible.
- No raw memory access: no pointers, no volatile loads/stores, so
  no MMIO (UART, framebuffer, CLINT) can be touched.
- No freestanding mode: generated C links libc (stdio, pthread,
  sockets, files) and expects a hosted `main`. A kernel has no OS
  underneath to provide those.
- No trap/interrupt primitives: no CSR access, no way to install a
  trap handler, no timer interrupt path.
- No inline assembly: some things (trap entry, `mret`, `fence`)
  cannot be expressed without it, or need dedicated builtins.
- Heap depends on libc `malloc`: strings and arrays allocate
  through it. A kernel needs an allocator it owns.
- Int width differs by backend: 64-bit native/WASM, 32-bit big32.
  Kernel code must be written width-aware (see the shift-count
  note in Phase A).

## Phases

### Phase A — Bitwise operators (DONE 27 Oct 2026)

`& | ^ << >> ~` on ints, C-like precedence (`|` loosest, then `^`,
then `&`, then `==`/`!=`, then comparisons, then `<<` `>>`, then
`+` `-`, then `*` `/` `%`). Semantics, pinned by
`tests/test_bitwise.py` (18 checks: native, WASM, big32 model UART
transcript, checker rejections, formatter stability):

- `& | ^`: two's-complement, all backends.
- `<<`: wraps through the unsigned width, so a negative left
  operand is defined (plain C leaves it undefined).
- `>>`: arithmetic (sign-extending) on all backends.
- Shift counts are masked: 0..63 on native/WASM (i64), 0..31 on
  big32 (32-bit words). Counts at or above the word width therefore
  differ across backends **by design**; kernel code must keep
  counts below 32 to be portable, or accept the divergence.
- big32 already emitted `and`/`or`/`xor`/`sll`/`sra` for these
  operators before the parser produced them; the work was lexer,
  parser, checker, formatter, native shifts, WASM opcodes, and the
  big32 `~` (`xori` with -1). One real bug caught by the tests:
  WASM `>>` was first emitted as `shr_u` (0x88) instead of `shr_s`
  (0x87); fixed and re-verified.

### Phase B — Raw memory access (DONE 27 Oct 2026)

Volatile `peek32`/`poke32` builtins (32-bit load/store through a
raw address): native emits a volatile pointer dereference
(`forge_peek32`/`forge_poke32` helpers, so the compiler can never
optimise an MMIO access away), big32 emits `lw`/`sw`, WASM
rejects loudly (no raw addresses there). `peek32(addr) -> int`
is an expression; `poke32(addr, val)` is statement-only, like
`push` — a write has no value, and the checker rejects using it
as one (this rule was found by the tests, not planned: the first
version made poke32 an expression and the checker refused bare
`poke32(...);` statements). Both are UNCHECKED in every mode, by
design: a raw address is unsafe by definition. Pinned by
`tests/test_peek_poke.py` (13 checks): big32 model run writes
byte `A` to the UART address and reads back status 0, RX -1,
and a RAM round-trip (`A0\n-1\n123456` transcript); native
generated C contains the volatile helpers; checker rejections;
WASM rejections. Note for kernel code: the language has no
address-of operator, so native round-trips cannot be addressed
from Qasida itself — big32 is where these builtins are truly
proven.

### Phase C — Freestanding codegen (DONE 27 Oct 2026)

`forge.py build --freestanding` (also `check`/`emit`): the
program stands without libc or Linux. Native builds with
`-nostdlib`; the program's own `_start` entry calls
`qasida_main` and exits via the raw Linux `exit_group` syscall
with main's return value (int main -> exit code, void main ->
exit 0), so a freestanding program's only observable output is
its exit code. The prelude is a minimal header (only the
freestanding-compatible `<stdint.h>`/`<stdbool.h>` types, checked
arithmetic via gcc builtins, volatile peek/poke helpers);
`fail()` halts in an infinite loop, since there is no OS to
exit to. Anything needing the OS is a clean error, not a link
error: the checker rejects files, sockets, threads (spawn and
scope), clock, args, print/println, libm builtins (sqrt/exp/log/
pow/abs), and extern C functions; the codegen rejects any
string/array value (including structs carrying str/array fields)
and `emit_free_owned` is a no-op, since no owned values can
exist. big32 runs under the same flag (its output is already
bare metal); WASM refuses the flag outright. Pinned by
`tests/test_freestanding.py` (24 checks): native exit codes
(27 computed, 0 void, 42 fast), ldd statically linked, nm zero
undefined symbols, `_start` + `qasida_main` present, checked
overflow halts (proven by timeout, not exit), big32 model
"OK" via poke32 + RAM round-trip, all rejections, and the
hosted control (the same print program builds fine without the
flag). Two real bugs found by testing, both fixed: the Return
path in main also emitted `forge_join_threads`, and unused
str/array parameters could emit frees for helpers that don't
exist. Limits: x86_64 Linux only for native (the `_start` asm);
freestanding v1 has no allocator, so no strings/arrays and no
I/O library — output is via poke32 (MMIO) and exit codes. The
bump allocator for strings/arrays is now kernel work, not a
Phase C promise: the roadmap's original allocator line is
superseded by this honest v1.

### Phase D — Traps, interrupts, and firmware calls (DONE 27 Oct 2026)

- CSR builtins: `csr_read(csr) -> int` (expression) and
  statement-only `csr_write`/`csr_set`/`csr_clear` (like
  `poke32`). The CSR number must be a literal: RISC-V CSR
  instructions take a 12-bit immediate, not a register, so a
  runtime value cannot encode one — the checker enforces this.
  Native and WASM reject all four loudly (no RISC-V CSRs there).
- Trap-handler hook: defining `fn trap_handler()` (no args, or
  one int = the trap-frame pointer since Phase E — enforced by
  the big32 backend) makes `_start` point `mtvec` at an assembly
  stub that saves all 30 clobberable registers on the stack,
  passes the frame pointer in `a0`, calls the handler, and —
  if the handler wrote a non-zero frame pointer to `mscratch` —
  switches stacks before restoring and `mret`ing. The stub does
  NOT touch `mepc`: advancing past an ecall is the handler's
  job (read `mcause`/`mepc`, write `mepc+4` for ecall traps).
  Program end still halts with a handler wired: main's ending
  (and fail/assert paths) clear `mtvec` before the final ecall,
  since a bare ecall with `mtvec` set would trap, not halt.
- `ecall(eid, arg) -> int`: extension id in `a7`, argument in
  `a0`, result back in `a0`. On SBI firmware this is the SBI
  call primitive; on the model it traps to the program's own
  handler. v1 covers single-argument calls only — full `sbiret`
  (error in `a0`, value in `a1`) and two-argument calls are
  named follow-up, not done.
- Honest checkpoint correction: the model's timer does not
  exist — there is no CLINT, no interrupt delivery, and no SBI
  emulation in `model.py`, so a "timer tick" cannot reach Jal
  Pari code there. The checkpoint is therefore ecall-driven,
  not timer-driven: `tests/test_traps.py` (18 checks) proves
  CSR set/clear/read, an `mscratch` round-trip, an ecall trap
  firing the handler and returning to continue, the exact UART
  transcript `SCRTK`, and a clean halt (not a slide through
  NOPs). A real timer tick needs model or hardware interrupt
  delivery first — that is Phase E bring-up work, not something
  Phase D can fake. Using the existing big32 SBI firmware as a
  bootloader/firmware layer stays honest, not cheating:
  TempleOS also ran on BIOS/UEFI firmware. The kernel itself
  is still ours; SBI is the floor it stands on, and later
  phases can replace SBI console/timer use with direct
  drivers.

### Phase E — Boot story and the first kernel

Linker script, `_start`, trap vector, and the first kernel:
UART hello, timer tick, and a round-robin scheduler — the JalOS
concepts (scheduler, allocator, VFS ideas) rewritten as real
bare-metal code. **Kernel building starts here, not before.**
Checkpoint: the kernel boots on the big32 model and prints its
own banner, tick count, and task switches to UART.

**Checkpoint 1 DONE 27 Oct 2026 — timer tick (model + kernel):**
the Python big32 model gained a minimal timer (mtime 0x10000010,
mtimecmp 0x10000018, 32-bit halves, mtime +1 per step; mip.MTIP
level-sensitive while mtime >= mtimecmp; delivery needs mtvec set
+ mstatus.MIE + mie.MTIE; trap entry saves MIE into MPIE and
clears MIE, mret restores it — without that, the first handler
instruction would re-trap before the handler could reprogram
mtimecmp). The Verilog has no CLINT yet, so this is model-only
so far. Kernel `examples/os/kernel_tick.fg` enables ONLY the
timer interrupt (no mcause dispatch needed), keeps its tick count
in RAM scratch 0x8000 (freestanding has no globals), prints `T`
per tick, and reprograms mtimecmp before mret. Verified:
`tests/test_kernel_tick.py` 5/5, exact UART transcript
`KERNTTTTTDONE`, halted, 5,474 steps. Phase D trap suite still
passes unchanged. NOT done yet: the round-robin scheduler
(checkpoint 2 — needs a yield path and per-task stacks, since
the trap stub restores the same frame it saved).

**Checkpoint 2 DONE 27 Oct 2026 — preemptive round-robin
scheduler:** the trap stub now passes the trap-frame pointer in
`a0` (no-arg handlers ignore it — Phase D programs unaffected)
and switches stacks when the handler writes a non-zero frame
pointer to `mscratch`. The scheduler handler saves the current
task's frame+`mepc` into its TCB each timer tick, loads the next
task's, and hands the next frame to the stub. Tasks are created
by fork: `ecall(2, 0)` copies the 120-byte trap frame onto a
fresh stack, sets the child's saved-`a0` slot to 0 and the
parent's to 1, records the child in TCB[1], and advances `mepc`
past the ecall for both. Kernel `examples/os/kernel_sched.fg`:
`KERN`, then task_a/task_b printing A/B until tick 20, when the
handler clears `mtvec` and the next ecall halts. Verified:
`tests/test_kernel_sched.py` — 907 A + 981 B, 19 A↔B switches,
halted, tick count exactly 20, 21,328 steps; trap + tick suites
still green. Honest limits: tasks must be helper functions
(main's locals live in main's frame, which fork does not copy);
explicit yield is not a switch yet (unknown ecall ids only
advance `mepc`); the timer is still model-only, Verilog has no
CLINT yet. **Phase E's three pieces — UART hello, timer tick,
scheduler — are all done.**

### Phase F and beyond — the OS itself

In order, each its own checkpoint: physical memory management and
paging; a real filesystem (start with a tiny read-only one, then
writable); processes and syscalls; a shell; a window manager and
GUI toolkit in Qasida; keyboard, disk, and display drivers;
networking (the capability TempleOS never had); user programs —
the Moon apps, rewritten as native OS programs. A PC port comes
only after the big32 OS is real.

**Checkpoint 1 DONE 27 Oct 2026 — bump allocator:** an allocator
needs no pointers (addresses are ints, peek32/poke32 are the
read/write). Heap [0xA000, 0xC000), bump pointer in RAM scratch
0x8040. `alloc` aligns up to 4, fails with -1 past the heap end,
else advances and returns the block; `free` is deliberately a
no-op (a free-list is checkpoint 2). Kernel
`examples/os/kernel_alloc.fg` verified by
`tests/test_kernel_alloc.py` 6/6: exact transcript
`KERNKKKKDONE`, halted, patterns intact in the model heap.
Phase E push also landed (RED-MOON- 10d9a19f -> 1c815883,
verified live) and the Phase E model timer was pushed to BIG-32
(commit 9e7ef047, verified live) — the model change is no longer
local-only.

**Checkpoint 2 DONE 27 Oct 2026 — free-list allocator:**
every block carries an 8-byte header [next, total_size] before
its payload; freed blocks live in an address-ordered list.
`alloc` first-fit searches, splits when the remainder is at
least 16 bytes, else takes the block whole, and falls back to
bump allocation; `free` inserts address-ordered and coalesces
with the next physical neighbour first, then the previous one.
Kernel `examples/os/kernel_freelist.fg` verified by
`tests/test_kernel_freelist.py` 6/6: exact transcript
`KERNKKKKDONE` (reuse of b's exact block, patterns, coalesced
re-alloc), halted, and the predicted heap state (16-byte split
remainder at 0xA038 as free-list head). Next: filesystem.

**Checkpoint 3 DONE 27 Oct 2026 — tiny filesystem:** files are
identified by numeric id, not names (freestanding rejects string
values, so names wait for a later checkpoint). Files are
fixed-size at create time, stored as contiguous 256-byte blocks:
file table in scratch 0x8060 (8 slots x 16 bytes [id, used,
size_words, start_block]), next-free-block in scratch 0x8050,
data blocks at 0xD000 (16 x 256 bytes). API: format, create,
write, read (0 ok, -1 fail; read returns -1 as a sentinel for
missing/out-of-bounds). Delete is NOT in v1 — freed blocks are
reclaimed only by reformat. Kernel `examples/os/kernel_fs.fg`
verified by `tests/test_kernel_fs.py`: exact transcript
`KERNKKKKKDONE` (create, readback, cross-block boundary,
disk-full failure, out-of-bounds failure), halted, file
contents intact in the model heap. This checkpoint also caught
and fixed a real big32 backend bug: argument registers used to
be expression temps, so under temp pressure the call-staging
loop overwrote an argument with another one (`fs_write(1, 3,
44)` stored 3 instead of 44); a-regs are now excluded from
TEMPS in `forge_lang/codegen_rv.py`. Next: delete with block
reclaim, then processes.

**Checkpoint 4 DONE 27 Oct 2026 — filesystem v2, delete with
block reclaim:** v1's contiguous files stranded freed blocks,
so v2 uses indexed allocation (the Unix direct-blocks idea):
each file owns a row of up to 16 block indices, and freed
blocks go on a free-list whose links live in the freed blocks
themselves. `create` allocates block by block (free-list first,
then bump) with clean rollback when a block allocation fails
mid-create; `delete` pushes every mapped block onto the
free-list. Kernel `examples/os/kernel_fs2.fg` verified by
`tests/test_kernel_fs2.py` 6/6: exact transcript
`KERNKKKKKDONE` (boundary, delete + reuse, disk-full failure,
full-disk re-alloc after deletes), halted, and the predicted
heap state (bump 16, free-list empty, file 5's map row in
free-list pop order). Next: processes.

**Checkpoint 5 DONE 27 Oct 2026 — processes:** process table
in scratch 0x8000 (4 slots x 16 bytes [state, frame, mepc,
exit_code]; 0 free, 1 ready, 2 running, 3 done), cooperative
switching via ecall: 2 = spawn (fork into a free slot; parent
gets the pid, child 0, -1 if no slot), 3 = yield (round-robin
to the next ready task), 4 = exit(code) (mark done, switch on;
if nobody is ready, clear mtvec and ecall, which halts). The
sharp rule: fork copies only the trap frame, not main's
function frame, so the child must branch on the spawn result
immediately, and the parent records pids into scratch before
any yield and waits on those copies, never on the shared
locals. Kernel `examples/os/kernel_proc.fg` verified by
`tests/test_kernel_proc.py` 9/9: exact transcript
`KERNABABABDONE` (the ABABAB interleave proves switching),
halted, final states [running, done, done, free], exit codes
0, pids 1 and 2 recorded, plus a probe proving the
exit-with-nobody-left halt path. Next: shell.

**Checkpoint 6 DONE 27 Oct 2026 — shell:** a REPL over UART
RX: prompt, line input with echo, dispatch on the first
character (freestanding rejects string values, so commands are
single characters): h = help, p = procs, s = spawn the demo
task, w = wait for the last spawned task, q = quit, anything
else = ?. The shell yields while waiting for input and once
per iteration, so spawned tasks genuinely run between
keystrokes. This checkpoint also extends the big32 model
itself: `run()` takes `input_bytes`, and RX pops from that
queue (previously RX always returned -1, so no interactive
program could ever be tested). Kernel
`examples/os/kernel_shell.fg` verified by
`tests/test_kernel_shell.py`: exact transcript over the input
`h, x, s, w, p, q` (help, unknown, spawn with H/I landing
between prompts, wait printing W0, procs showing ready ->
done, BYE), halted. Next: GUI.

**Checkpoint 7 DONE 27 Oct 2026 — GUI:** no framebuffer
hardware exists in the model or the Verilog, so the GUI is a
text windowing system over UART in the ncurses spirit:
ANSI-drawn boxes rendered by the terminal, single-character
titles (freestanding rejects string values), and focus as a
redraw (no back-buffer exists). Kernel
`examples/os/kernel_gui.fg` verified by
`tests/test_kernel_gui.py`: exact ANSI byte stream (clear,
window A, overlapping window B, A redrawn to front, DONE),
halted. Next: drivers.

**Checkpoint 8 DONE 27 Oct 2026 — drivers:** UART driver
(putc/getc) and timer driver (mtime/mtimecmp, interrupt
enable, sleep) as the hardware layer — all MMIO goes through
these functions. Sleep blocks the task until its wake time;
the timer interrupt wakes due tasks and preemptively
switches; interrupts resume at mepc, ecalls at mepc + 4.
Kernel `examples/os/kernel_drivers.fg` verified by
`tests/test_kernel_drivers.py`: exact transcript
`KERNBADONE` (B before A proves wake ordering), halted,
final states [running, done, done, free], 7 timer ticks.
Caught in testing: the first demo used 3 vs 1 ticks and the
two wake times landed in the same tick interval, so A
printed first — sleep differences must exceed scheduling
jitter (~1900 steps here), so the demo uses 6 vs 1. Known
limitation: no idle task yet, so sleep with no other ready
task degrades to an immediate resume. Next: networking.

**Checkpoint 9 DONE 27 Oct 2026 — networking:** loopback
stack — SLIP framing (RFC 1055), UDP-inspired packets [dst,
src, len, payload, checksum], echo service on port 7. No NIC
exists in the model or the Verilog, so the wire is an
in-memory loopback buffer (bytes stored as words, linear
positions); everything else is a real stack. Kernel
`examples/os/kernel_net.fg` verified by
`tests/test_kernel_net.py`: exact transcript (KERN, PONG,
S4R3D1, DONE), halted, all 29 framed bytes consumed, sent 4
/ recv 3 / dropped 1 — the drop is a corrupted packet failing
its checksum, and the ESC path is exercised by a payload of
192. **Phase F is now complete:** memory management, tiny
filesystem, processes, shell, GUI, drivers, networking —
each as a standalone kernel. What remains is integration
(one kernel with a unified memory map) and the hardware the
model still fakes (timer CLINT in Verilog, a real NIC, a
framebuffer).

**Integration DONE 27 Oct 2026 — one unified kernel:**
`examples/os/kernel_unified.fg` runs every Phase F
subsystem in a single program: processes + preemptive timer,
bump allocator, filesystem v2, shell REPL, ANSI GUI windows,
loopback network stack. The map resolves every standalone
kernel's collisions: proc table 0x8000, current/last/ticks
0x8040/0x8044/0x8048, alloc bump 0x8050, FS bump/free
0x8060/0x8064, FS table 0x8070, FS map 0x80F0, net
positions/stats 0x82F0-0x830C, net packet area 0x8310, heap
0x8400-0x8800, loopback 0x8800-0x8C00, FS data
0x8C00-0x9C00, child stacks at 0xE000/0xC000 — all kernel
data below 0xA000, clear of both stack regions. Verified by
`tests/test_kernel_unified.py`: exact transcript over the
shell tour h/p/s/w/m/f/g/n/q (help, procs, spawn with
HI landing across a timer tick, wait W0, alloc M8400 in
hex, FS F, GUI windows, net PONG + S4R3D1, BYE), halted,
states [running, done, free, free], 25 timer ticks, heap
bump +16, net 4/3/1. Honest limits carried over: 2 child
slots only (a third stack would grow down through the
kernel regions), and the shell never sleeps (no idle task
yet). The 'm' command prints addresses in HEX, not
decimal: print_num assumes non-negative input, but SOC2
addresses sit above 2^31 and are negative in signed
32-bit arithmetic (0x80008400 printed as '*' through
print_num, since -2147449856 % 10 is -6) — hex works on
bit patterns via shifts and masks, so it is correct for
any address.

**Hardware frontier 1 DONE 27 Oct 2026 — legacy UART RX
on the Verilog SOC:** surveying the SOC before building
corrected an outdated note — the CLINT (mtime/mtimecmp,
timer interrupt into the core) already exists in
big32_soc2.v from the Linux-boot track's Phase 5, so the
real first gap was receive: the core already implemented
the RX contract (load 0x10000004 returns the byte, -1
when empty, pop on load) but the SOC tied ready to 0.
Added a 16-byte RX FIFO in big32_soc2.v (same push/pop
discipline as the 16550 FIFO; overflow drops), wired to
the core, fed by the existing top-level rx_data/rx_valid
pins. Proven by a directed echo program (~/workspace/
rx-proof/echo.s + tb_rx.v, kept out of the shared tree):
"Hi\n" fed through the pins came back out of TX —
**RX ECHO PASS**. Regression: soc2 plic + timer64 still
PASS with the edited SOC. The edit is LOCAL to the
shared big32 tree (not pushed — the Linux-boot track
owns BIG-32 publication). NEXT hardware item: the
unified kernel cannot run on SOC2 as-is — its scratch
(0x8000), stacks, and SP (0xFFFC) assume the model's
flat 64 KB memory, while SOC2 RAM lives at 0x80000000,
so it needs rebasing to SOC2 RAM addresses.

**Hardware frontier 2 DONE 27 Oct 2026 — unified kernel
runs on the Verilog SOC:** tools/rebase_soc2.py shifts
the kernel's RAM literals (105 in [0x8000, 0x10000),
MMIO/CSR/counts untouched, verified by distinct-value
audit) into examples/os/kernel_unified_soc2.fg, and a
new --stack-top build flag (default 65532 unchanged)
puts main's stack at 0x800F0000. The full shell tour
ran on big32_soc2 via the new RX path (tb_shell.v):
KERN, help, procs, spawn, W0, M80008400, F, GUI
windows, PONG + S4R3D1, BYE, HALTED after 45,461
cycles. One real bug found by the run: decimal
print_num breaks on SOC2 addresses (above 2^31, hence
negative signed — 0x80008400 printed as '*'), fixed by
printing addresses in hex (print_hex, shifts + masks).
Model test updated (M33792 -> M8400) and green. The
SOC2 edit from frontier 1 stays local (BIG-32
publication belongs to the Linux-boot track); the
RED-MOON- push below carries the rebase tooling.

**Hardware frontier 5 DONE 27 Oct 2026 — pixels
with a font:** SOC2 pixel framebuffer at 0x10020000,
mode-13h-style: 320x200, 8 bits per pixel, 64000 bytes
as 16000 words (byte 0 = leftmost of 4 pixels), word
stores only, aligned-word reads, NOT reset-cleared.
Kernel `examples/os/kernel_pix.fg` (SOC2-only, no RAM
scratch so no rebase needed) clears to black, draws a
white border and a white filled rectangle, and renders
"KERN" in black on the rectangle from a hand-drawn 8x8
font (glyphs K, E, R, N as small positive row bytes —
the font lives in code as row functions, because
freestanding mode has no arrays). Verified by
`tests/test_kernel_pix.py`: PIX PASS, all 64000 pixels
match, halted, UART KERN / DONE — and the text reads
cleanly as ASCII art in the test output. Regression:
soc2 plic + timer64 still PASS. Honest scope: palette
indices only (0 black, 1 white) — a palette register
is the next display step, not this one. The SOC2 pixel
edit stays LOCAL (BIG-32 publication belongs to the
Linux-boot track).

**INTEGRATION ON HARDWARE DONE 27 Oct 2026 — one
kernel, everything:** `examples/os/kernel_full.fg`
(unified base: shell, processes, bump allocator,
filesystem v2, sleep, ANSI GUI) + the network stack
over the REAL serial device (the loopback retires;
its buffer frees up) + text-VRAM windows (`t`) +
pixel windows with the font (`v`, including two new
glyphs A and B — the first draft's window titles
couldn't render with the K/E/R/N-only font).
One map, no collisions: device scratch remapped into
the unified net area (0x82F8–0x8350). Both VRAMs are
cleared at boot (the pixel clear alone is 16000
words). Verified by `tests/test_kernel_full.py` on
the combined testbench (shell tour fed over UART RX,
network peer live): FULL PASS — all 2000 text cells
and the pixel windows match, both TX packets
byte-exact, halted, exact 329-char shell-tour
transcript (KERN, help, procs, spawn H/I interleave,
M80008400, F, ANSI windows, PONG + S2R2D1, T, V,
BYE). Regression: soc2 plic + timer64 still PASS.
Testbench lesson, kept: the tour feeder syncs on the
KERN banner — a fixed delay would overflow the
16-byte RX FIFO during the boot VRAM clears. Limits
carried over: 2 child slots, no idle task, palette
indices only. The SOC2 device edits stay LOCAL
(BIG-32 publication belongs to the Linux-boot
track).

**Hardware frontier 4 DONE 27 Oct 2026 — a real
framebuffer:** SOC2 text-mode VRAM at 0x10004000,
VGA-text-style: 80x25 cells, 2 bytes per cell (char +
attribute), stored as 1000 words (2 cells per word).
Word stores only, aligned-word reads, VRAM deliberately
NOT reset-cleared (the kernel must clear it, like real
hardware powering up undefined). Kernel
`examples/os/kernel_fb.fg` (SOC2-only, no RAM scratch
so no rebase needed) clears the screen to spaces and
draws the GUI checkpoint's windows — A, B, then A to
the front — into VRAM instead of UART escapes.
Verified by `tests/test_kernel_fb.py`: FB PASS, all
2000 cells match including attributes (title chars
attr 1, everything else 0; the overlap region shows
A's cells, spaces included, over B's), halted, UART
KERN / DONE. Regression: soc2 plic + timer64 still
PASS. Debugging notes, owned: the first build failed
on the checker's own rule (`word` reassigned after a
plain `let` — needs `let mut`); then the clear word
took two tries (0x20202020 sets attr 0x20 too — the
right clear word is 0x00200020, char space + attr 0).
The SOC2 VRAM edit stays LOCAL (BIG-32 publication
belongs to the Linux-boot track). Honest scope: this
is TEXT mode, not pixels — a pixel framebuffer with a
font is the next hardware step, not this one.

**Hardware frontier 3 DONE 27 Oct 2026 — a real network
device:** SOC2 serial packet device at 0x10003000
(SLIP over a serial line, RFC 1055): TX_DATA +0x00 (WO),
RX_DATA +0x04 (RO, pop on read, -1 when empty), STATUS
+0x08 (RX ready, TX not full); 64-byte FIFOs each way,
TX drains one byte per cycle to the pins, RX pop uses
the mem_load_w discipline of the 16550. Kernel
`examples/os/kernel_netdev.fg` (model addresses, via
rebase_soc2.py; SOC2-only — the model has no net
device) runs the checkpoint-9 stack against it, with
the testbench as the peer: both transmitted packets
verified byte-exact, then the peer sends a reflection
(ESC path), a corrupted packet (dropped), and a pong.
Verified by `tests/test_kernel_netdev.py`: NETDEV PASS,
transcript KERN / PONG / S2R2D1 / DONE, halted.
Regression: soc2 plic + timer64 still PASS. Debugging
note, owned plainly: the first run failed with only
KERN — the bus trace showed stores to 0x10001000
(virtio), not 0x10003000, because the decimal I wrote
for 0x10003000 was wrong (268439552 is 0x10001000;
the correct value is 268447744). The assembler was
right; the hex spelling in the earlier probe had been
right. Lesson, now in the kernel's comments: the
language has no hex literals, so round-trip every MMIO
decimal through hex() before use. The SOC2 device edit
stays LOCAL (BIG-32 publication belongs to the
Linux-boot track). What remains on the hardware
frontier: a real framebuffer for the GUI.

**MACOS LOOK — STAGE 1A + 1B + 2 (STATIC) DONE 27 Oct 2026 — the
integrated OS gets a desktop picture:** Stage 1a grows the
SOC2 pixel VRAM from 320x200 to 640x480 (307200 bytes as
76800 words, still at 0x10020000) and adds a pointer device
at 0x10006000 (X +0x00, Y +0x04, BTN +0x08, read-only,
absolute position, TB-driven; pins guarded against
unconnected testbenches reading x). Stage 1b is
`tools/gen_font.py`, which emits one `glyph_<name>(row)`
function per glyph plus a `mac_font_row(ch, row)` dispatch
on ASCII code — 47 glyphs (14 capitals, 16 lowercase, 10
digits, 7 symbols); the 6 proven glyphs (K, E, R, N, A, B)
are reproduced byte-exact by the generator. Stage 2
(static) is `examples/os/kernel_mac.fg` (font + body,
1682 lines, SOC2-only, no RAM scratch): palette indices
0 black, 1 white, 2 light gray, 3 dark gray, 4 red,
5 yellow, 6 green, 7 deep blue, 8 mid blue, 9 light
blue; wallpaper as three horizontal bands; a menu bar
with Finder / File / Edit / View / Window / Help texts;
a dock with 5 icons (Finder, Terminal, Notes, Code,
Terminal-2); a Finder window and a Terminal window on
top, each with red / yellow / green traffic-light
circles and a title; the menu-bar clock reads "21:22"
as a STATIC mock, labelled as such in the file header
(a live clock comes with the event loop, where its
value is time-dependent and cannot be exact-checked).
Verified by `tests/test_kernel_mac.py`: MAC PASS —
desktop structure matches, halted after 4,664,710
cycles, UART MAC / DONE. Debugging, owned: the first
run failed 32 pixels with an empty UART file — the
kernel had not finished drawing inside the 5M-cycle
cap, because the fill recomputed its address with a
multiply and a divide on every word across ~120k word
fills; the fix carries a running address (computed
once per row segment, then +4 per word) and raises
the cap to 20M, and the layout preview now prints '?'
for unwritten pixels instead of letting them hide as
wallpaper. The second run failed exactly 1 pixel —
the test point, not the kernel: the Notes icon's
centre is crossed by the N diagonal stroke (glyph
row 4 = 137, that bit is ink), so the check moved
to a true background pixel in the same icon. Honest
scope: this is a static shot only — mock clock, no
pointer interaction yet (the device exists, the
static testbench ties it to 0), no apps. The SOC2
VRAM + pointer edits stay LOCAL (BIG-32 publication
belongs to the Linux-boot track). `kernel_pix.fg`
and `kernel_full.fg` moved to the same 640x480
geometry in the same tree state; their 640-wide
re-runs are the next verification step, not yet
claimed here.

**MACOS LOOK — STAGE 2 (INTERACTIVE) DONE 28 Oct 2026 — the
desktop moves:** `examples/os/kernel_mac_interactive.fg`
(font + body, SOC2-only, no RAM scratch) runs a redraw-based
event loop: state lives in main() locals (window positions,
focus, closed flags, drag state, previous button), and
`draw_desktop` repaints everything in z-order with the
focused window last, packing focus/closed flags into one
int to stay under the 8-register argument limit. Pointer
polls at 0x10006000; a press hits the top window first,
then the other — red light closes, title bar focuses and
starts a drag, body only focuses; a drag redraws only
when the position changes. The clock reads mtime low,
hours = (secs/3600)%24, minutes = (secs/60)%60, drawn
only when the minute changes; its signed low word wraps
after ~21 s at 100 MHz, so the test checks format and
position only, never the value. The kernel never halts.
Verified by `tests/test_kernel_mac_int.py` (testbench
`~/workspace/rx-proof/tb_mac_int.v`, outside the repo
like all testbenches): INTERACTIVE PASS — click Finder
title brings Finder on top, drag moves it by (+50,+50),
red light closes it and Terminal shows again, clock
pixels are ink or paper, UART exactly "MAC\n", after
~22M cycles. Debugging, owned: the first draft failed
to build with a branch offset of 4164 beyond the
±4095 range, because duplicated hit-test chains made
main() too large for one loop back-edge; factoring
`hit_window` (0 none / 1 red / 2 title / 3 body) fixed
it. Honest scope: still no apps — Finder and Terminal
are windows with titles, not working programs yet.

**FINDER APP — STAGE 1 DONE 28 Oct 2026 — the first working
app:** `examples/os/kernel_finder.fg` (SOC2-only, 640x480)
is the interactive desktop with filesystem v2 behind the
Finder window. At boot it creates three real files (ids 1,
2, 3) in the FS table, and the Finder window lists them by
reading the table itself — rows "FILE 1", "FILE 2", "FILE 3".
Clicking a row selects it (inverted); focus, drag and close
from the interactive kernel keep working, and the state
gains a selection nibble (selected × 8 in the packed state).
Honest limit, stated up front: FS v2 has numeric ids, no
filenames, so rows are FILE 1/2/3, not names. Verified by
`tests/test_kernel_finder.py` (testbench
`~/workspace/rx-proof/tb_mac_finder.v`, outside the repo
like all testbenches): FINDER PASS — list, select, drag,
clock all match, UART exactly "MAC\n", after ~18M cycles.
Debugging, owned, and worth recording because it will bite
again: the first finder kernel failed its click test in a
way that looked impossible — the click code, the call
sites and the pointer reads were all verified correct in
the compiled output and in isolation, yet the click
returned no hit and the screen showed a window the kernel
state said was never drawn. The cause was not the click
code at all: the FS v2 data (file table at 0x80008060,
block map at 0x80008100) sat INSIDE this kernel's code
image, which ends at 0x80008CC4, so `boot_files()` wrote
~640 bytes over ~160 of the kernel's own instructions
before the first draw — the draw survived (its code sits
below the overwritten region) and the press path did not.
The fix: FS v2 data lives in high RAM at 0x800E0000+
(table 0x800E0010, block map 0x800E0100, data blocks
0x800E1000), above the code and below the stack top, so
no boot write can ever touch an instruction. Rule going
forward: any kernel whose code image passes 0x8000 must
not use the old model-space FS bases. Next in the chain:
Terminal in a window, then the lifetime-ordered allocator
borrowed from the QAIRT work.

**TERMINAL IN A WINDOW — DONE 30 Oct 2026 — the second
working app:** `examples/os/kernel_term.fg` (SOC2-only,
640x480) is the Finder kernel plus a working terminal
inside the Terminal window. The terminal keeps a 16-line
× 38-column text buffer in high RAM (0x800E3000, one word
per character; cursor words at 0x800E3980/0x800E3984),
draws one cell per character at 8px × 10px pitch from the
window origin, and handles input only while the Terminal
is focused (focus starts on Terminal, so no click is
needed to type). Commands follow the C6 shell's first-char
dispatch: h = help line, f = list FS files as "file <id>"
lines, c = clear plus a fresh prompt, unknown = "?" line,
empty = a new prompt; backspace erases but never into the
prompt. Three glyphs the base font lacks were added
terminal-only ('>' = 62, '?' = 63, lowercase 'f' = 102);
the base font file was deliberately not touched. No
cursor block in v1, stated scope. Verified by
`tests/test_kernel_term.py` (testbench
`~/workspace/rx-proof/tb_mac_finder_longwait.v`, outside
the repo like all testbenches): FINDER PASS — list,
select, drag, clock all match, UART exactly "MAC\n",
after ~36M cycles. Debugging, owned, and worth recording
because it will bite again: the first two terminal runs
failed in a way that looked like broken input — the
click did not select, the drag did not move — and a
pixel-dump run then showed the Finder window VANISHING
after the click, which looked like a close bug. The
press path was verified clean in code (the click lands
as a body hit, not a close). The real cause was test
timing, not kernel logic: the terminal kernel's repaint
is bigger than the Finder kernel's (608 terminal cells),
and the testbench's 5.5M-cycle waits — calibrated for
the Finder kernel — caught the repaint mid-flight, just
before the Finder window (which draws last once focus
flips to it) got painted. The fix was in the test, not
the kernel: wait for the kernel's MAC signal instead of
a fixed count, and wait 14M cycles after the click and
drag instead of 5.5M. Rule going forward: testbench
waits must scale with the kernel's repaint size; a
failure that moves when the waits move is a test-timing
failure until proven otherwise.

**LIFETIME-ORDERED ALLOCATOR v2 — DONE 30 Oct 2026 —
the first QAIRT borrow, applied to the real allocator:**
`examples/os/kernel_lifetime2.fg` upgrades the C2
free-list allocator with lifetime-ordered placement: the
heap is split into a short region [0xA000, 0xB000) and a
long region [0xB000, 0xC000), each with its own bump
pointer and free list, and the same first-fit, split
(≥16), and coalesce rules run per list. `free` picks the
list from the block's address, so short churn can never
fragment long-lived space — and because each list holds
only its own region's blocks, a merge can never cross
the region boundary: the split is safe by construction,
not by a runtime guard. Verified by
`tests/test_kernel_lifetime2.py` (big32 model):
transcript LIFEKKKKKDONE, halted, short bump advanced
exactly three 24-byte blocks, long bump exactly one —
short reuse, long survival through short churn,
three-block coalescing, and a 48-byte alloc from the
coalesced space all check out. The segregated allocator
is available for the unified kernel to adopt; the chain
continues with the library batches. PUSHED + VERIFIED
30 Oct 2026 ~08:00 IST: RED-MOON- main d7a5c981 →
ffd9c9cc9752c45d0fc7ee0d874cfb6b716dd910
(API ref match + kernel_lifetime2.fg 4,462 bytes
exact on Contents API).

## What does not change

- Black Moon OS (the Linux distro) continues as the system people
  can actually use today. The from-scratch OS is a second track,
  not a replacement, until it can stand on its own.
- JalOS (the simulation) stays as the concepts prototype; its
  code does not become kernel code, its ideas do.
- Numbers in this document come from verified runs only; anything
  unbuilt is labelled as a plan, not a result.

## SBI dispatch demo kernel (agent+REA loop, 30 Oct 2026)
`examples/os/kernel_sbi_demo.fg` + `tests/test_kernel_sbi_demo.py` — the
agent+REA loop closed in Qasida: Ghidra's RISC-V decode of the big32 SBI
firmware (mscratch stack swap, mcause dispatch, EID compare-and-branch table)
was reimplemented fresh as a freestanding kernel with a `trap_handler` that
dispatches Base FIDs (0 = spec version 2, 1 = demo impl id 7) and TIME
(mtime low word) from ecalls, returning -2 for unknown EIDs. Documented
difference from SBI: Qasida's 2-argument `ecall` carries (EID in a7, one
argument in a0), so Base FIDs dispatch from a0, not a6; a 3-argument ecall is
the named future slice for exact SBI ABI. Model-verified transcript
`2 / 7 / <mtime> / -2 / DONE`, halted (halt via clear-mtvec-then-ecall).

## `ecall3` builtin (language upgrade, 30 Oct 2026)
`ecall3(eid, arg0, arg1) -> int`: extension id in `a7`, arguments in `a0`
and `a1`, result back in `a0` (big32 target only; native and WASM reject it
like `ecall`). `examples/os/kernel_ecall3.fg` + `tests/test_kernel_ecall3.py`
prove the second argument arrives: the handler returns `arg1 + 100` for
Base fid 1, so `ecall3(16, 1, 41)` prints `141`. Model-verified exact
transcript `2 / 141 / -2 / DONE`, halted. Honest scope: this is the
three-register call (`a7`, `a0`, `a1`); real SBI additionally uses `a6` for
the function id, so calling firmware SBI exactly still needs an
`a6`-carrying call, which remains a future slice.

## 16550 UART driver kernel (drivers item, 30 Oct 2026)
`examples/os/kernel_uart16550.fg` + `tests/test_kernel_uart16550.py` —
reference first: REA/Ghidra on /usr/bin/stty (x86-64) found no baud
procedure of its own (baud search: 0 hits); speed search hit only libc
termios imports (cfgetispeed/cfsetispeed/cfgetospeed/cfsetospeed), and
xrefs on cfsetospeed led to stty's own set_speed (src/stty.c, per its
assert string): a name-table walk + strcmp, then cfsetispeed/cfsetospeed
with the looked-up speed_t. So the kernel implements the hardware side
of that call: 16550 divisor = 1,843,200 / (16 * baud), DLAB divisor
latch, LCR 0x03 (8N1), FIFO enable. Model-verified transcript
`9600=12 / 19200=6 / 38400=3 / 115200=1 / DONE`, halted. The model has
no 16550 (those stores wrap into low dmem harmlessly), so the register
programming itself awaits a SOC2 Verilog run once no other sim is
running — the computation half is verified, the hardware half is queued.
