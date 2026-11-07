# Stability promise — Qasida 1.0

From 1.0.0 onward, the language follows semantic versioning for real:

- **1.x releases add, never break.** New builtins, new stdlib functions,
  new backends, and new syntax may arrive in a minor release. Existing
  programs written against documented behaviour keep compiling and
  behaving the same.
- **Breaking changes require a major version.** If a change would break
  a program that follows the documented language surface, it ships as
  2.0.0 (or later), never as 1.x.
- **Deprecation first.** A feature headed for removal is marked
  deprecated in the CHANGELOG and kept working for at least one minor
  release before it goes away in the next major release.

## What the promise covers

- The `.fg` language surface documented in README, docs/BOOK.md, and
  docs/HIGH_SCHOOL_GUIDE.md: syntax, types, control flow, builtins,
  and safe-mode semantics (checked arithmetic, bounds checks, no null,
  no implicit conversions).
- The stdlib APIs in `forge_lang/stdlib/` as documented in docs/ECOSYSTEM.md
  (function names, argument order, return types).
- The `qasida` command-line interface: `run`, `build`, `test`, `fmt`,
  `pkg`, `emit-wasm`, `emit-big32`, and their flags as documented.
- The package format and lockfile produced by `qasida pkg`.

## What it does NOT cover (honest limits)

- **Missing features are gaps, not breaks.** The language still lacks
  things (float printing on big32, PNG/JPEG loading). Adding them in 1.x is
  not a breaking change; their absence in 1.0 is stated in the README
  and CHANGELOG, not hidden.
- **Experimental backends.** The CUDA emitter, the big32 soft-float
  helpers, and the self-hosting front-end prototype are experimental:
  their internal APIs and output details may change in 1.x.
- **Performance characteristics.** Speed may change (usually for the
  better) in any release; only correctness semantics are promised.
- **Error message text.** The wording of checker and compiler errors
  may improve in 1.x; programs must not parse it. Error *kinds*
  (which programs are rejected) are covered.
- **The WASM v1/v2 subset.** The set of constructs the WASM backend
  accepts will grow in 1.x (that is an addition, not a break); programs
  the subset already accepts keep working.

## Why 1.0 now

1.0 is a commitment, not a claim of completeness. The language has a
real toolchain (formatter, LSP, REPL, tests, packages, debugger,
fuzzer), verified numbers behind its claims, and a public issue
tracker in the repo. What it does not yet have — a large user base,
a deep package ecosystem, fluent demo models — is stated openly
and is not part of this promise.
