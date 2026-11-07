# JalOS — a complete teaching OS in Qasida

One file, `jalos.fg` (1408 lines), implementing every subsystem a
modern OS has, at the architecture level:

| Subsystem | What JalOS does |
|---|---|
| Bootloader + kernel + init | Banner, RAM test, rootfs mount, daemon startup, login |
| Process management | Fixed process table, spawn, kill, ps/top |
| Scheduler | Priority scheduling in one-step quanta, tick log |
| Memory management | First-fit free-list allocator over 1024 simulated words, split + coalesce, `malloc`/`free`/`mem` |
| Filesystem | Hierarchical VFS (inodes by index), mkdir/write/cat/cp/mv/rm/ls, `/proc` pseudo-filesystem |
| Permissions + users | root/guest, file owners, owner-or-root checks, `su`, `useradd`, `/etc/passwd` |
| Devices | Console, loopback network device, disk (the VFS) |
| Networking | `ping` (loopback, simulated), `ifconfig`, `httpget` (real HTTP through the host stack) |
| Package manager | `pkg list/search/info/install/remove` — install really fetches the package source over HTTPS from the repo |
| Services + logging | cron (heartbeat every 5 ticks), syslog (`/var/log/syslog`), `logger`, `services` |
| Shell | ~30 commands, script files, single-command mode, `history`, `env`, `uptime`, `df`, `shutdown`, `ai`, `audit` |

## Run it

```
python3 forge.py run examples/os/jalos.fg            # built-in demo tour
python3 forge.py run examples/os/jalos.fg script.txt # run a script file
python3 forge.py run examples/os/jalos.fg ps         # a single command
```

The demo tour is offline and deterministic, and it is wired into
`tests/run_tests.py` as an exact-output test.

## Honest limits

- **Not bootable — yet.** JalOS itself still runs on top of a
  host OS: it is a simulation, not a kernel. But the language
  underneath it has changed since this was written: Qasida now
  has a freestanding mode (`--freestanding`: no libc, own
  `_start`), raw memory (`peek32`/`poke32`), bitwise operators,
  CSR builtins, an `ecall` builtin, and a `trap_handler` hook —
  the pieces a bootable kernel needs. The from-scratch kernel
  track (Phases A–D done, first kernel next) lives in
  `docs/FREESTANDING.md`; JalOS's ideas feed that kernel, but
  JalOS the program does not become it. What Qasida still
  lacks for kernel work: pointers and inline assembly.
- **No GUI.** No graphics builtins exist, so the desktop is the
  text shell. A TUI window manager over ANSI escapes is possible
  later; it is not here.
- **No passwords worth trusting.** Passwords are compared as plain
  strings (no hashing builtin exists) — the user model demonstrates
  permissions, it does not secure anything real.
- **HTTPS works through proxies now.** `pkg install` and `httpget`
  over HTTPS honour `https_proxy` / `HTTPS_PROXY` (plain HTTP
  proxy, `CONNECT` handshake before TLS; `no_proxy` bypasses it).
  In a proxied sandbox, set the proxy env vars and HTTPS works;
  plain HTTP works everywhere regardless.
- **No persistence.** The VFS lives in memory; shutdown loses it.
  Saving the filesystem image to a host file is a planned step.
