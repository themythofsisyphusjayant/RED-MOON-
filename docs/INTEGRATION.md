# Integration: RED-MOON- × BLACK-MOON-OS-

How the two repositories fit together, who owns what, and which
combinations are verified to work. This file lives in RED-MOON- (the
language side); BLACK-MOON-OS- carries a mirror note (`INTEGRATION.md`
at its root) from the distro side.

## Current state (27 Oct 2026)

- RED-MOON- live `main` (code): `6a92164f` (HTTPS proxy support, pushed 27 Oct 2026).
- BLACK-MOON-OS- live `main` (code): `a98cddb` (INTEGRATION.md added 27 Oct 2026).
- The post-1.1.0 drift is CLOSED: live `main` now contains the Windows
  port, registry deploy configs, JalOS with `ai`/`audit` (1408 lines),
  and CHANGELOG "Unreleased" entries.
- Note on refs: doc-only pushes move `main` after this file is written,
  so the refs above name the last code push. The matrix below records
  code combinations, which doc pushes do not invalidate.
- Local git HEAD here (`4688857`, v0.3.0 era) is stale and is NOT the
  push path: RED-MOON- is published by `scripts/push_forge.py`, which
  builds Git trees from this working tree via the GitHub API. Do not
  treat local git history as the project's history.
- **12 Nov 2026 — the OS moved out of RED-MOON-:** `examples/os/`
  (JalOS + all `kernel_*.fg`) and `tests/test_kernel_*.py` now live
  in [MOON-OS](https://github.com/themythofsisyphusjayant/MOON-OS).
  This file's JalOS rows below now point there; the compiler
  (including freestanding mode and the `ecall`/`ecall3` builtins)
  stays in RED-MOON-.

## Ownership

| Component | Owner | Notes |
|---|---|---|
| Qasida language, compiler, stdlib, registry, packages | RED-MOON- | Source of truth; versioned releases |
| `jalos.fg` (JalOS source) | [MOON-OS](https://github.com/themythofsisyphusjayant/MOON-OS) | Moved 12 Nov 2026 from RED-MOON- `examples/os/`; suite-guarded there now |
| Distro profile, theme, AI/sec launchers, installer | BLACK-MOON-OS- | archiso profile under `distro/` |
| `jalos.fg` copies in BLACK-MOON-OS- (root + `distro/.../blackmoon/`) | BLACK-MOON-OS- vendors | Byte-identical copies of MOON-OS's file; see Sync |
| Kaggle notebook (`jalos-on-kaggle.ipynb`) | Neither (workspace) | Reference combined workflow; clones both repos |

## Interfaces (explicit, no silent dependencies)

1. **Source compatibility.** BLACK-MOON-OS- consumes RED-MOON-
   releases: any `jalos.fg` it ships must build with the released
   compiler. JalOS needs v1.1.0-level features (arrays of structs,
   `break`, string indexing); minimum compiler is RED-MOON- v1.1.0.
2. **Vendoring, not submodules.** BLACK-MOON-OS- carries copies of
   `jalos.fg`, not a git submodule: the API push scripts build plain
   trees and do not support gitlinks, so copies plus a check script
   are the mechanism that actually works here.
3. **Sync check.** The checker `tools/check_jalos_sync.py` lived in
   RED-MOON- and was removed with the OS move (12 Nov 2026); it
   verified the combined workflow: all three `jalos.fg` copies
   byte-identical, the demo output matches BLACK-MOON-OS-'s
   `tests/expected_output.txt`, and the `ai`/`audit` commands print
   their expected markers. Until it is re-added in MOON-OS,
   byte-compare the copies by hand before any release that touches
   either side.
4. **Distro install.** `blackmoon-install-qasida` (BLACK-MOON-OS-)
   clones RED-MOON- into the installed system and runs its
   `scripts/install.sh`. The distro therefore depends on RED-MOON-'s
   install script staying runnable, not on any internal layout.
5. **Kaggle notebook.** Clones RED-MOON- (compiler) + BLACK-MOON-OS-
   (`jalos.fg`) and builds across repos. It is the standing proof
   that the two live mains work together (see Matrix).

## Compatibility matrix (verified, not claimed)

| RED-MOON- | BLACK-MOON-OS- | Verified | How |
|---|---|---|---|
| v1.1.0 (`d56a903`) | `6fab40f` | 27 Oct 2026 | Kaggle kernel v1: RUNNING → COMPLETE; log shows demo, `ai` (4 epochs), `audit` |
| working tree post-1.1.0 | `6fab40f` | 27 Oct 2026 | `jalos.fg` byte-identical across all 3 copies; demo output identical (254 lines) |
| `627904d` | `8fa46c2` | 27 Oct 2026 | Fresh public clones of both repos: full native suite PASS + sync check 9/9 |
| `6a92164f` | `a98cddb` | 27 Oct 2026 | Kaggle kernel v2: RUNNING → COMPLETE; log shows demo, `ai` (4 epochs), `audit`; clones used contain the proxy code |

## Known drift (open, not hidden)

- No code drift at present: both live mains contain the same JalOS.
- Verification gap CLOSED 27 Oct 2026: Kaggle kernel v2 ran the current
  code refs (`6a92164f` + `a98cddb`) to COMPLETE. (Kaggle re-runs need
  the owner's token re-supplied each time, per the standing rule.)
- BLACK-MOON-OS- live `main` is current.
- The distro ISO itself is still unbuilt/unbooted (needs an Arch
  builder); the theme, AI/sec launchers, and installer theme-copying
  are untested until first boot, same as the rest of the profile.

## Sync procedure (on any JalOS or compiler change)

1. Change `jalos.fg` in MOON-OS (or the compiler here) and run the
   full native suite (`python3 forge.py test`).
2. Copy `jalos.fg` to BLACK-MOON-OS- root and
   `distro/archiso/airootfs/usr/share/blackmoon/jalos.fg`; byte-compare.
3. Byte-compare the three `jalos.fg` copies by hand (the old
   `tools/check_jalos_sync.py` was removed with the OS move).
4. Push RED-MOON- (`scripts/push_forge.py`) and BLACK-MOON-OS-
   (`scripts/push_jalos.py`) — **only on the owner's explicit word**;
   pushes are external publication and are never assumed.
5. Update the matrix above with the new refs and how they were verified.

## Next actions

1. Decide the next version number/release notes (no version bump
   decided yet) — the pushed tree is post-1.1.0 but unversioned.
2. First ISO build + VM boot test (needs an Arch builder) — the
   standing blocker for every distro claim beyond "profile done".
3. (Done 27 Oct 2026) Kaggle re-run against the new refs — kernel v2
   COMPLETE; verification gap closed (see matrix).
4. (Done 27 Oct 2026) HTTP client proxy (CONNECT) support — was the
   named next language feature JalOS wanted; shipped in RED-MOON-,
   tested in `tests/test_proxy_connect.py` (6/6).
