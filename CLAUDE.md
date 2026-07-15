# drishti — Claude Code Instructions

> **Core rule**: this file is **preferences, process, and procedures** —
> durable rules that change rarely. Volatile state (current version,
> module line counts, supported backends, test counts, dep-gap status,
> consumers) lives in [`docs/development/state.md`](docs/development/state.md).
> Do not inline state here.

## Project Identity

**drishti** (दृष्टि — Sanskrit: *sight / vision*) — sovereign video
codecs for AGNOS, pure Cyrius: no C, no FFI, no libav\*. ONE repo,
codec families as flat `[lib]` modules (the shravan model —
[ADR 0001](docs/adr/0001-one-repo-module-per-codec.md)): **AV1**
(decode+encode, replaces dav1d+rav1e), **H.264/AVC** (decode+encode,
replaces openh264), **H.265/HEVC** (decode-only, replaces libde265),
**VP8/VP9** (decode+encode, replaces libvpx), over a shared
bit-I/O + VLC + IVF core.

- **Type**: Library (no CLI binary — consumers link `dist/drishti.cyr`)
- **License**: GPL-3.0-only
- **Language**: Cyrius (toolchain pinned in `cyrius.cyml [package].cyrius`)
- **Version**: `VERSION` at the project root is the source of truth — do not inline the number here
- **Genesis repo**: [agnosticos](https://github.com/MacCracken/agnosticos)
- **Standards**: [First-Party Standards](https://github.com/MacCracken/agnosticos/blob/main/docs/development/first-party/first-party-standards.md) · [First-Party Documentation](https://github.com/MacCracken/agnosticos/blob/main/docs/development/first-party/first-party-documentation.md)

## Goal

Own **video codec decode/encode** for AGNOS — encoded bitstream bytes
→ pixels (and back), with zero C dependency. What shravan is to audio,
drishti is to video. Consumers: tarang, tazama, jalwa, aethersafta.

## Current State

> Volatile state lives in [`docs/development/state.md`](docs/development/state.md) —
> current version, surface area, in-flight work, consumers, dep gaps.
> Refreshed every release.

This file (`CLAUDE.md`) is durable rules.

## Scaffolding

Project was scaffolded with `cyrius init` (greenfield) or `cyrius port` (Rust → Cyrius migration). **Do not manually create project structure** — use the tools. If a tool is missing something, fix the tool.

## Quick Start

```sh
cyrius deps                          # resolve sibling deps
cyrius build programs/smoke.cyr build/drishti-smoke
cyrius test                          # run [build].test + tests/*.tcyr
```

## Key Principles

- **Correctness over cleverness** — a codec that mis-parses one field is worse than one that rejects the stream cleanly
- **Spec-first, multi-source** — derive every parse/coding step from the SPEC (cite the section inline); cross-check against multiple implementations (dav1d+libaom, openh264+x264+JM+ffmpeg, libde265+HM, libvpx), NEVER port from one. Citations live in [`docs/sources.md`](docs/sources.md)
- **Trust no input byte** — encoded video is hostile: bounds-check every read, reject lying sizes/truncation via sticky error codes (never crash, never OOB, never infinite-loop), cap dimension bombs, fuzz from day one
- **Family prefixes are a hard rule** — `dr_` core / `av1_` / `h264_` / `h265_` / `vbool_` / `vp8_` / `vp9_` on EVERY symbol incl. helpers; cyrius has no module-private scoping and silently shadows duplicate fn names (last-def-wins, warn-only). Family error codes stay in the reserved bands in `src/drishti.cyr`
- **Flat modules** — domain modules (`src/*.cyr` except `main.cyr`) carry ZERO include lines; `src/main.cyr` is the single wiring point, mirrored by `cyrius.cyml [lib].modules` in dependency order. That's what keeps `dist/drishti.cyr` compile-clean
- **Entropy coders stay per-family** — CABAC / adaptive-CDF / boolean coder do NOT get speculatively unified (roadmap "consolidation watch")
- Test after every change, not after the feature is "done" — `make test` is cheap
- ONE change at a time — never bundle unrelated changes
- Build with `cyrius build`, not raw `cat file | cycc` — the manifest auto-resolves deps and prepends includes
- Every buffer declaration is a contract: function-local `var buf[N]` = N **bytes**; module-global `var buf[N]` in an INCLUDED module = N × u64 (8N bytes) — comment the unit at every declaration
- `&&` / `||` short-circuit; mixed expressions require explicit parens
- **`>>` is LOGICAL; `>>>` is arithmetic (sign-preserving)** — the reverse of JS/Java, and
  the single easiest way to silently corrupt signed maths (transforms, `Round2`, MV
  projection). `&` is two's-complement, so the spec's `~(x - 1)` transcribes as `(0 - x)`.
  Comparisons yield exactly 0/1, so the spec's arithmetic on booleans (`2 * AboveIntra`,
  `a ^ b`) transcribes directly
- Cyrius **silently shadows duplicate `fn` names** (last-def-wins, warn-only) — there is no
  module-private scoping, so grep before naming a driver over an existing leaf; the
  convention is leaf = `_sym` suffix, driver = plain name. `grep -hoE '^fn [a-z0-9_]+'
  src/*.cyr | sort | uniq -d` must be empty. A wrong ARG COUNT also does not hard-fail —
  changing a signature needs every call site checked by hand
- Hand-built test vectors comment EVERY field's bit packing; anything with a writer gets a round-trip test; adversarial cases (truncation, lying sizes, forbidden bits) are part of the definition of done
- **A test you have not seen fail is not evidence** — mutation-verify: break the code on purpose, confirm the suite goes red, restore. Known answers come from a spec-literal port in `scripts/refs/`, never from the Cyrius. See [`docs/guides/verification.md`](docs/guides/verification.md) for the loop and the failure modes (circular tests, aliased fixtures, digest blindness, silent name shadowing)

## Rules (Hard Constraints)

- **Do not commit or push** — the user handles all git operations
- **Never use `gh` CLI** — use `curl` to the GitHub API if needed
- Do not skip tests before claiming changes work
- Do not use `sys_system()` with unsanitized input — command injection
- Do not trust external data (file / network / args) without validation
- Do not modify `lib/` files (vendored stdlib / dep symlinks)
- Do not hardcode toolchain versions in CI YAML — `cyrius = "X.Y.Z"` in `cyrius.cyml` is the source of truth

## Documentation

- [`docs/adr/`](docs/adr/) — Architecture Decision Records (*why X over Y?*)
- [`docs/architecture/`](docs/architecture/) — Non-obvious constraints (*what's true about the code?*)
- [`docs/guides/`](docs/guides/) — Task-oriented how-tos; **[`verification.md`](docs/guides/verification.md) is the one to read first** — the spec-derive → reference-port → mutation-verify → adversarial-review loop, and the failure modes that shipped green without it
- [`docs/examples/`](docs/examples/) — Runnable examples
- [`docs/development/state.md`](docs/development/state.md) — Live state snapshot
- [`docs/development/roadmap.md`](docs/development/roadmap.md) — Milestones through v1.0

## Process

1. **Work phase** — features, roadmap items, bug fixes
2. **Build check** — `cyrius build`
3. **Test + benchmark additions** for new code
4. **Internal review** — performance, memory, correctness, edge cases
5. **Documentation** — update CHANGELOG, `docs/development/state.md`, any ADR the change earned
6. **Version sync** — `VERSION`, `cyrius.cyml`, CHANGELOG header

