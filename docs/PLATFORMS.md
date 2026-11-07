# Platforms — Qasida

What runs where, what blocks the rest, and what would unblock it.
Verified 26 Oct 2026 on a Linux VM (x86_64, gcc, OpenSSL headers
present). Nothing here claims a binary that was not built.

## Linux (x86_64) — verified

The supported platform. `forge.py run/build` compiles generated C
with `cc` (`-std=gnu11 -pthread`, `-lm -lssl -lcrypto`, falling
back to `-lm` if the SSL libraries are missing). Install is
verified on a clean HOME and a clean pip venv (1.0.0).

## The C compiler is selectable: `QASIDA_CC`

`forge.py run`, `forge.py build`, and the shared-library build all
use `QASIDA_CC` when it is set, and `cc` otherwise. The default
is unchanged, so this is an addition, not a behavior change:

```
QASIDA_CC=/usr/bin/gcc python3 forge.py run examples/fib.fg
QASIDA_CC=x86_64-w64-mingw32-gcc-posix python3 forge.py build prog.fg -o prog.exe
```

Setting it to a cross compiler produces a binary for another
OS wherever the generated C compiles for that OS — that is
now true for Windows via MinGW (see below; run-verification
still pending), and still untested for macOS.

## Windows (MinGW-w64) — cross-compiles, not yet run-verified

Done 27 Oct 2026: the generated C now has a `#ifdef _WIN32`
branch (forge_lang/codegen.py HEADER) — winsock headers
(`winsock2.h`, `ws2tcpip.h`) instead of the POSIX socket
headers, a `forge_sock_t` type (`SOCKET` on Windows, `int`
elsewhere), `closesocket` via `forge_sock_close`, lazy
`WSAStartup` via `forge_sock_init` (called by the HTTP client
and `http_listen`), and link `-lws2_32`. The `-posix`
MinGW variant provides `pthread.h`, so threads work too.
Fast mode drops `-march=native` for MinGW targets (it
describes the build machine, not the target).

Verified 27 Oct 2026 with `gcc-mingw-w64-x86-64` 13.2.0
(`x86_64-w64-mingw32-gcc-posix`), safe mode unless noted:

```
QASIDA_CC=x86_64-w64-mingw32-gcc-posix python3 forge.py build prog.fg -o prog.exe
```

Programs cross-compiled to working `.exe` files: a hello
program, the HTTP registry server (`examples/apps/
registry_server.fg`, plain sockets), `scope_demo.fg`
(threads), struct-array, nested-array, and break demos,
plus an `http_get("https://…")` program (compiles to the
HTTPS stub below). Fast mode also cross-compiles.

Limits, stated honestly:

- **Run-verified: NO.** No Wine is installed in this VM,
  so the `.exe` files compile but have never executed.
  A Windows machine (or Wine) still needs to run one and
  report back before Windows is called supported.
- **HTTPS is off by default on Windows.** No MinGW
  OpenSSL is available here, so `https_get` compiles to
  a stub that fails at runtime with a clear message
  ("HTTPS is not supported in this build"). Plain HTTP
  and non-network programs are unaffected. A Windows
  user with MSYS2 OpenSSL can opt back in with
  `QASIDA_HAVE_OPENSSL=1` (untested here).
- **Same opt-out exists everywhere:** `QASIDA_NO_OPENSSL=1`
  builds any platform without OpenSSL (same stub). This
  is also the macOS-without-Homebrew-OpenSSL path.

## macOS — NOT verified here, path documented

No macOS machine, SDK, or Apple clang is available in this VM,
and `zig` (the usual Linux-to-macOS cross toolchain) is not
installed, so no macOS binary was built or tested. By analysis:

- The POSIX headers in the generated C all exist on macOS
  (pthread, sockets, unistd), so the socket code is not the
  blocker it is on Windows.
- The blocker is OpenSSL: macOS ships no OpenSSL headers by
  default. A native macOS build needs Homebrew OpenSSL
  (`brew install openssl`, with its include/lib paths visible
  to the compiler), or the same conditional-HTTPS work as
  Windows item 2 above.
- A native build ON a Mac (Xcode command-line tools + Homebrew
  OpenSSL + `QASIDA_CC` if a specific clang is wanted) is the
  plausible first macOS binary. Cross-compiling macOS binaries
  from Linux needs an Apple SDK or zig, neither of which is
  present here.

## Notes for distributed binaries

- Fast mode uses `-march=native`: a binary built in fast mode
  may not run on a different CPU. Ship release binaries built
  in safe mode (or with an explicit portable `-march`), not
  fast mode.
- WASM and big32 backends do not use the C compiler at all, so
  they are unaffected by all of the above. The playground
  (Pyodide + WASM) is already OS-independent.
- The Python toolchain itself (`forge.py`, `pip install`) is
  platform-neutral; only the native C backend has OS-specific
  requirements.
